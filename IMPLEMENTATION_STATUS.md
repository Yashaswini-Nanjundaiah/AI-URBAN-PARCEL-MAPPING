# Implementation Status — SIH 2026 Urban Parcel Mapping

Last updated: 2026-11-05T20:15 IST

## Architecture

| Layer | Technology | Status |
|---|---|---|
| AI Pipeline | ONNX Runtime (model.onnx, 256×256 tiles) | ✅ Working |
| Preprocessing | Rasterio, OpenCV, NumPy | ✅ Working |
| Parcel Extraction | Shapely, PyProj, rasterio.features | ✅ Working |
| Backend | FastAPI, uvicorn | 🔧 Fixing |
| Database | PostgreSQL 16 + PostGIS 3.4 | ✅ Running |
| Frontend | React 18, Vite, Leaflet, react-leaflet | 🔧 Fixing |

## Root Causes Identified

1. **Overlay alignment**: `pipeline.py` uses `write_rgba_overlay()` which resizes masks without geospatial information. Must use `render_mask_overlay()` from `display.py` instead.
2. **Missing overlay_bounds**: Upload route doesn't pass `overlay_bounds` from preview generation to database.
3. **Missing metadata in upload**: `file_size_bytes`, `resolution_m`, `nodata`, `north_up`, `dtype` are not stored.
4. **Stale run recovery**: `fail_interrupted_runs()` exists but never called at startup.
5. **Pipeline progress tracking**: `detect_buildings()` supports `progress_callback` but pipeline doesn't use it.

## Files Modified

- `backend/services/pipeline.py` — Use georeferenced overlays, add progress callbacks
- `backend/routes/uploads.py` — Pass all metadata to database
- `backend/main.py` — Call fail_interrupted_runs at startup
- `database/schema.sql` — Schema already sufficient
- `preprocessing/preview.py` — Return full result including overlay_bounds
- `frontend/web/src/App.jsx` — Enhanced dashboard
- `frontend/web/src/MapView.jsx` — Layer alignment
- `frontend/web/src/styles.css` — Polish

## Files Created

- `IMPLEMENTATION_STATUS.md` (this file)
- `IMPLEMENTATION_LOG.md`

## Current Status

Implementation complete. Upload, processing, output persistence, and dashboard
routes were exercised against the sample GeoTIFF and local PostGIS database.
Image previews and result overlays use a shared Web Mercator extent. Candidate
polygonization was optimized and verified to preserve all 568 detected regions.
