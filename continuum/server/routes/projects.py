"""V2 Project endpoints."""

from fastapi import APIRouter, HTTPException

from ...core.service import ContinuumService
from ..models import Project, ProjectCreate

router = APIRouter(prefix="/v2/projects", tags=["projects"])
service = ContinuumService()


@router.post("", response_model=Project)
def create_project(body: ProjectCreate):
    project = service.find_or_create_project(
        name=body.name,
        path=body.path,
        git_remote=body.git_remote,
        metadata=body.metadata,
    )
    return project


@router.get("", response_model=list[Project])
def list_projects():
    return service.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str):
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
