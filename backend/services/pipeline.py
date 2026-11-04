import json
import sqlite3
from pathlib import Path
from datetime import datetime

import cv2
import rasterio

from ai_model.building_detection import detect_buildings
from parcel_extraction.extract_parcels import extract_parcels


# Project paths
BASE_DIR = Path(__file__).resolve().parents[2]

DEFAULT_IMAGE_PATH = (
    BASE_DIR / "dataset" / "raw_images" / "residential_blocks.tif"
)

MODEL_PATH = (
    BASE_DIR / "ai_model" / "model_weights" / "model.onnx"
)

OUTPUT_DIR = BASE_DIR / "outputs"

DB_PATH = BASE_DIR / "database" / "urban_mapping.db"


def update_run_status(run_id, status):

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE processing_runs
            SET status = ?
            WHERE id = ?
            """,
            (status, run_id)
        )


def run_pipeline(run_id, image_path=None):

    # Select input image
    if image_path is None:
        image_path = DEFAULT_IMAGE_PATH
    else:
        image_path = Path(image_path)

    # Create output directories
    run_output = OUTPUT_DIR / f"run_{run_id}"

    detection_output = run_output / "detection"
    parcel_output = run_output / "parcels"

    detection_output.mkdir(parents=True, exist_ok=True)
    parcel_output.mkdir(parents=True, exist_ok=True)

    try:

        print("\nStarting urban parcel mapping pipeline...")

        update_run_status(run_id, "processing")

        # Validate files
        if not image_path.exists():
            raise FileNotFoundError(
                f"Input image not found: {image_path}"
            )

        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"ONNX model not found: {MODEL_PATH}"
            )

        # Read image metadata
        with rasterio.open(image_path) as src:

            image_width = src.width
            image_height = src.height
            image_crs = str(src.crs)

            if src.count < 3:
                raise ValueError(
                    "Input image must contain at least 3 bands."
                )

            if src.crs is None:
                raise ValueError(
                    "Input image must have a valid CRS."
                )

        print(f"Input image: {image_path.name}")
        print(f"Image dimensions: {image_width} x {image_height}")
        print(f"CRS: {image_crs}")

        # STEP 1: Building detection
        print("\nRunning building detection...")

        building_mask_path = detect_buildings(
            image_path=str(image_path),
            output_dir=str(detection_output),
            model_path=str(MODEL_PATH)
        )

        # STEP 2: Candidate region extraction
        print("\nExtracting candidate regions...")

        geojson_path, parcel_mask_path, region_count = extract_parcels(
            image_path=str(image_path),
            building_mask_path=str(building_mask_path),
            output_dir=str(parcel_output)
        )

        # STEP 3: Read GeoJSON
        with open(geojson_path, "r", encoding="utf-8") as file:
            geojson_data = json.load(file)

        regions = []

        for index, feature in enumerate(
            geojson_data.get("features", []),
            start=1
        ):

            properties = feature.get("properties", {})

            regions.append({
                "region_number": index,
                "area_sqm": float(
                    properties.get("area_sqm", 0)
                ),
                "geometry": json.dumps(
                    feature["geometry"]
                )
            })

        # STEP 4: Calculate building pixels
        building_mask = cv2.imread(
            str(building_mask_path),
            cv2.IMREAD_GRAYSCALE
        )

        if building_mask is None:
            raise RuntimeError(
                "Could not read generated building mask."
            )

        building_pixels = int(
            cv2.countNonZero(building_mask)
        )

        # STEP 5: Store results in database
        with sqlite3.connect(DB_PATH) as conn:

            # Remove old region records if this run is retried
            conn.execute(
                """
                DELETE FROM candidate_regions
                WHERE run_id = ?
                """,
                (run_id,)
            )

            conn.execute(
                """
                UPDATE processing_runs
                SET building_pixels = ?,
                    candidate_count = ?,
                    completed_at = ?
                WHERE id = ?
                """,
                (
                    building_pixels,
                    region_count,
                    datetime.now().isoformat(),
                    run_id
                )
            )

            for region in regions:

                conn.execute(
                    """
                    INSERT INTO candidate_regions
                    (
                        run_id,
                        region_number,
                        area_sqm,
                        geometry
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        region["region_number"],
                        region["area_sqm"],
                        region["geometry"]
                    )
                )

        # STEP 6: Update processing status
        update_run_status(run_id, "completed")

        print("\nPipeline completed successfully!")

        return {
            "run_id": run_id,
            "status": "completed",
            "input_image": str(image_path),
            "image_width": image_width,
            "image_height": image_height,
            "crs": image_crs,
            "building_pixels": building_pixels,
            "candidate_regions": region_count,
            "building_mask": str(building_mask_path),
            "parcel_mask": str(parcel_mask_path),
            "geojson": str(geojson_path)
        }

    except Exception as error:

        update_run_status(run_id, "failed")

        raise RuntimeError(
            f"Processing failed: {error}"
        ) from error