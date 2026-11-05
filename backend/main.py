from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.routes.processing import router as processing_router
from backend.routes.regions import router as regions_router
from backend.routes.runs import router as runs_router
from backend.routes.uploads import router as uploads_router
from backend.services.pipeline import MODEL_PATH
from database.db import (
    check_database,
    create_project,
    fail_interrupted_runs,
    get_project,
    get_projects,
    initialize_database,
)


BASE_DIR = Path(__file__).resolve().parents[1]


@asynccontextmanager
async def lifespan(_app):
    initialize_database()
    fail_interrupted_runs()
    yield


app = FastAPI(
    title="AI-Based Urban Parcel Mapping API",
    description="SIH 2026 - Automated Urban Parcel Mapping",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProjectCreate(BaseModel):
    project_name: str
    image_name: str
    image_width: int
    image_height: int
    crs: str


def _stored_preview(project):
    raw_path = project.get("preview_path")
    if not raw_path:
        raise HTTPException(status_code=404, detail="Preview is not available.")

    path = Path(raw_path).resolve()
    allowed_roots = (
        (BASE_DIR / "outputs").resolve(),
        (BASE_DIR / "dataset").resolve(),
    )
    if not any(path.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(status_code=400, detail="Preview path is outside the project.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Preview file was not found.")
    return path


@app.get("/")
def home():
    return {"message": "Urban Parcel Mapping API is running"}


@app.get("/api/health")
def health():
    database_version = None
    database_ok = False
    database_error = None

    try:
        database_version = check_database()
        database_ok = True
    except Exception as error:
        database_error = str(error)

    return {
        "status": "healthy" if database_ok and MODEL_PATH.exists() else "degraded",
        "database": database_ok,
        "postgis": database_version,
        "database_error": database_error,
        "model": MODEL_PATH.exists(),
    }


@app.post("/api/projects")
def add_project(project: ProjectCreate):
    project_id = create_project(
        project.project_name,
        project.image_name,
        project.image_width,
        project.image_height,
        project.crs,
    )
    return {
        "message": "Project created successfully",
        "project_id": project_id,
    }


@app.get("/api/projects")
def list_projects():
    projects = []
    for project in get_projects():
        projects.append(
            {
                "project_id": project["id"],
                "project_name": project["project_name"],
                "image_name": project["image_name"],
                "width": project["image_width"],
                "height": project["image_height"],
                "bands": project["bands"],
                "crs": project["crs"],
                "bounds": project["bounds"],
                "preview_url": f"/api/projects/{project['id']}/preview",
                "created_at": project["created_at"],
            }
        )
    return projects


@app.get("/api/projects/{project_id}")
def read_project(project_id: int):
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "project_id": project["id"],
        "project_name": project["project_name"],
        "image_name": project["image_name"],
        "width": project["image_width"],
        "height": project["image_height"],
        "bands": project["bands"],
        "crs": project["crs"],
        "bounds": project["bounds"],
        "preview_url": f"/api/projects/{project_id}/preview",
        "created_at": project["created_at"],
    }


@app.get("/api/projects/{project_id}/preview")
def project_preview(project_id: int):
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return FileResponse(_stored_preview(project), media_type="image/png")


app.include_router(uploads_router)
app.include_router(processing_router)
app.include_router(regions_router)
app.include_router(runs_router)
