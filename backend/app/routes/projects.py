"""Project catalog, resume detail, and deletion routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_store
from app.models import ProjectDetail, ProjectSummary
from app.services.asset_urls import asset_url
from app.services.sprite_service import (
    ProjectNotFoundError,
    ProjectUnavailableError,
    SpriteService,
)
from app.storage.project_store import ProjectStore

router = APIRouter()


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(store: ProjectStore = Depends(get_store)):
    return [
        ProjectSummary(
            **summary.model_dump(exclude={"thumbnail_filename"}),
            thumbnail_url=(
                asset_url(summary.id, summary.thumbnail_filename)
                if summary.thumbnail_filename
                else None
            ),
        )
        for summary in SpriteService(store=store).list_projects()
    ]


@router.get("/projects/{project_id}")
def get_project(project_id: str, store: ProjectStore = Depends(get_store)):
    try:
        result = SpriteService(store=store).get_project(project_id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    except ProjectUnavailableError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )
    payload = result.project.model_dump()
    for clip in payload["clips"].values():
        for frame in clip["frames"]:
            filename = frame.get("rendered_filename")
            frame["url"] = asset_url(project_id, filename) if filename else None
    frames = []
    for frame, filename in zip(result.project.frames, result.frame_filenames):
        frame_payload = frame.model_dump()
        frame_payload["url"] = asset_url(project_id, filename) if filename else None
        frames.append(frame_payload)
    payload.update(
        {
            "frames": frames,
            "action": result.project.action,
            "fps": result.project.fps,
            "sprite_url": asset_url(project_id, result.sprite_filename),
            "health": result.health,
            "resume_available": True,
        }
    )
    return payload


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, store: ProjectStore = Depends(get_store)):
    try:
        store.get_project_record(project_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="project not found")
    store.delete_project(project_id)
    return {"deleted": project_id}
