import json
from pathlib import Path

import cv2
import rasterio
from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from ai_model.building_detection import detect_buildings
from database.db import (
    mark_run_failed,
    save_processing_results,
    update_processing_status,
    update_run_progress,
)
from parcel_extraction.extract_parcels import extract_parcels
from preprocessing.display import clear_invalid_pixels, render_mask_overlay


BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_IMAGE_PATH = BASE_DIR / "dataset" / "raw_images" / "residential_blocks.tif"

MODEL_PATH = BASE_DIR / "ai_model" / "model_weights" / "model.onnx"

OUTPUT_DIR = BASE_DIR / "outputs"


def _to_wgs84_geometry(geometry, source_crs):
    polygon = shape(geometry)

    if source_crs is None:
        raise ValueError("Input image must have a CRS.")

    crs_text = str(source_crs)
    if crs_text not in {"EPSG:4326", "OGC:CRS84"}:
        transformer = Transformer.from_crs(
            source_crs,
            "EPSG:4326",
            always_xy=True,
        )
        polygon = transform(transformer.transform, polygon)

    if polygon.is_empty:
        return None

    return mapping(polygon)


def run_pipeline(run_id, image_path=None):
    if image_path is None:
        image_path = DEFAULT_IMAGE_PATH
    else:
        image_path = Path(image_path)

    run_output = OUTPUT_DIR / f"run_{run_id}"
    detection_output = run_output / "detection"
    parcel_output = run_output / "parcels"
    detection_output.mkdir(parents=True, exist_ok=True)
    parcel_output.mkdir(parents=True, exist_ok=True)

    try:
        print("\nStarting urban parcel mapping pipeline...")
        update_processing_status(run_id, "processing")

        if not image_path.exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"ONNX model not found: {MODEL_PATH}")

        with rasterio.open(image_path) as src:
            image_width = src.width
            image_height = src.height
            image_crs = src.crs

            if src.count < 3:
                raise ValueError("Input image must contain at least 3 bands.")

            if src.crs is None:
                raise ValueError("Input image must have a valid CRS.")

        print(f"Input image: {image_path.name}")
        print(f"Image dimensions: {image_width} x {image_height}")
        print(f"CRS: {image_crs}")

        update_run_progress(run_id, "building_detection", 0, 0)
        print("\nRunning building detection...")

        def report_detection_progress(current, total):
            update_run_progress(run_id, "building_detection", current, total)

        building_mask_path = detect_buildings(
            image_path=str(image_path),
            output_dir=str(detection_output),
            model_path=str(MODEL_PATH),
            progress_callback=report_detection_progress,
        )
        clear_invalid_pixels(image_path, building_mask_path)

        print("\nExtracting candidate regions...")
        update_run_progress(run_id, "candidate_extraction", 0, 0)

        def report_extraction_progress(current, total):
            update_run_progress(run_id, "candidate_extraction", current, total)

        geojson_path, parcel_mask_path, region_count = extract_parcels(
            image_path=str(image_path),
            building_mask_path=str(building_mask_path),
            output_dir=str(parcel_output),
            progress_callback=report_extraction_progress,
        )

        update_run_progress(run_id, "rendering_overlays", 0, 0)
        building_overlay = render_mask_overlay(
            image_path,
            building_mask_path,
            detection_output / "building_overlay.png",
            color_rgb=(214, 69, 45),
        )
        candidate_overlay = render_mask_overlay(
            image_path,
            parcel_mask_path,
            parcel_output / "candidate_overlay.png",
            color_rgb=(217, 149, 38),
        )
        if building_overlay["overlay_bounds"] != candidate_overlay["overlay_bounds"]:
            raise RuntimeError("Generated overlays do not share the same geospatial extent.")
        building_overlay_path = building_overlay["path"]
        candidate_overlay_path = candidate_overlay["path"]

        with open(geojson_path, "r", encoding="utf-8") as file:
            geojson_data = json.load(file)

        regions = []
        for feature in geojson_data.get("features", []):
            properties = feature.get("properties", {})
            geometry = _to_wgs84_geometry(feature["geometry"], image_crs)
            if geometry is None:
                continue

            regions.append(
                {
                    "region_number": int(properties.get("region_number", len(regions) + 1)),
                    "area_sqm": float(properties.get("area_sqm", 0)),
                    "geometry": geometry,
                }
            )

        building_mask = cv2.imread(str(building_mask_path), cv2.IMREAD_GRAYSCALE)
        if building_mask is None:
            raise RuntimeError("Could not read generated building mask.")

        building_pixels = int(cv2.countNonZero(building_mask))

        save_processing_results(
            run_id=run_id,
            building_pixels=building_pixels,
            regions=regions,
            building_mask_path=building_mask_path,
            candidate_mask_path=parcel_mask_path,
            building_overlay_path=building_overlay_path,
            candidate_overlay_path=candidate_overlay_path,
            geojson_path=geojson_path,
            candidate_count=region_count,
        )

        print("\nPipeline completed successfully!")

        return {
            "run_id": run_id,
            "status": "completed",
            "input_image": str(image_path),
            "image_width": image_width,
            "image_height": image_height,
            "crs": str(image_crs),
            "building_pixels": building_pixels,
            "candidate_regions": region_count,
            "building_mask": str(building_mask_path),
            "parcel_mask": str(parcel_mask_path),
            "geojson": str(geojson_path),
        }

    except Exception as error:
        mark_run_failed(run_id, error)
        raise RuntimeError(f"Processing failed: {error}") from error
