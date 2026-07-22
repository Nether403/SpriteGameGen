"""Canonical clip workspace and deterministic repair routes."""
from __future__ import annotations
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps import get_provider_registry, get_store
from app.models import AnimateRequest, Direction, ImageProviderName, LoopMode, RenderSettings
from app.services.asset_urls import asset_url
from app.services.provider_selection import ProviderRegistry, ProviderUnavailableError
from app.services.sprite_service import (
    ProjectConflictServiceError,
    ProjectNotFoundError,
    SpriteService,
    ValidationServiceError,
)
from app.storage.project_store import ProjectStore

router = APIRouter(prefix="/projects/{project_id}")


def _raise(exc: Exception) -> None:
    if isinstance(exc, ProjectNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ProjectConflictServiceError):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ProviderUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc))
    raise HTTPException(status_code=422, detail=str(exc))


def _project_payload(project):
    payload = project.model_dump()
    for clip in payload["clips"].values():
        for frame in clip["frames"]:
            filename = frame.get("rendered_filename")
            frame["url"] = asset_url(project.id, filename) if filename else None
    return payload


@router.get("/clips")
def list_clips(project_id: str, store: ProjectStore = Depends(get_store)):
    try:
        project = store.read_manifest(project_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="project not found") from exc
    return {
        "active_clip_id": project.active_clip_id,
        "clips": _project_payload(project)["clips"],
    }


class CreateClipRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    frames: int | None = Field(default=None, ge=2, le=8)
    fps: int = Field(default=8, ge=1, le=60)
    direction: Direction = Direction.LEFT
    loop_mode: LoopMode = LoopMode.LOOP
    provider: ImageProviderName | None = None
    custom_motion: str | None = Field(default=None, min_length=1, max_length=2000)
    first_pose: str | None = Field(default=None, max_length=1000)
    last_pose: str | None = Field(default=None, max_length=1000)


@router.post("/clips")
def create_clip(
    project_id: str,
    body: CreateClipRequest,
    request: Request,
    providers: ProviderRegistry = Depends(get_provider_registry),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(project_id)
        resolved = providers.resolve(body.provider or project.image_provider)
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).animate(
            AnimateRequest(
                project_id=project_id,
                clip_id=uuid.uuid4().hex[:16],
                action=body.action,
                clip_name=body.name,
                frames=body.frames,
                fps=body.fps,
                direction=body.direction,
                loop_mode=body.loop_mode,
                custom_motion=body.custom_motion,
                first_pose=body.first_pose,
                last_pose=body.last_pose,
            )
        )
        return _project_payload(result.project)
    except (ProjectNotFoundError, ProjectConflictServiceError, ProviderUnavailableError, ValidationServiceError, FileNotFoundError, ValueError) as exc:
        _raise(exc)


class UpdateClipRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    fps: int | None = Field(default=None, ge=1, le=60)
    loop_mode: LoopMode | None = None
    loop_start: int | None = Field(default=None, ge=0)
    loop_end: int | None = Field(default=None, ge=0)
    enabled: bool | None = None


@router.patch("/clips/{clip_id}")
def update_clip(project_id: str, clip_id: str, body: UpdateClipRequest, store: ProjectStore = Depends(get_store)):
    try:
        result = SpriteService(store=store).update_clip(
            project_id, clip_id, **body.model_dump()
        )
        return _project_payload(result.project)
    except (ProjectNotFoundError, ProjectConflictServiceError, ValidationServiceError, ValueError) as exc:
        _raise(exc)


@router.post("/clips/{clip_id}/select")
def select_clip(project_id: str, clip_id: str, store: ProjectStore = Depends(get_store)):
    try:
        return _project_payload(SpriteService(store=store).select_clip(project_id, clip_id).project)
    except (ProjectNotFoundError, ProjectConflictServiceError, ValidationServiceError) as exc:
        _raise(exc)


@router.delete("/clips/{clip_id}")
def delete_clip(project_id: str, clip_id: str, store: ProjectStore = Depends(get_store)):
    try:
        return _project_payload(SpriteService(store=store).delete_clip(project_id, clip_id).project)
    except (ProjectNotFoundError, ProjectConflictServiceError, ValidationServiceError) as exc:
        _raise(exc)


class FrameAdjustmentRequest(BaseModel):
    enabled: bool | None = None
    nudge_x: int | None = Field(default=None, ge=-4096, le=4096)
    nudge_y: int | None = Field(default=None, ge=-4096, le=4096)
    horizontal_flip: bool | None = None
    reset: bool = False


@router.patch("/clips/{clip_id}/frames/{index}")
def adjust_frame(
    project_id: str,
    clip_id: str,
    index: int,
    body: FrameAdjustmentRequest,
    store: ProjectStore = Depends(get_store),
):
    try:
        result = SpriteService(store=store).set_frame_adjustment(
            project_id, index, clip_id=clip_id, **body.model_dump()
        )
        payload = result.frame.model_dump()
        payload["url"] = (
            asset_url(project_id, result.filename) if result.filename else None
        )
        return payload
    except (ProjectNotFoundError, ProjectConflictServiceError, ValidationServiceError, FileNotFoundError) as exc:
        _raise(exc)


@router.put("/render-settings")
def set_render_settings(
    project_id: str,
    body: RenderSettings,
    store: ProjectStore = Depends(get_store),
):
    try:
        return _project_payload(
            SpriteService(store=store).set_render_settings(project_id, body)
        )
    except (ProjectNotFoundError, ProjectConflictServiceError, ValidationServiceError, FileNotFoundError, ValueError) as exc:
        _raise(exc)
