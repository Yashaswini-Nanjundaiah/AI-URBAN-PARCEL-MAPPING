import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from database.db import create_project, get_project
from preprocessing.image_loader import (
    ImageValidationError,
    validate_for_detection,
    validate_geotiff,
)
from preprocessing.preview import write_preview


router = APIRouter(prefix="/api", tags=["Uploads"])

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "dataset" / "raw_images" / "uploads"
PREVIEW_DIR = BASE_DIR / "outputs" / "previews"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(filename):
    name = Path(filename or "upload.tif").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if not cleaned.lower().endswith((".tif", ".tiff")):
        cleaned = f"{cleaned}.tif"
    return cleaned


def _project_payload(project):
    return {
        "project_id": project["id"],
        "project_name": project["project_name"],
        "image_name": project["image_name"],
        "width": project["image_width"],
        "height": project["image_height"],
        "bands": project["bands"],
        "crs": project["crs"],
        "bounds": project["bounds"],
        "geographic_bounds": project.get("geographic_bounds"),
        "resolution_m": project.get("resolution_m"),
        "file_size_bytes": project.get("file_size_bytes"),
        "nodata": project.get("nodata"),
        "north_up": project.get("north_up"),
        "dtype": project.get("dtype"),
        "preview_url": f"/api/projects/{project['id']}/preview",
        "created_at": project["created_at"],
    }


@router.post("/uploads")
async def upload_geotiff(file: UploadFile):
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()

    if suffix not in {".tif", ".tiff"}:
        raise HTTPException(
            status_code=400,
            detail="Only GeoTIFF files (.tif, .tiff) can be uploaded.",
        )

    destination = UPLOAD_DIR / f"{uuid.uuid4().hex}_{_safe_filename(filename)}"

    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not store the uploaded file: {error}",
        ) from error
    finally:
        await file.close()

    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        metadata = validate_for_detection(validate_geotiff(destination))
    except ImageValidationError as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not read the uploaded GeoTIFF: {error}",
        ) from error

    preview_path = PREVIEW_DIR / f"{destination.stem}.png"
    overlay_bounds = None
    try:
        preview_result = write_preview(destination, preview_path)
        preview_path = Path(preview_result["path"])
        overlay_bounds = preview_result.get("overlay_bounds")
    except Exception as error:
        destination.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not create an image preview: {error}",
        ) from error

    try:
        project_id = create_project(
            project_name=Path(filename).stem or destination.stem,
            image_name=Path(filename).name,
            image_width=metadata["width"],
            image_height=metadata["height"],
            crs=metadata["crs"],
            image_path=destination,
            bands=metadata["bands"],
            bounds=metadata["bounds"],
            preview_path=preview_path,
            file_size_bytes=metadata.get("file_size_bytes"),
            resolution_m=metadata.get("resolution_m"),
            nodata=metadata.get("nodata"),
            north_up=metadata.get("north_up"),
            dtype=metadata.get("dtype"),
            overlay_bounds=overlay_bounds,
        )
    except Exception as error:
        destination.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=500,
            detail=f"Could not save uploaded project metadata: {error}",
        ) from error

    project = get_project(project_id)
    return {
        "message": "GeoTIFF uploaded",
        **_project_payload(project),
    }
