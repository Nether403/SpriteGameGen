"""GET /projects (list) and DELETE /projects/{id}."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import get_store
from app.models import Project
from app.storage.project_store import ProjectStore

router = APIRouter()


@router.get("/projects", response_model=list[Project])
def list_projects(store: ProjectStore = Depends(get_store)):
    return store.list_projects()


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, store: ProjectStore = Depends(get_store)):
    store.delete_project(project_id)
    return {"deleted": project_id}
