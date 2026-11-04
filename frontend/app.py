import sys
import uuid
import json
from pathlib import Path

import streamlit as st
import rasterio
import cv2
import numpy as np

from PIL import Image

# Project paths
BASE_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(BASE_DIR))

from backend.services.pipeline import run_pipeline
from database.db import create_project, create_processing_run


OUTPUT_DIR = BASE_DIR / "outputs"
UPLOAD_DIR = BASE_DIR / "dataset" / "raw_images" / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Page configuration
st.set_page_config(
    page_title="Urban Parcel Mapping",
    page_icon="🛰️",
    layout="wide"
)


# Helper functions
def load_image(path):

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)

    if image is None:
        return None

    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

    elif image.shape[2] >= 3:
        image = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2RGB)

    return image


def get_metadata(path):

    with rasterio.open(path) as src:

        return {
            "width": src.width,
            "height": src.height,
            "bands": src.count,
            "crs": str(src.crs),
            "bounds": str(src.bounds)
        }


def display_run(run_id):

    run_dir = OUTPUT_DIR / f"run_{run_id}"

    building_path = (
        run_dir / "detection" / "building_mask.png"
    )

    candidate_path = (
        run_dir / "parcels" / "candidate_regions_mask.png"
    )

    geojson_path = (
        run_dir / "parcels" / "candidate_regions.geojson"
    )

    if not building_path.exists():
        st.warning("Building mask not available.")
        return

    if not candidate_path.exists():
        st.warning("Candidate region mask not available.")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Building Detection")
        st.image(str(building_path), use_container_width=True)

    with col2:
        st.subheader("Candidate Open Regions")
        st.image(str(candidate_path), use_container_width=True)

    if geojson_path.exists():

        with open(geojson_path, "r", encoding="utf-8") as file:
            geojson_data = json.load(file)

        features = geojson_data.get("features", [])

        st.subheader("Processing Results")

        areas = [
            feature.get("properties", {}).get("area_sqm", 0)
            for feature in features
        ]

        c1, c2 = st.columns(2)

        c1.metric("Candidate Regions", len(features))

        c2.metric(
            "Total Candidate Area",
            f"{sum(areas):,.2f} m²"
        )

        with open(geojson_path, "rb") as file:

            st.download_button(
                label="Download GeoJSON",
                data=file.read(),
                file_name=f"candidate_regions_run_{run_id}.geojson",
                mime="application/geo+json"
            )


# Header
st.title("🛰️ AI-Based Automated Urban Parcel Mapping")

st.caption(
    "Satellite and drone imagery analysis using computer vision "
    "and geospatial processing."
)

st.divider()


# Sidebar
st.sidebar.title("Navigation")

page = st.sidebar.radio(
    "Select Section",
    [
        "Dashboard",
        "Upload Image",
        "Previous Results"
    ]
)


# Dashboard
if page == "Dashboard":

    st.header("Project Dashboard")

    st.write(
        "Automated building detection and candidate open-region "
        "extraction from georeferenced aerial imagery."
    )

    st.subheader("Existing Demonstration Run")

    run_dir = OUTPUT_DIR / "run_1"

    if run_dir.exists():

        st.success("Previous processing run is available.")

        display_run(1)

    else:

        st.info("No previous processing results found.")


# Upload Image
elif page == "Upload Image":

    st.header("Upload Geospatial Image")

    uploaded_file = st.file_uploader(
        "Upload a GeoTIFF image",
        type=["tif", "tiff"]
    )

    if uploaded_file is not None:

        st.success(f"Uploaded: {uploaded_file.name}")

        temp_path = UPLOAD_DIR / (
            f"{uuid.uuid4().hex}_{Path(uploaded_file.name).name}"
        )

        temp_path.write_bytes(uploaded_file.getvalue())

        try:

            metadata = get_metadata(temp_path)

            st.subheader("Image Metadata")

            col1, col2, col3 = st.columns(3)

            col1.metric("Width", metadata["width"])
            col2.metric("Height", metadata["height"])
            col3.metric("Bands", metadata["bands"])

            st.write("CRS:", metadata["crs"])

            if metadata["crs"] == "None":
                st.error("Image does not contain a CRS.")

            elif metadata["bands"] < 3:
                st.error("Image must contain at least 3 bands.")

            else:

                st.subheader("Uploaded Image Preview")

                with rasterio.open(temp_path) as src:

                    preview = src.read(
                        [1, 2, 3],
                        out_shape=(
                            3,
                            min(800, src.height),
                            min(800, src.width)
                        )
                    )

                preview = np.transpose(preview, (1, 2, 0))
                preview = preview.astype(np.float32)

                for channel in range(3):

                    band = preview[:, :, channel]

                    low, high = np.percentile(
                        band, [2, 98]
                    )

                    if high > low:
                        preview[:, :, channel] = (
                            (band - low) / (high - low) * 255
                        )

                preview = np.clip(
                    preview, 0, 255
                ).astype(np.uint8)

                st.image(
                    preview,
                    caption="Uploaded GeoTIFF",
                    use_container_width=True
                )

                if st.button(
                    "Start Processing",
                    type="primary"
                ):

                    with st.spinner(
                        "Processing image. This may take several minutes..."
                    ):

                        project_id = create_project(
                            project_name=Path(uploaded_file.name).stem,
                            image_name=uploaded_file.name,
                            image_width=metadata["width"],
                            image_height=metadata["height"],
                            crs=metadata["crs"]
                        )

                        run_id = create_processing_run(project_id)

                        result = run_pipeline(
                            run_id,
                            image_path=temp_path
                        )

                    st.success("Processing completed!")

                    st.json(result)

                    display_run(run_id)

        except Exception as error:

            st.error(f"Error: {error}")


# Previous Results
elif page == "Previous Results":

    st.header("Previous Processing Results")

    available_runs = []

    for folder in OUTPUT_DIR.glob("run_*"):

        if folder.is_dir():

            try:
                run_id = int(folder.name.split("_")[1])
                available_runs.append(run_id)

            except ValueError:
                continue

    available_runs.sort(reverse=True)

    if available_runs:

        selected_run = st.selectbox(
            "Select Processing Run",
            available_runs
        )

        display_run(selected_run)

    else:

        st.info("No processing runs available.")