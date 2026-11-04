import os
import json
import cv2
import numpy as np
import rasterio

from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import transform
from pyproj import Transformer


def extract_parcels(
    image_path,
    building_mask_path,
    output_dir
):

    os.makedirs(output_dir, exist_ok=True)

    with rasterio.open(image_path) as src:

        image = src.read([1, 2, 3])
        transform_affine = src.transform
        crs = src.crs

        if crs is None:
            raise ValueError(
                "Input image must have a CRS."
            )

        image = np.transpose(
            image,
            (1, 2, 0)
        )

    building_mask = cv2.imread(
        building_mask_path,
        cv2.IMREAD_GRAYSCALE
    )

    if building_mask is None:
        raise FileNotFoundError(
            building_mask_path
        )

    if building_mask.shape != image.shape[:2]:
        raise ValueError(
            "Building mask dimensions do not match input image."
        )

    # Identify vegetation using HSV
    hsv = cv2.cvtColor(
        image.astype(np.uint8),
        cv2.COLOR_RGB2HSV
    )

    vegetation_mask = (
        (hsv[:, :, 0] >= 25) &
        (hsv[:, :, 0] <= 100) &
        (hsv[:, :, 1] > 35) &
        (hsv[:, :, 2] > 35)
    )

    # Candidate open regions:
    # Exclude detected buildings and vegetation.
    building_binary = building_mask > 0

    candidate_mask = (
        (~building_binary) &
        (~vegetation_mask)
    ).astype(np.uint8)

    kernel = np.ones(
        (5, 5),
        dtype=np.uint8
    )

    candidate_mask = cv2.morphologyEx(
        candidate_mask,
        cv2.MORPH_OPEN,
        kernel
    )

    count, labels, stats, centroids = (
        cv2.connectedComponentsWithStats(
            candidate_mask,
            connectivity=8
        )
    )

    filtered_mask = np.zeros_like(
        candidate_mask,
        dtype=np.uint8
    )

    features = []

    # Transform geographic geometries to a metre-based CRS
    source_crs = crs

    if source_crs.is_geographic:
        target_crs = "EPSG:32618"
    else:
        target_crs = source_crs

    transformer = Transformer.from_crs(
        source_crs,
        target_crs,
        always_xy=True
    )

    region_number = 0

    for label in range(1, count):

        area_pixels = stats[
            label,
            cv2.CC_STAT_AREA
        ]

        if area_pixels < 500:
            continue

        region_number += 1

        filtered_mask[
            labels == label
        ] = 255

        for geom, value in shapes(
            (labels == label).astype(np.uint8),
            mask=(labels == label),
            transform=transform_affine
        ):

            if value != 1:
                continue

            polygon = shape(geom)

            projected_polygon = transform(
                transformer.transform,
                polygon
            )

            area_sqm = projected_polygon.area

            features.append({
                "type": "Feature",
                "properties": {
                    "region_number": region_number,
                    "area_sqm": round(
                        area_sqm,
                        2
                    ),
                    "classification": "candidate_open_region"
                },
                "geometry": mapping(polygon)
            })

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    geojson_path = os.path.join(
        output_dir,
        "candidate_regions.geojson"
    )

    mask_path = os.path.join(
        output_dir,
        "candidate_regions_mask.png"
    )

    with open(
        geojson_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            geojson,
            file
        )

    cv2.imwrite(
        mask_path,
        filtered_mask
    )

    print(
        f"Candidate regions detected: {region_number}"
    )

    return (
        geojson_path,
        mask_path,
        region_number
    )