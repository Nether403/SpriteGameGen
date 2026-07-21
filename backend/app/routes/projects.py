"""Project catalog, resume detail, and deletion routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_store
from app.models import Frame, FrameStatus, ProjectDetail, ProjectHealth, ProjectSummary
from app.services.asset_urls import asset_url
from app.storage.project_store import ProjectRecord, ProjectStore

router = APIRouter()


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(store: ProjectStore = Depends(get_store)):
    return [_summary(record) for record in store.list_project_records()]


def _frame_url(record: ProjectRecord, frame: Frame) -> str | None:
    if frame.status is FrameStatus.FAILED or record.project is None:
        return None
    name = "sprite" if record.project.action is None else f"frame_{frame.index}"
    return asset_url(record.id, f"{name}.png")


def _summary(record: ProjectRecord) -> ProjectSummary:
    project = record.project
    frames = project.frames if project is not None else []
    return ProjectSummary(
        id=record.id,
        prompt_preview=project.prompt[:120] if project is not None else None,
        style=project.style if project is not None else None,
        thumbnail_url=asset_url(record.id, "sprite.png") if record.has_sprite else None,
        action=project.action if project is not None else None,
        fps=project.fps if project is not None else None,
        frame_count=len(frames),
        ok_count=sum(frame.status is FrameStatus.OK for frame in frames),
        failed_count=sum(frame.status is FrameStatus.FAILED for frame in frames),
        created_at=project.created_at if project is not None else record.updated_at,
        updated_at=record.updated_at,
        health=record.health,
        resume_available=record.health is ProjectHealth.READY,
    )


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str, store: ProjectStore = Depends(get_store)):
    try:
        record = store.get_project_record(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found")
    if record.project is None or record.health is not ProjectHealth.READY:
        raise HTTPException(
            status_code=409,
            detail=f"project is {record.health.value} and cannot be resumed",
        )
    project = record.project.model_copy(
        update={
            "frames": [
                frame.model_copy(update={"url": _frame_url(record, frame)})
                for frame in record.project.frames
            ]
        }
    )
    return ProjectDetail(
        **project.model_dump(),
        sprite_url=asset_url(project_id, "sprite.png"),
        health=record.health,
        resume_available=True,
    )


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, store: ProjectStore = Depends(get_store)):
    try:
        store.get_project_record(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found")
    store.delete_project(project_id)
    return {"deleted": project_id}
