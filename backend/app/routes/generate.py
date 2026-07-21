"""POST /generate — text/image -> clean, trimmed sprite (Stage 1).

Pipeline: gemini.generate -> background.remove -> trim.autocrop -> (quantize if
pixel). Accepts multipart form so an optional reference image can be uploaded
alongside the prompt.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from app.deps import get_azure_image_provider, get_gemini_client, get_store
from app.models import Direction, ImageProviderName, Style, ViewMode, validate_direction
from app.services.azure_image_provider import AzureImageProvider
from app.services.gemini_client import GeminiClient
from app.services.asset_urls import asset_url
from app.services.sprite_service import (
    GenerateSpriteInput,
    SafetyServiceError,
    SpriteService,
    UpstreamServiceError,
)
from app.services.provider_selection import (
    ProviderUnavailableError,
    resolve_image_provider,
)
from app.storage.project_store import ProjectStore

router = APIRouter()


def _parse_style(value: str) -> Style:
    try:
        return Style(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown style: {value!r}")


def _parse_camera(view_mode: str, direction: str) -> tuple[ViewMode, Direction]:
    try:
        mode_enum = ViewMode(view_mode)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"unknown view mode: {view_mode!r}"
        )
    try:
        direction_enum = Direction(direction)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"unknown direction: {direction!r}"
        )
    try:
        validate_direction(mode_enum, direction_enum)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return mode_enum, direction_enum


@router.post("/generate")
async def generate(
    request: Request,
    prompt: str = Form(...),
    style: str = Form(...),
    enhanced_prompt: str | None = Form(default=None),
    view_mode: str = Form(default=ViewMode.SIDE_SCROLLER.value),
    direction: str = Form(default=Direction.LEFT.value),
    provider: str = Form(default=ImageProviderName.GEMINI.value),
    reference: UploadFile | None = File(default=None),
    gemini: GeminiClient = Depends(get_gemini_client),
    azure: AzureImageProvider | None = Depends(get_azure_image_provider),
    store: ProjectStore = Depends(get_store),
):
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt must not be empty")
    style_enum = _parse_style(style)
    mode_enum, direction_enum = _parse_camera(view_mode, direction)
    try:
        provider_enum = ImageProviderName(provider)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown provider: {provider!r}")
    try:
        resolved = resolve_image_provider(provider_enum, gemini, azure)
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    accepted_prompt = enhanced_prompt.strip() if enhanced_prompt else None
    if accepted_prompt is not None and len(accepted_prompt) > 2000:
        raise HTTPException(
            status_code=422, detail="enhanced prompt must be at most 2000 characters"
        )

    ref_img: Image.Image | None = None
    if reference is not None:
        raw = await reference.read()
        max_bytes = getattr(request.app.state, "max_upload_bytes", 10 * 1024 * 1024)
        if len(raw) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"reference image exceeds {max_bytes} bytes",
            )
        try:
            ref_img = Image.open(io.BytesIO(raw)).convert("RGBA")
        except UnidentifiedImageError:
            raise HTTPException(status_code=422, detail="reference is not a valid image")

    try:
        result = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=gemini,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        ).generate_sprite(
            GenerateSpriteInput(
                prompt=prompt,
                enhanced_prompt=accepted_prompt,
                style=style_enum,
                view_mode=mode_enum,
                direction=direction_enum,
                reference=ref_img,
            )
        )
    except SafetyServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "project_id": result.project_id,
        "sprite_url": asset_url(result.project_id, result.sprite_filename),
        "prompt_source": result.project.prompt_source,
        "provider": result.project.image_provider,
    }
