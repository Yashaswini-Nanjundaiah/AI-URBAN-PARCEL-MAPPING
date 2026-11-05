import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from backend.services.pipeline import MODEL_PATH, run_pipeline
from database.db import create_processing_run, get_project, update_processing_status


router = APIRouter(prefix="/api", tags=["Processing"])
logger = logging.getLogger(__name__)


def _execute_run(run_id, image_path):
    try:
        run_pipeline(run_id, image_path=image_path)
    except Exception:
        logger.exception("Processing run %s failed", run_id)


@router.post("/projects/{project_id}/process")
def process_project(project_id: int, background_tasks: BackgroundTasks):
    project = get_project(project_id)

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    image_path = project.get("image_path")
    if not image_path:
        raise HTTPException(
            status_code=400,
            detail="This project has no uploaded GeoTIFF to process.",
        )

    if not Path(image_path).exists():
        raise HTTPException(
            status_code=404,
            detail="The uploaded GeoTIFF is no longer available on disk.",
        )

    if not MODEL_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="ONNX model weights were not found.",
        )

    run_id = create_processing_run(project_id)
    update_processing_status(run_id, "processing")
    background_tasks.add_task(_execute_run, run_id, image_path)

    return {
        "message": "Processing started",
        "run_id": run_id,
        "project_id": project_id,
        "status": "processing",
        "image_name": project["image_name"],
    }
