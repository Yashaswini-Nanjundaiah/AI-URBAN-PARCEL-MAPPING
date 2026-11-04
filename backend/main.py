from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database.db import (
    initialize_database,
    create_project,
    get_projects
)

from backend.routes.processing import router as processing_router
from backend.routes.regions import router as regions_router
from backend.routes.runs import router as runs_router


app = FastAPI(
    title="AI-Based Urban Parcel Mapping API",
    description="SIH 2026 - Automated Urban Parcel Mapping",
    version="1.0.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


class ProjectCreate(BaseModel):
    project_name: str
    image_name: str
    image_width: int
    image_height: int
    crs: str


@app.on_event("startup")
def startup():
    initialize_database()


@app.get("/")
def home():
    return {
        "message": "Urban Parcel Mapping API is running"
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy"
    }


@app.post("/api/projects")
def add_project(project: ProjectCreate):

    project_id = create_project(
        project.project_name,
        project.image_name,
        project.image_width,
        project.image_height,
        project.crs
    )

    return {
        "message": "Project created successfully",
        "project_id": project_id
    }


@app.get("/api/projects")
def list_projects():
    return get_projects()


app.include_router(processing_router)
app.include_router(regions_router)
app.include_router(runs_router)