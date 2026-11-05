"""Browser-ready georeferenced previews and map overlays.

The original GeoTIFF is never modified. Display rasters are reprojected to
EPSG:3857 so a Leaflet image overlay lines up with the OpenStreetMap basemap.
"""

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import Affine, from_bounds
from rasterio.warp import reproject, transform_bounds
from scipy import ndimage


WEB_MERCATOR = CRS.from_epsg(3857)
WGS84 = CRS.from_epsg(4326)
DISPLAY_MAX_SIZE = 2048

# Orthomosaics often store the empty frame as pure black without a NoData tag.
VOID_CORE = 6
VOID_FRINGE = 18


def _finite_bounds(west, south, east, north):
    values = [west, south, east, north]
    if not all(np.isfinite(values)):
        raise ValueError("Raster bounds are not finite.")
    if east <= west or north <= south:
        raise ValueError("Raster bounds do not form a usable geographic extent.")
    return {
        "west": float(west),
        "south": float(south),
        "east": float(east),
        "north": float(north),
    }


def geographic_bounds(src):
    if src.crs is None:
        raise ValueError("Raster has no coordinate reference system.")
    west, south, east, north = transform_bounds(
        src.crs,
        WGS84,
        *src.bounds,
        densify_pts=21,
    )
    return _finite_bounds(west, south, east, north)


def mercator_frame(src, max_size=DISPLAY_MAX_SIZE):
    """North-up Web Mercator grid covering the raster footprint."""
    if src.crs is None:
        raise ValueError("Raster has no coordinate reference system.")

    left, bottom, right, top = transform_bounds(
        src.crs,
        WEB_MERCATOR,
        *src.bounds,
        densify_pts=21,
    )
    width_m = float(right - left)
    height_m = float(top - bottom)
    if width_m <= 0 or height_m <= 0 or not np.isfinite([width_m, height_m]).all():
        raise ValueError("Raster geographic extent is empty.")

    if width_m >= height_m:
        dst_width = int(max_size)
        dst_height = max(1, int(round(max_size * height_m / width_m)))
    else:
        dst_height = int(max_size)
        dst_width = max(1, int(round(max_size * width_m / height_m)))

    dst_transform = from_bounds(left, bottom, right, top, dst_width, dst_height)
    west, south, east, north = transform_bounds(
        WEB_MERCATOR,
        WGS84,
        left,
        bottom,
        right,
        top,
        densify_pts=21,
    )
    return {
        "width": dst_width,
        "height": dst_height,
        "transform": dst_transform,
        "crs": WEB_MERCATOR,
        "bounds": _finite_bounds(west, south, east, north),
    }


def _read_scale(src, max_pixels):
    pixels = src.width * src.height
    if max_pixels is None or pixels <= max_pixels:
        return 1, 1, src.width, src.height, src.transform
    scale = (pixels / float(max_pixels)) ** 0.5
    out_width = max(1, int(round(src.width / scale)))
    out_height = max(1, int(round(src.height / scale)))
    transform = src.transform * Affine.scale(
        src.width / out_width,
        src.height / out_height,
    )
    return src.width / out_width, src.height / out_height, out_width, out_height, transform


def _to_display_units(rgb):
    data = rgb.astype(np.float32)
    finite = np.isfinite(data)
    if not finite.any():
        return np.zeros_like(data)
    peak = float(np.nanpercentile(data[finite], 99))
    if peak <= 1.5:
        data = data * 255.0
    return data


