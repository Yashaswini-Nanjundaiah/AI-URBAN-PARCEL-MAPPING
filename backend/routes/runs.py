from fastapi import APIRouter, HTTPException

from database.db import get_processing_run


router = APIRouter(prefix="/api/runs", tags=["Runs"])


@router.get("/{run_id}")
def get_run_status(run_id: int):

    run = get_processing_run(run_id)

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Processing run not found"
        )

    return {
        "run_id": run["id"],
        "project_id": run["project_id"],
        "status": run["status"],
        "building_pixels": run["building_pixels"],
        "candidate_regions": run["candidate_count"],
        "started_at": run["started_at"],
        "completed_at": run["completed_at"]
    }