import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from database.db import get_candidate_regions, get_processing_run, list_processing_runs


router = APIRouter(prefix="/api/runs", tags=["Runs"])

BASE_DIR = Path(__file__).resolve().parents[2]


def _public_run(run):
    completed = run["status"] == "completed"
    return {
        "run_id": run["id"],
        "project_id": run["project_id"],
        "project_name": run["project_name"],
        "image_name": run["image_name"],
        "status": run["status"],
        "building_pixels": run["building_pixels"],
        "candidate_regions": run["candidate_count"],
        "width": run["image_width"],
        "height": run["image_height"],
        "bands": run["bands"],
        "crs": run["crs"],
        "bounds": run["bounds"],
        "error_message": run["error_message"],
        "stage": run["stage"],
        "progress_current": run["progress_current"],
        "progress_total": run["progress_total"],
        "duration_seconds": run["duration_seconds"],
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "preview_url": f"/api/projects/{run['project_id']}/preview",
        "building_overlay_url": (
            f"/api/runs/{run['id']}/files/building-overlay" if completed else None
        ),
        "candidate_overlay_url": (
            f"/api/runs/{run['id']}/files/candidate-overlay" if completed else None
        ),
        "geojson_url": f"/api/runs/{run['id']}/geojson",
        "download_geojson_url": f"/api/runs/{run['id']}/download/geojson",
        "download_building_mask_url": f"/api/runs/{run['id']}/download/building-mask",
        "download_candidate_mask_url": f"/api/runs/{run['id']}/download/candidate-mask",
    }


def _stored_file(run, key):
    raw_path = run.get(key)
    if not raw_path:
        raise HTTPException(status_code=404, detail="Output file is not available.")

    path = Path(raw_path).resolve()
    allowed = (BASE_DIR / "outputs").resolve()
    if not path.is_relative_to(allowed):
        raise HTTPException(status_code=400, detail="Output path is outside the project.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file was not found on disk.")
    return path


def _require_run(run_id):
    run = get_processing_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Processing run not found")
    return run


@router.get("")
def list_runs():
    return [_public_run(run) for run in list_processing_runs()]


@router.get("/{run_id}")
def get_run_status(run_id: int):
    return _public_run(_require_run(run_id))


@router.get("/{run_id}/files/building-overlay")
def building_overlay(run_id: int):
    run = _require_run(run_id)
    return FileResponse(_stored_file(run, "building_overlay_path"), media_type="image/png")


@router.get("/{run_id}/files/candidate-overlay")
def candidate_overlay(run_id: int):
    run = _require_run(run_id)
    return FileResponse(_stored_file(run, "candidate_overlay_path"), media_type="image/png")


@router.get("/{run_id}/download/building-mask")
def download_building_mask(run_id: int):
    run = _require_run(run_id)
    path = _stored_file(run, "building_mask_path")
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"building_mask_run_{run_id}.png",
    )


@router.get("/{run_id}/download/candidate-mask")
def download_candidate_mask(run_id: int):
    run = _require_run(run_id)
    path = _stored_file(run, "candidate_mask_path")
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"candidate_regions_run_{run_id}.png",
    )


def _feature_collection(run_id):
    features = []
    for region in get_candidate_regions(run_id):
        geometry = region.get("geometry")
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        if not geometry:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "region_number": region.get("region_number"),
                    "area_sqm": region.get("area_sqm"),
                    "classification": "candidate_open_region",
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/{run_id}/download/geojson")
def download_geojson(run_id: int):
    _require_run(run_id)
    payload = _feature_collection(run_id)
    return Response(
        content=json.dumps(payload),
        media_type="application/geo+json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="candidate_regions_run_{run_id}.geojson"'
            )
        },
    )
