"""POST /generate — text/image -> clean, trimmed sprite (Stage 1).

Pipeline: gemini.generate -> background.remove -> trim.autocrop -> (quantize if
pixel). Accepts multipart form so an optional reference image can be uploaded
alongside the prompt.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from PIL import Image, UnidentifiedImageError

from app.deps import get_gemini_client, get_store
from app.models import Frame, Project, Style
from app.pipeline import background, pixelate, trim
from app.pipeline.trim import EmptyImageError
from app.services.gemini_client import GeminiClient, GeminiError, SafetyBlockedError
from app.storage.project_store import ProjectStore

router = APIRouter()


def _parse_style(value: str) -> Style:
    try:
        return Style(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"unknown style: {value!r}")


@router.post("/generate")
async def generate(
    request: Request,
    prompt: str = Form(...),
    style: str = Form(...),
    reference: UploadFile | None = File(default=None),
    gemini: GeminiClient = Depends(get_gemini_client),
    store: ProjectStore = Depends(get_store),
):
    if not prompt.strip():
        raise HTTPException(status_code=422, detail="prompt must not be empty")
    style_enum = _parse_style(style)

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

    # --- generation ---
    try:
        raw_img = gemini.generate(prompt, style_enum, reference=ref_img)
    except SafetyBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    # --- deterministic post-processing ---
    remover = getattr(request.app.state, "remover", None)
    cut = background.remove(raw_img, remover=remover)
    try:
        sprite = trim.autocrop(cut, padding=0)
    except EmptyImageError:
        raise HTTPException(
            status_code=502,
            detail="generated image was empty after background removal",
        )
    if style_enum is Style.PIXEL:
        sprite = pixelate.quantize(sprite)

    # --- persist ---
    pid = store.create()
    store.save_image(pid, "sprite", sprite)
    sprite_url = f"/projects/{pid}/sprite.png"
    project = Project(
        id=pid,
        prompt=prompt.strip(),
        style=style_enum,
        frames=[Frame(index=0, url=sprite_url)],
    )
    store.write_manifest(pid, project)

    return {"project_id": pid, "sprite_url": sprite_url}
