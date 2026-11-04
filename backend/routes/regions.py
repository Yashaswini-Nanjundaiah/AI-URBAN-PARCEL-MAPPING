from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from database.db import get_candidate_regions

import json

router = APIRouter(prefix="/api/runs", tags=["Regions"])


@router.get("/{run_id}/regions")
def get_regions(run_id: int):
    try:
        regions = get_candidate_regions(run_id)

        if regions is None:
            regions = []

        return {
            "run_id": run_id,
            "region_count": len(regions),
            "regions": regions
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not retrieve regions: {str(error)}"
        )


@router.get("/{run_id}/geojson")
def get_regions_geojson(run_id: int):
    try:
        regions = get_candidate_regions(run_id)

        features = []

        for region in regions:
            if isinstance(region, dict):
                geometry_value = region.get("geometry")

                if isinstance(geometry_value, str):
                    geometry_value = json.loads(geometry_value)

                if not geometry_value:
                    continue

                features.append({
                    "type": "Feature",
                    "geometry": geometry_value,
                    "properties": {
                        "region_number": region.get("region_number"),
                        "area_sqm": region.get("area_sqm")
                    }
                })

        return JSONResponse({
            "type": "FeatureCollection",
            "features": features
        })

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Could not generate GeoJSON: {str(error)}"
        )