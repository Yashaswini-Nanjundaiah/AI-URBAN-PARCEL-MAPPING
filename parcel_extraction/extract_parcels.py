import json
import os

import cv2
import numpy as np
import rasterio
from pyproj import Geod
from rasterio.features import shapes
from shapely.geometry import mapping, shape
from shapely.ops import transform as project_geometry
from shapely.validation import make_valid
from pyproj import Transformer

from preprocessing.display import valid_pixel_mask


GEOD = Geod(ellps="WGS84")
MIN_REGION_PIXELS = 500


def _to_wgs84(polygon, crs):
    crs_text = str(crs)
    if crs_text in {"EPSG:4326", "OGC:CRS84"}:
        return polygon
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return project_geometry(transformer.transform, polygon)


def _area_sqm(polygon, crs):
    geographic = _to_wgs84(polygon, crs)
    if not geographic.is_valid:
        geographic = make_valid(geographic)
    area, _perimeter = GEOD.geometry_area_perimeter(geographic)
    return abs(float(area)), geographic


def _uint8_rgb(image):
    data = image.astype(np.float32)
    finite = np.isfinite(data)
    peak = float(np.nanpercentile(data[finite], 99)) if finite.any() else 0.0
    if peak <= 1.5:
        data = data * 255.0
    return np.clip(data, 0, 255).astype(np.uint8)


def extract_parcels(image_path, building_mask_path, output_dir, progress_callback=None):
    os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(image_path) as src:
        if src.count < 3:
            raise ValueError("Candidate extraction requires at least 3 bands.")
        if src.crs is None:
            raise ValueError("Input image must have a CRS.")
        image = src.read([1, 2, 3])
        transform_affine = src.transform
        crs = src.crs
        image = np.transpose(image, (1, 2, 0))

    building_mask = cv2.imread(building_mask_path, cv2.IMREAD_GRAYSCALE)
    if building_mask is None:
        raise FileNotFoundError(building_mask_path)
    if building_mask.shape != image.shape[:2]:
        raise ValueError("Building mask dimensions do not match input image.")

    valid = valid_pixel_mask(image_path)
    if valid.shape != building_mask.shape:
        raise ValueError("Validity mask dimensions do not match input image.")

    rgb = _uint8_rgb(image)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    vegetation_mask = (
        (hsv[:, :, 0] >= 25)
        & (hsv[:, :, 0] <= 100)
        & (hsv[:, :, 1] > 35)
        & (hsv[:, :, 2] > 35)
    )

    candidate_mask = (
        valid
        & (building_mask == 0)
        & (~vegetation_mask)
    ).astype(np.uint8)

    kernel = np.ones((5, 5), dtype=np.uint8)
    candidate_mask = cv2.morphologyEx(candidate_mask, cv2.MORPH_OPEN, kernel)

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        candidate_mask,
        connectivity=8,
    )

    features = []
    region_number = 0

    eligible = np.zeros(count, dtype=bool)
    eligible[1:] = stats[1:, cv2.CC_STAT_AREA] >= MIN_REGION_PIXELS
    filtered_labels = np.where(eligible[labels], labels, 0).astype(np.int32)
    filtered_mask = np.where(filtered_labels > 0, 255, 0).astype(np.uint8)
    polygon_shapes = list(
        shapes(
            filtered_labels,
            mask=filtered_labels > 0,
            transform=transform_affine,
            connectivity=4,
        )
    )
    total_regions = len(polygon_shapes)
    processed_regions = 0

    for geometry, _value in polygon_shapes:
        processed_regions += 1
        if progress_callback and (
            processed_regions == total_regions or processed_regions % 10 == 0
        ):
            progress_callback(processed_regions, total_regions)
        polygon = shape(geometry)
        if polygon.is_empty:
            continue
        if not polygon.is_valid:
            polygon = make_valid(polygon)
        if polygon.geom_type == "GeometryCollection":
            polygon = max(
                (part for part in polygon.geoms if part.geom_type in {"Polygon", "MultiPolygon"}),
                key=lambda part: part.area,
                default=None,
            )
        if polygon is None or polygon.is_empty:
            continue

        area_sqm, geographic = _area_sqm(polygon, crs)
        if area_sqm <= 0:
            continue

        point = geographic.representative_point()
        minx, miny, maxx, maxy = geographic.bounds
        region_number += 1
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "region_number": region_number,
                    "area_sqm": round(area_sqm, 2),
                    "classification": "candidate_open_region",
                    "centroid_lon": round(float(point.x), 8),
                    "centroid_lat": round(float(point.y), 8),
                    "bbox": [
                        round(float(minx), 8),
                        round(float(miny), 8),
                        round(float(maxx), 8),
                        round(float(maxy), 8),
                    ],
                },
                "geometry": mapping(geographic),
            }
        )

    geojson = {
        "type": "FeatureCollection",
        "crs_epsg": 4326,
        "features": features,
    }
    geojson_path = os.path.join(output_dir, "candidate_regions.geojson")
    mask_path = os.path.join(output_dir, "candidate_regions_mask.png")

    with open(geojson_path, "w", encoding="utf-8") as file:
        json.dump(geojson, file)

    encoded = cv2.imencode(".png", filtered_mask)[1]
    encoded.tofile(mask_path)
    return geojson_path, mask_path, region_number
