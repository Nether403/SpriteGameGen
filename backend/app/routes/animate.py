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
from PIL import Image

from app.deps import get_gemini_client, get_store
from app.models import AnimateRequest, Frame, FrameStatus, Style
from app.pipeline import background, pixelate, trim
from app.pipeline.trim import DegenerateBBoxError, EmptyImageError
from app.services import prompt_builder
from app.services.gemini_client import GeminiClient, GeminiError, SafetyBlockedError
from app.storage.project_store import ProjectStore

router = APIRouter()


@router.get("/presets")
def presets():
    return prompt_builder.list_presets()


def _resolve_frame_count(preset: dict, requested: int | None) -> int:
    """Clamp the requested frame count into the preset's [min, max] window, or
    fall back to the preset default when unspecified."""
    if requested is None:
        return preset["default_frames"]
    return max(preset["min_frames"], min(preset["max_frames"], requested))


@router.post("/animate")
def animate(
    req: AnimateRequest,
    request: Request,
    gemini: GeminiClient = Depends(get_gemini_client),
    store: ProjectStore = Depends(get_store),
):
    try:
        preset = prompt_builder.get_preset(req.action)
    except KeyError:
        raise HTTPException(status_code=422, detail=f"unknown action: {req.action!r}")

    try:
        project = store.read_manifest(req.project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")

    try:
        base = store.load_image(req.project_id, "sprite")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project has no base sprite")

    total = _resolve_frame_count(preset, req.frames)
    remover = getattr(request.app.state, "remover", None)

    # Phase 1: generate + background-remove each frame. Frames are NOT cropped
    # here — cropping happens after all frames exist so they can share one
    # bounding box (anti-jitter). Failures are recorded and skipped.
    cut_by_index: dict[int, Image.Image] = {}
    failed: set[int] = set()
    for index in range(total):
        prompt = prompt_builder.frame_prompt(req.action, index, total)
        try:
            edited = gemini.edit(base, prompt)
            cut_by_index[index] = background.remove(edited, remover=remover)
        except (GeminiError, SafetyBlockedError):
            failed.add(index)

    # Phase 2: shared-bbox alignment across the successful frames only, so the
    # character never resizes or shifts between frames.
    ok_indices = sorted(cut_by_index)
    aligned_by_index: dict[int, Image.Image] = {}
    if ok_indices:
        ordered = [cut_by_index[i] for i in ok_indices]
        try:
            box = trim.shared_bbox(ordered)
            aligned = trim.align_to_bbox(ordered, box, padding=0)
        except (EmptyImageError, DegenerateBBoxError):
            # No usable content in any frame — treat them all as failures.
            failed.update(ok_indices)
            aligned = []
        for i, img in zip(ok_indices, aligned):
            if project.style is Style.PIXEL:
                img = pixelate.quantize(img)
            aligned_by_index[i] = img

    # Phase 3: persist and build the frame manifest, preserving frame order.
    frames: list[Frame] = []
    for index in range(total):
        if index in aligned_by_index:
            name = f"frame_{index}"
            store.save_image(req.project_id, name, aligned_by_index[index])
            frames.append(
                Frame(
                    index=index,
                    url=f"/projects/{req.project_id}/{name}.png",
                    status=FrameStatus.OK,
                )
            )
        else:
            frames.append(Frame(index=index, url=None, status=FrameStatus.FAILED))

    project.frames = frames
    project.action = req.action
    project.fps = req.fps
    store.write_manifest(req.project_id, project)

    return {
        "project_id": req.project_id,
        "action": req.action,
        "fps": req.fps,
        "frames": [f.model_dump() for f in frames],
    }
