"""POST /generate — text/image -> clean, trimmed sprite (Stage 1).

Pipeline: gemini.generate -> background.remove -> trim.autocrop -> (quantize if
pixel). Accepts multipart form so an optional reference image can be uploaded
alongside the prompt.
"""
from __future__ import annotations

import io
import warnings
from functools import partial

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from app.deps import get_provider_registry, get_store
from app.models import (
    Direction,
    ImageProviderName,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PROMPT_LENGTH,
    Style,
    ViewMode,
    validate_direction,
)
from app.services.asset_urls import asset_url
from app.services.sprite_service import (
    GenerateSpriteInput,
    OperationControl,
    SafetyServiceError,
    SpriteService,
    UpstreamServiceError,
)
from app.services.provider_selection import (
    ProviderRegistry,
    ProviderUnavailableError,
)
from app.storage.project_store import ProjectStore

router = APIRouter()


def _check_reference_size(image: Image.Image) -> None:
    width, height = image.size
    if (
        width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "reference image dimensions exceed the decoded image limit"
            ),
        )


def _decode_reference(raw: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as candidate:
                _check_reference_size(candidate)
                candidate.verify()
            with Image.open(io.BytesIO(raw)) as candidate:
                _check_reference_size(candidate)
                candidate.load()
                return candidate.convert("RGBA")
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(
            status_code=413, detail="reference image exceeds the decoded image limit"
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(status_code=422, detail="reference is not a valid image")


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
    prompt: str = Form(..., min_length=1, max_length=MAX_PROMPT_LENGTH),
    style: str = Form(...),
    enhanced_prompt: str | None = Form(default=None, max_length=MAX_PROMPT_LENGTH),
    view_mode: str = Form(default=ViewMode.SIDE_SCROLLER.value),
    direction: str = Form(default=Direction.LEFT.value),
    provider: str = Form(default=ImageProviderName.GEMINI.value),
    reference: UploadFile | None = File(default=None),
    providers: ProviderRegistry = Depends(get_provider_registry),
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
        resolved = providers.resolve(provider_enum)
    except ProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    accepted_prompt = enhanced_prompt.strip() if enhanced_prompt else None

    ref_img: Image.Image | None = None
    if reference is not None:
        max_bytes = getattr(request.app.state, "max_upload_bytes", 10 * 1024 * 1024)
        raw = await reference.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"reference image exceeds {max_bytes} bytes",
            )
        ref_img = _decode_reference(raw)

    try:
        service = SpriteService(
            store=store,
            image_provider=resolved.provider,
            prompt_enhancer=providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=getattr(request.app.state, "remover", None),
        )
        operation = OperationControl()
        result = await anyio.to_thread.run_sync(
            partial(
                service.generate_sprite,
                control=operation,
                request=GenerateSpriteInput(
                    prompt=prompt,
                    enhanced_prompt=accepted_prompt,
                    style=style_enum,
                    view_mode=mode_enum,
                    direction=direction_enum,
                    reference=ref_img,
                ),
            ),
            abandon_on_cancel=True,
        )
    except anyio.get_cancelled_exc_class():
        operation.cancel()
        raise
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
