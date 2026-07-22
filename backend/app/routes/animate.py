"""POST /animate — expand a project's base sprite into an animation (Stage 2).

For each frame we ask Gemini to *edit* the original base sprite (base-anchored,
never chained) into the target pose, then run the same deterministic pipeline as
generate (bg removal -> trim -> quantize if pixel). Frame generation is
partial-failure tolerant: a frame that fails to generate or post-process is
recorded with ``status=failed`` and ``url=None`` rather than aborting the batch.

GET /presets exposes the action table so the frontend can populate its picker.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps import get_provider_registry, get_store
from app.models import (
    AnimateRequest,
    ImageProviderName,
    ViewMode,
    directions_for,
)
from app.services import prompt_builder
from app.services.asset_urls import asset_url
from app.services.sprite_service import (
    AnimationResult,
    ProjectConflictServiceError,
    ProjectNotFoundError,
    SpriteService,
    ValidationServiceError,
)
from app.services.provider_selection import (
    ProviderRegistry,
    ProviderRequirements,
    ProviderUnavailableError,
)
from app.services.image_provider import ProviderCapability
from app.storage.project_store import ProjectStore

router = APIRouter()


@router.get("/presets")
def presets():
    return prompt_builder.list_presets()


@router.get("/animation-options")
def animation_options():
    return [
        {
            "view_mode": view_mode.value,
            "directions": [direction.value for direction in directions_for(view_mode)],
        }
        for view_mode in ViewMode
    ]


@router.get("/image-providers")
def image_providers(
    providers: ProviderRegistry = Depends(get_provider_registry),
):
    return providers.options()


def _animation_payload(result: AnimationResult) -> dict:
    frames = []
    for frame, filename in zip(result.frames, result.frame_filenames):
        payload = frame.model_dump()
        payload["url"] = asset_url(result.project_id, filename) if filename else None
        frames.append(payload)
    return {
        "project_id": result.project_id,
        "action": result.action,
        "fps": result.fps,
        "view_mode": result.view_mode,
        "direction": result.direction,
        "provider": result.project.image_provider,
        "frames": frames,
        "clip_id": result.clip_id,
    }


@router.post("/animate")
def animate(
    req: AnimateRequest,
    request: Request,
    providers: ProviderRegistry = Depends(get_provider_registry),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(req.project_id)
        target_clip = project.clips.get(req.clip_id or project.active_clip_id or "")
        requested = req.provider or (
            target_clip.image_provider if target_clip else project.image_provider
        )
        required = {
            ProviderCapability.EDIT,
            ProviderCapability.IDENTITY_REFERENCE,
        }
        if req.action == "walk" and project.view_mode is ViewMode.SIDE_SCROLLER:
            required.add(ProviderCapability.POSE_REFERENCE)
        if req.seed is not None:
            required.add(ProviderCapability.SEED)
        resolved = providers.resolve(
            requested, ProviderRequirements(frozenset(required))
        )
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).animate(req)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectConflictServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    return _animation_payload(result)


class RegenerateFrameRequest(BaseModel):
    """Regenerate a single frame in-place (FrameStrip escape hatch, spec §4).

    The action/frame-count come from the project's stored animation metadata so
    the per-frame prompt matches the rest of the cycle.
    """

    project_id: str
    index: int = Field(ge=0)
    provider: ImageProviderName | None = None
    clip_id: str | None = None


@router.post("/animate/frame")
def regenerate_frame(
    req: RegenerateFrameRequest,
    request: Request,
    providers: ProviderRegistry = Depends(get_provider_registry),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(req.project_id)
        target_clip = project.clips.get(req.clip_id or project.active_clip_id or "")
        requested = req.provider or (
            target_clip.image_provider if target_clip else project.image_provider
        )
        clip = target_clip
        required = {
            ProviderCapability.EDIT,
            ProviderCapability.IDENTITY_REFERENCE,
        }
        if clip and clip.action == "walk" and project.view_mode is ViewMode.SIDE_SCROLLER:
            required.add(ProviderCapability.POSE_REFERENCE)
        resolved = providers.resolve(
            requested, ProviderRequirements(frozenset(required))
        )
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).regenerate_frame(req.project_id, req.index, clip_id=req.clip_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectConflictServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    payload = result.frame.model_dump()
    payload["url"] = (
        asset_url(result.project_id, result.filename) if result.filename else None
    )
    return payload


class DeleteFrameRequest(BaseModel):
    """Compatibility request that disables a frame without deleting its source."""

    project_id: str
    index: int = Field(ge=0)
    clip_id: str | None = None


@router.delete("/animate/frame")
def delete_frame(
    req: DeleteFrameRequest,
    store: ProjectStore = Depends(get_store),
):
    try:
        result = SpriteService(store=store).delete_frame(
            req.project_id, req.index, clip_id=req.clip_id
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectConflictServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _animation_payload(result)
