from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer


class ImageValidationError(ValueError):
    pass


def _ground_resolution_m(src):
    if src.crs is None or src.width < 1 or src.height < 1:
        return None

    transform = src.transform
    column = src.width / 2.0
    row = src.height / 2.0
    x0, y0 = transform * (column, row)
    x1, y1 = transform * (column + 1, row)
    x2, y2 = transform * (column, row + 1)

    if src.crs.is_projected and str(src.crs.linear_units).lower() in {"metre", "meter", "m"}:
        return [
            float(np.hypot(x1 - x0, y1 - y0)),
            float(np.hypot(x2 - x0, y2 - y0)),
        ]

    transformer = Transformer.from_crs(src.crs, "EPSG:3857", always_xy=True)
    ax, ay = transformer.transform(x0, y0)
    bx, by = transformer.transform(x1, y1)
    cx, cy = transformer.transform(x2, y2)
    return [
        float(np.hypot(bx - ax, by - ay)),
        float(np.hypot(cx - ax, cy - ay)),
    ]


def inspect_geotiff(image_path):
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    try:
        dataset = rasterio.open(image_path)
    except Exception as error:
        raise ImageValidationError(f"Could not read the file as a raster: {error}") from error

    with dataset as src:
        problems = []
        crs = None if src.crs is None else str(src.crs)
        transform = src.transform
        coefficients = [transform.a, transform.b, transform.c, transform.d, transform.e, transform.f]
        north_up = (
            abs(transform.b) <= 1e-9
            and abs(transform.d) <= 1e-9
            and transform.a > 0
            and transform.e < 0
        )
        bounds = None
        resolution_m = None

        if src.crs is not None:
            try:
                from preprocessing.display import geographic_bounds

                bounds = geographic_bounds(src)
                resolution_m = _ground_resolution_m(src)
            except Exception as error:
                problems.append(f"Could not resolve geographic bounds: {error}")

        metadata = {
            "width": int(src.width),
            "height": int(src.height),
            "bands": int(src.count),
            "crs": crs,
            "dtype": str(src.dtypes[0]) if src.dtypes else None,
            "bounds": bounds,
            "transform": coefficients,
            "resolution": [float(src.res[0]), float(src.res[1])],
            "resolution_m": resolution_m,
            "nodata": None if src.nodata is None else src.nodata,
            "north_up": bool(north_up),
            "file_size_bytes": int(image_path.stat().st_size),
            "problems": problems,
        }
    return metadata


def validate_geotiff(image_path):
    metadata = inspect_geotiff(image_path)
    problems = list(metadata.get("problems") or [])

    if metadata["width"] < 64 or metadata["height"] < 64:
        problems.append(
            f"Image dimensions {metadata['width']}x{metadata['height']} "
            "are below the 64x64 minimum."
        )

    if metadata["bands"] < 1:
        problems.append("Image does not contain any bands.")

    if not metadata["crs"]:
        problems.append("Image has no coordinate reference system.")

    transform = metadata.get("transform") or []
    if len(transform) != 6 or not all(np.isfinite(transform)):
        problems.append("Image affine transform is missing or invalid.")

    resolution = metadata.get("resolution") or [0, 0]
    if resolution[0] == 0 or resolution[1] == 0:
        problems.append("Image pixel resolution is zero.")

    if metadata.get("bounds") is None and metadata.get("crs"):
        problems.append("Image geographic bounds could not be calculated.")

    if problems:
        raise ImageValidationError(" ".join(problems))

    return metadata


def validate_for_detection(metadata):
    if metadata["bands"] < 3:
        raise ImageValidationError(
            f"Building detection needs at least 3 bands. This image has {metadata['bands']}."
        )
    return metadata


def load_image(image_path):
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    with rasterio.open(image_path) as src:
        image = src.read()
        metadata = {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "crs": str(src.crs),
            "transform": src.transform,
            "bounds": src.bounds,
            "dtype": str(src.dtypes[0]),
        }

    return image, metadata
