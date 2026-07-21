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

from app.deps import get_azure_image_provider, get_gemini_client, get_store
from app.models import (
    AnimateRequest,
    ImageProviderName,
    ViewMode,
    directions_for,
)
from app.services.azure_image_provider import AzureImageProvider
from app.services import prompt_builder
from app.services.asset_urls import asset_url
from app.services.gemini_client import GeminiClient
from app.services.sprite_service import (
    AnimationResult,
    ProjectNotFoundError,
    SpriteService,
    ValidationServiceError,
)
from app.services.provider_selection import (
    ProviderUnavailableError,
    list_provider_options,
    resolve_image_provider,
)
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
    azure: AzureImageProvider | None = Depends(get_azure_image_provider),
):
    return list_provider_options(azure_available=azure is not None)


def _animation_payload(result: AnimationResult) -> dict:
    frames = [
        frame.model_copy(
            update={
                "url": (
                    asset_url(result.project_id, filename) if filename else None
                )
            }
        ).model_dump()
        for frame, filename in zip(result.frames, result.frame_filenames)
    ]
    return {
        "project_id": result.project_id,
        "action": result.action,
        "fps": result.fps,
        "view_mode": result.view_mode,
        "direction": result.direction,
        "provider": result.project.image_provider,
        "frames": frames,
    }


@router.post("/animate")
def animate(
    req: AnimateRequest,
    request: Request,
    gemini: GeminiClient = Depends(get_gemini_client),
    azure: AzureImageProvider | None = Depends(get_azure_image_provider),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(req.project_id)
        requested = req.provider or project.image_provider
        resolved = resolve_image_provider(requested, gemini, azure)
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=gemini,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).animate(req)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
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


@router.post("/animate/frame")
def regenerate_frame(
    req: RegenerateFrameRequest,
    request: Request,
    gemini: GeminiClient = Depends(get_gemini_client),
    azure: AzureImageProvider | None = Depends(get_azure_image_provider),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(req.project_id)
        requested = req.provider or project.image_provider
        resolved = resolve_image_provider(requested, gemini, azure)
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=gemini,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).regenerate_frame(req.project_id, req.index)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")
    return result.frame.model_copy(
        update={
            "url": asset_url(result.project_id, result.filename)
            if result.filename
            else None
        }
    ).model_dump()


class DeleteFrameRequest(BaseModel):
    """Delete a single frame and re-index the remainder (FrameStrip escape hatch).

    Frames persist as ``frame_{index}.png`` and the export route assumes manifest
    indices match those filenames, so deleting frame *i* renumbers every later
    frame down by one on disk as well as in the manifest.
    """

    project_id: str
    index: int = Field(ge=0)


@router.delete("/animate/frame")
def delete_frame(
    req: DeleteFrameRequest,
    store: ProjectStore = Depends(get_store),
):
    try:
        result = SpriteService(store=store).delete_frame(req.project_id, req.index)
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _animation_payload(result)
