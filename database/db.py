import json
import os
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


BASE_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://parcel:parcel@127.0.0.1:5432/urban_parcel",
)


def get_connection():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _statement_list(sql_text):
    statements = []
    for chunk in sql_text.split(";"):
        statement = chunk.strip()
        if statement:
            statements.append(statement)
    return statements


def initialize_database():
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        for statement in _statement_list(schema_sql):
            conn.execute(statement)
        version = conn.execute("SELECT PostGIS_Version() AS version").fetchone()
    return version["version"]


def check_database():
    with get_connection() as conn:
        row = conn.execute("SELECT PostGIS_Version() AS version").fetchone()
    return row["version"]


def fail_interrupted_runs():
    """Mark runs left active by a previous server process.

    In-flight work does not survive a restart, so this only runs at startup.
    """
    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE processing_runs
            SET status = 'failed',
                stage = 'failed',
                error_message = 'Processing was interrupted before it finished. Start the run again.',
                completed_at = NOW()
            WHERE status IN ('pending', 'processing')
              AND completed_at IS NULL
            """
        )
    return result.rowcount


def create_project(
    project_name,
    image_name,
    image_width,
    image_height,
    crs,
    image_path=None,
    bands=None,
    bounds=None,
    preview_path=None,
    file_size_bytes=None,
    resolution_m=None,
    nodata=None,
    north_up=None,
    dtype=None,
    overlay_bounds=None,
):
    bounds = bounds or {}
    overlay_bounds = overlay_bounds or {}
    resolution_m = resolution_m or [None, None]
    nodata_text = None if nodata is None else str(nodata)
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO projects (
                project_name,
                image_name,
                image_path,
                preview_path,
                image_width,
                image_height,
                bands,
                crs,
                west,
                south,
                east,
                north,
                file_size_bytes,
                resolution_x,
                resolution_y,
                nodata,
                north_up,
                dtype,
                overlay_west,
                overlay_south,
                overlay_east,
                overlay_north,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            RETURNING id
            """,
            (
                project_name,
                image_name,
                None if image_path is None else str(image_path),
                None if preview_path is None else str(preview_path),
                image_width,
                image_height,
                bands,
                crs,
                bounds.get("west"),
                bounds.get("south"),
                bounds.get("east"),
                bounds.get("north"),
                file_size_bytes,
                resolution_m[0],
                resolution_m[1],
                nodata_text,
                north_up,
                dtype,
                overlay_bounds.get("west"),
                overlay_bounds.get("south"),
                overlay_bounds.get("east"),
                overlay_bounds.get("north"),
            ),
        ).fetchone()
    return row["id"]


def _leaflet_bounds(south, west, north, east):
    if None in (south, west, north, east):
        return None
    return [[float(south), float(west)], [float(north), float(east)]]


def _project_row(row):
    if row is None:
        return None
    data = dict(row)
    data["created_at"] = _iso(data.get("created_at"))
    data["geographic_bounds"] = None
    if data.get("south") is not None and data.get("west") is not None:
        data["geographic_bounds"] = {
            "west": data["west"],
            "south": data["south"],
            "east": data["east"],
            "north": data["north"],
        }
    overlay = _leaflet_bounds(
        data.get("overlay_south"),
        data.get("overlay_west"),
        data.get("overlay_north"),
        data.get("overlay_east"),
    )
    geographic = _leaflet_bounds(
        data.get("south"),
        data.get("west"),
        data.get("north"),
        data.get("east"),
    )
    data["bounds"] = overlay or geographic
    if data.get("resolution_x") is not None and data.get("resolution_y") is not None:
        data["resolution_m"] = [data["resolution_x"], data["resolution_y"]]
    else:
        data["resolution_m"] = None
    return data


def get_projects():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM projects
            ORDER BY id DESC
            """
        ).fetchall()
    return [_project_row(row) for row in rows]


def get_project(project_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM projects
            WHERE id = %s
            """,
            (project_id,),
        ).fetchone()
    return _project_row(row)


def create_processing_run(project_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO processing_runs (
                project_id,
                status,
                started_at
            )
            VALUES (%s, 'pending', NOW())
            RETURNING id
            """,
            (project_id,),
        ).fetchone()
    return row["id"]


def update_processing_status(run_id, status, error_message=None, stage=None):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE processing_runs
            SET status = %s,
                error_message = %s,
                stage = COALESCE(%s, stage)
            WHERE id = %s
            """,
            (status, error_message, stage, run_id),
        )


def update_run_progress(run_id, stage, current=None, total=None):
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE processing_runs
            SET stage = %s,
                progress_current = COALESCE(%s, progress_current),
                progress_total = COALESCE(%s, progress_total)
            WHERE id = %s
              AND status = 'processing'
            """,
            (stage, current, total, run_id),
        )


def mark_run_failed(run_id, error_message):
    message = str(error_message)
    if len(message) > 2000:
        message = message[:2000]
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE processing_runs
            SET status = 'failed',
                stage = 'failed',
                error_message = %s,
                completed_at = NOW()
            WHERE id = %s
              AND status <> 'completed'
            """,
            (message, run_id),
        )


