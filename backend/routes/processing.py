from fastapi import APIRouter, HTTPException
from database.db import create_processing_run, get_project
from backend.services.pipeline import run_pipeline

router = APIRouter(prefix="/api", tags=["Processing"])


@router.post("/projects/{project_id}/process")
def process_project(project_id: int):

    project = get_project(project_id)

    if not project:
        raise HTTPException(
            status_code=404,
            detail="Project not found"
        )

    run_id = create_processing_run(project_id)

    try:
        result = run_pipeline(run_id)

        return {
            "message": "Processing completed",
            **result
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=str(error)
        )