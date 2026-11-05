CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    project_name TEXT NOT NULL,
    image_name TEXT NOT NULL,
    image_path TEXT,
    preview_path TEXT,
    image_width INTEGER,
    image_height INTEGER,
    bands INTEGER,
    crs TEXT,
    west DOUBLE PRECISION,
    south DOUBLE PRECISION,
    east DOUBLE PRECISION,
    north DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processing_runs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    status TEXT NOT NULL DEFAULT 'pending',
    building_pixels INTEGER DEFAULT 0,
    candidate_count INTEGER DEFAULT 0,
    building_mask_path TEXT,
    candidate_mask_path TEXT,
    building_overlay_path TEXT,
    candidate_overlay_path TEXT,
    geojson_path TEXT,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS candidate_regions (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES processing_runs(id) ON DELETE CASCADE,
    region_number INTEGER NOT NULL,
    area_sqm DOUBLE PRECISION,
    geom geometry(Geometry, 4326)
);

CREATE INDEX IF NOT EXISTS candidate_regions_geom_idx
    ON candidate_regions USING GIST (geom);

CREATE INDEX IF NOT EXISTS processing_runs_project_idx
    ON processing_runs (project_id);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS file_size_bytes BIGINT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS resolution_x DOUBLE PRECISION;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS resolution_y DOUBLE PRECISION;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS nodata TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS north_up BOOLEAN;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS dtype TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS overlay_west DOUBLE PRECISION;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS overlay_south DOUBLE PRECISION;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS overlay_east DOUBLE PRECISION;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS overlay_north DOUBLE PRECISION;

ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS stage TEXT;
ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS progress_current INTEGER;
ALTER TABLE processing_runs ADD COLUMN IF NOT EXISTS progress_total INTEGER;