def border_void_mask(display_rgb, valid):
    """Border-connected near-black frame, excluding interior dark roofs."""
    if display_rgb.ndim != 3 or display_rgb.shape[2] < 3:
        raise ValueError("Expected an RGB image.")

    dark = np.all(display_rgb <= VOID_CORE, axis=2) & valid
    if not dark.any():
        return valid

    seed = np.zeros(dark.shape, dtype=bool)
    seed[0, :] = dark[0, :]
    seed[-1, :] = dark[-1, :]
    seed[:, 0] = dark[:, 0]
    seed[:, -1] = dark[:, -1]
    if not seed.any():
        return valid

    structure = np.ones((3, 3), dtype=int)
    void = ndimage.binary_propagation(seed, mask=dark, structure=structure)
    fringe = np.all(display_rgb <= VOID_FRINGE, axis=2) & valid
    void = ndimage.binary_propagation(void, mask=fringe, structure=structure)
    cleaned = valid & ~void
    if cleaned.any():
        return cleaned
    return valid


def _color_indexes(src):
    alpha_index = None
    color_indexes = []
    for index, interpretation in zip(src.indexes, src.colorinterp):
        if interpretation == ColorInterp.alpha:
            alpha_index = index
        else:
            color_indexes.append(index)
    if not color_indexes:
        color_indexes = [index for index in src.indexes if index != alpha_index]
    return color_indexes, alpha_index


def load_rgb(src, max_pixels=None):
    """Read RGB (or replicated grayscale) on the source grid or a reduced grid."""
    _, _, out_width, out_height, transform = _read_scale(src, max_pixels)
    resampling = Resampling.nearest
    color_indexes, alpha_index = _color_indexes(src)
    reduced = out_width != src.width or out_height != src.height
    out_shape = (out_height, out_width) if reduced else None

    def read_band(index):
        if out_shape is None:
            return src.read(index)
        return src.read(index, out_shape=out_shape, resampling=resampling)

    if len(color_indexes) >= 3:
        raw = np.stack([read_band(index) for index in color_indexes[:3]], axis=0)
    else:
        band = read_band(color_indexes[0])
        raw = np.stack([band, band, band], axis=0)

    alpha = read_band(alpha_index) if alpha_index else None
    rgb = np.moveaxis(raw, 0, -1)
    return rgb, alpha, transform


def valid_mask_from_rgb(rgb, alpha, nodata):
    raw = rgb.astype(np.float32)
    valid = np.isfinite(raw).all(axis=2)
    if nodata is not None and np.isfinite(nodata):
        valid &= ~np.any(np.isclose(raw, float(nodata)), axis=2)
    if alpha is not None:
        valid &= alpha > 0
    display = _to_display_units(raw)
    valid = border_void_mask(display, valid)
    return valid, display


def stretch_rgba(display_rgb, valid):
    stretched = display_rgb.astype(np.float32).copy()
    for channel in range(3):
        band = stretched[:, :, channel]
        values = band[valid]
        values = values[np.isfinite(values)]
        if values.size == 0:
            continue
        low, high = np.percentile(values, [2, 98])
        if high > low:
            stretched[:, :, channel] = (band - low) / (high - low) * 255.0
    stretched = np.clip(stretched, 0, 255)
    rgba = np.zeros((*valid.shape, 4), dtype=np.uint8)
    rgba[:, :, :3] = stretched.astype(np.uint8)
    rgba[:, :, 3] = np.where(valid, 255, 0).astype(np.uint8)
    # Keep a non-zero value for genuine dark pixels so 0 can mean NoData while warping.
    dark_valid = valid & np.all(rgba[:, :, :3] == 0, axis=2)
    rgba[dark_valid, :3] = 1
    return rgba