def save_processing_results(
    run_id,
    building_pixels,
    regions,
    building_mask_path,
    candidate_mask_path,
    building_overlay_path,
    candidate_overlay_path,
    geojson_path,
    candidate_count,
):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM candidate_regions WHERE run_id = %s",
            (run_id,),
        )
        conn.execute(
            """
            UPDATE processing_runs
            SET building_pixels = %s,
                candidate_count = %s,
                building_mask_path = %s,
                candidate_mask_path = %s,
                building_overlay_path = %s,
                candidate_overlay_path = %s,
                geojson_path = %s,
                status = 'completed',
                stage = 'completed',
                error_message = NULL,
                completed_at = NOW()
            WHERE id = %s
            """,
            (
                building_pixels,
                candidate_count,
                str(building_mask_path),
                str(candidate_mask_path),
                str(building_overlay_path),
                str(candidate_overlay_path),
                str(geojson_path),
                run_id,
            ),
        )
        for region in regions:
            geometry = region.get("geometry")
            if not geometry:
                continue
            conn.execute(
                """
                INSERT INTO candidate_regions (
                    run_id,
                    region_number,
                    area_sqm,
                    geom
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    ST_MakeValid(
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    )
                )
                """,
                (
                    run_id,
                    region["region_number"],
                    region["area_sqm"],
                    json.dumps(geometry),
                ),
            )


RUN_QUERY = """
    SELECT
        runs.id,
        runs.project_id,
        runs.status,
        runs.building_pixels,
        runs.candidate_count,
        runs.building_mask_path,
        runs.candidate_mask_path,
        runs.building_overlay_path,
        runs.candidate_overlay_path,
        runs.geojson_path,
        runs.error_message,
        runs.stage,
        runs.progress_current,
        runs.progress_total,
        runs.started_at,
        runs.completed_at,
        projects.project_name,
        projects.image_name,
        projects.image_path,
        projects.preview_path,
        projects.image_width,
        projects.image_height,
        projects.bands,
        projects.crs,
        projects.dtype,
        projects.file_size_bytes,
        projects.resolution_x,
        projects.resolution_y,
        projects.nodata,
        projects.north_up,
        projects.west,
        projects.south,
        projects.east,
        projects.north,
        projects.overlay_west,
        projects.overlay_south,
        projects.overlay_east,
        projects.overlay_north,
        projects.created_at,
        (
            SELECT COALESCE(SUM(area_sqm), 0)
            FROM candidate_regions
            WHERE candidate_regions.run_id = runs.id
        ) AS total_area_sqm
    FROM processing_runs AS runs
    JOIN projects ON projects.id = runs.project_id
"""


def _run_row(row):
    if row is None:
        return None
    data = dict(row)
    started = data.get("started_at")
    completed = data.get("completed_at")
    data["duration_seconds"] = None
    if started is not None and completed is not None:
        data["duration_seconds"] = (completed - started).total_seconds()
    data["started_at"] = _iso(started)
    data["completed_at"] = _iso(completed)
    data["created_at"] = _iso(data.get("created_at"))
    data["geographic_bounds"] = None
    if data.get("south") is not None and data.get("west") is not None:
        data["geographic_bounds"] = {
            "west": data["west"],
            "south": data["south"],
            "east": data["east"],
            "north": data["north"],
        }
    overlay = _leaflet_bounds(
        data.get("overlay_south"),
        data.get("overlay_west"),
        data.get("overlay_north"),
        data.get("overlay_east"),
    )
    geographic = _leaflet_bounds(
        data.get("south"),
        data.get("west"),
        data.get("north"),
        data.get("east"),
    )
    data["bounds"] = overlay or geographic
    if data.get("resolution_x") is not None and data.get("resolution_y") is not None:
        data["resolution_m"] = [data["resolution_x"], data["resolution_y"]]
    else:
        data["resolution_m"] = None
    return data


def get_processing_run(run_id):
    with get_connection() as conn:
        row = conn.execute(
            RUN_QUERY + " WHERE runs.id = %s",
            (run_id,),
        ).fetchone()
    return _run_row(row)


def list_processing_runs():
    with get_connection() as conn:
        rows = conn.execute(
            RUN_QUERY + " ORDER BY runs.id DESC"
        ).fetchall()
    return [_run_row(row) for row in rows]


def get_candidate_regions(run_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                region_number,
                area_sqm,
                ST_AsGeoJSON(geom) AS geometry
            FROM candidate_regions
            WHERE run_id = %s
            ORDER BY region_number, id
            """,
            (run_id,),
        ).fetchall()

    regions = []
    for row in rows:
        geometry = row["geometry"]
        if isinstance(geometry, str):
            geometry = json.loads(geometry)
        regions.append(
            {
                "region_number": row["region_number"],
                "area_sqm": row["area_sqm"],
                "geometry": geometry,
            }
        )
    return regions
