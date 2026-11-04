import sqlite3
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "database" / "urban_mapping.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT NOT NULL,
                image_name TEXT NOT NULL,
                image_width INTEGER,
                image_height INTEGER,
                crs TEXT,
                created_at TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS processing_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                building_pixels INTEGER DEFAULT 0,
                candidate_count INTEGER DEFAULT 0,
                started_at TEXT,
                completed_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidate_regions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                region_number INTEGER,
                area_sqm REAL,
                geometry_json TEXT,
                FOREIGN KEY(run_id) REFERENCES processing_runs(id)
            )
        """)


def create_project(
    project_name,
    image_name,
    image_width,
    image_height,
    crs
):
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO projects (
                project_name,
                image_name,
                image_width,
                image_height,
                crs,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            project_name,
            image_name,
            image_width,
            image_height,
            crs,
            datetime.now().isoformat()
        ))

        return cursor.lastrowid


def get_projects():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM projects
            ORDER BY id DESC
        """).fetchall()

        return [dict(row) for row in rows]


def get_project(project_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM projects WHERE id = ?
        """, (project_id,)).fetchone()

        return dict(row) if row else None


def create_processing_run(project_id):
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO processing_runs (
                project_id,
                status,
                started_at
            )
            VALUES (?, 'pending', ?)
        """, (project_id, datetime.now().isoformat()))

        return cursor.lastrowid


def update_processing_status(run_id, status):
    with get_connection() as conn:
        conn.execute("""
            UPDATE processing_runs
            SET status = ?
            WHERE id = ?
        """, (status, run_id))


def get_processing_run(run_id):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM processing_runs
            WHERE id = ?
        """, (run_id,)).fetchone()

        return dict(row) if row else None


def save_processing_results(run_id, building_pixels, regions):
    with get_connection() as conn:
        conn.execute("""
            UPDATE processing_runs
            SET building_pixels = ?,
                candidate_count = ?,
                completed_at = ?
            WHERE id = ?
        """, (
            building_pixels,
            len(regions),
            datetime.now().isoformat(),
            run_id
        ))

        for region in regions:
            conn.execute("""
                INSERT INTO candidate_regions (
                    run_id,
                    region_number,
                    area_sqm,
                    geometry_json
                )
                VALUES (?, ?, ?, ?)
            """, (
                run_id,
                region["region_number"],
                region["area_sqm"],
                region["geometry"]
            ))


def get_candidate_regions(run_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT region_number, area_sqm, geometry_json
            FROM candidate_regions
            WHERE run_id = ?
            ORDER BY region_number
        """, (run_id,)).fetchall()

        return [
            {
                "region_number": row["region_number"],
                "area_sqm": row["area_sqm"],
                "geometry": row["geometry_json"]
            }
            for row in rows
        ]