def _warp_rgba(rgba, src_transform, src_crs, frame):
    rgb = rgba[:, :, :3].astype(np.float32)
    rgb[rgba[:, :, 3] == 0] = np.nan
    destination = np.full((3, frame["height"], frame["width"]), np.nan, dtype=np.float32)
    reproject(
        source=np.moveaxis(rgb, 2, 0),
        destination=destination,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=np.nan,
        dst_transform=frame["transform"],
        dst_crs=frame["crs"],
        dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    alpha = np.zeros((frame["height"], frame["width"]), dtype=np.uint8)
    reproject(
        source=rgba[:, :, 3],
        destination=alpha,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=0,
        dst_transform=frame["transform"],
        dst_crs=frame["crs"],
        dst_nodata=0,
        resampling=Resampling.nearest,
    )
    colors = np.nan_to_num(np.moveaxis(destination, 0, -1), nan=0.0)
    warped = np.zeros((frame["height"], frame["width"], 4), dtype=np.uint8)
    warped[:, :, :3] = np.clip(colors, 0, 255).astype(np.uint8)
    warped[:, :, 3] = np.where(alpha > 0, 255, 0).astype(np.uint8)
    warped[warped[:, :, 3] == 0, :3] = 0
    return warped


def render_image_preview(image_path, output_path, max_size=DISPLAY_MAX_SIZE, max_pixels=24_000_000):
    image_path = Path(image_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(image_path) as src:
        if src.crs is None:
            raise ValueError("Raster has no coordinate reference system.")
        if src.count < 1:
            raise ValueError("Raster does not contain any bands.")
        frame = mercator_frame(src, max_size=max_size)
        rgb, alpha, transform = load_rgb(src, max_pixels=max_pixels)
        nodata = src.nodata
        source_crs = src.crs

    valid, display = valid_mask_from_rgb(rgb, alpha, nodata)
    rgba = stretch_rgba(display, valid)
    warped = _warp_rgba(rgba, transform, source_crs, frame)
    Image.fromarray(warped, mode="RGBA").save(output_path, format="PNG", optimize=True)
    return {
        "path": str(output_path),
        "overlay_bounds": frame["bounds"],
        "width": frame["width"],
        "height": frame["height"],
    }


def valid_pixel_mask(image_path):
    """Full-resolution validity mask aligned to the source raster."""
    with rasterio.open(image_path) as src:
        rgb, alpha, _transform = load_rgb(src, max_pixels=None)
        valid, _display = valid_mask_from_rgb(rgb, alpha, src.nodata)
    if valid.shape != (rgb.shape[0], rgb.shape[1]):
        raise RuntimeError("Validity mask does not match the raster.")
    return valid


def clear_invalid_pixels(image_path, mask_path):
    """Zero mask pixels that fall in NoData or the border void."""
    import cv2

    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Mask not found: {mask_path}")
    valid = valid_pixel_mask(image_path)
    if mask.shape != valid.shape:
        raise ValueError(
            f"Mask shape {mask.shape} does not match raster shape {valid.shape}."
        )
    mask[~valid] = 0
    output = Path(mask_path)
    written = cv2.imencode(".png", mask)[1]
    written.tofile(str(output))
    return mask


def render_mask_overlay(
    image_path,
    mask_path,
    output_path,
    color_rgb,
    max_size=DISPLAY_MAX_SIZE,
    alpha=176,
):
    import cv2

    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Mask not found: {mask_path}")

    with rasterio.open(image_path) as src:
        if mask.shape != (src.height, src.width):
            raise ValueError(
                f"Mask shape {mask.shape} does not match raster {(src.height, src.width)}."
            )
        frame = mercator_frame(src, max_size=max_size)
        src_transform = src.transform
        src_crs = src.crs

    warped = np.zeros((frame["height"], frame["width"]), dtype=np.uint8)
    reproject(
        source=mask,
        destination=warped,
        src_transform=src_transform,
        src_crs=src_crs,
        src_nodata=0,
        dst_transform=frame["transform"],
        dst_crs=frame["crs"],
        dst_nodata=0,
        resampling=Resampling.nearest,
    )

    rgba = np.zeros((frame["height"], frame["width"], 4), dtype=np.uint8)
    selected = warped > 0
    rgba[selected, 0] = int(color_rgb[0])
    rgba[selected, 1] = int(color_rgb[1])
    rgba[selected, 2] = int(color_rgb[2])
    rgba[selected, 3] = int(alpha)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG", optimize=True)
    return {
        "path": str(output_path),
        "overlay_bounds": frame["bounds"],
        "width": frame["width"],
        "height": frame["height"],
    }
