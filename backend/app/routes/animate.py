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
from pydantic import BaseModel, Field

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


class RegenerateFrameRequest(BaseModel):
    """Regenerate a single frame in-place (FrameStrip escape hatch, spec §4).

    The action/frame-count come from the project's stored animation metadata so
    the per-frame prompt matches the rest of the cycle.
    """

    project_id: str
    index: int = Field(ge=0)


def _fit_to_size(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Center ``img``'s content on a transparent canvas of ``size``.

    A regenerated frame is trimmed to its own content, then placed on a canvas
    matching the sibling frames so playback keeps the shared-bbox size (no
    resize/jitter). Content larger than the canvas is downscaled to fit.
    """
    cropped = trim.autocrop(img, padding=0)
    cw, ch = cropped.size
    tw, th = size
    if cw > tw or ch > th:
        scale = min(tw / cw, th / ch)
        cropped = cropped.resize(
            (max(1, int(cw * scale)), max(1, int(ch * scale))), Image.LANCZOS
        )
        cw, ch = cropped.size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(cropped, ((tw - cw) // 2, (th - ch) // 2))
    return canvas


@router.post("/animate/frame")
def regenerate_frame(
    req: RegenerateFrameRequest,
    request: Request,
    gemini: GeminiClient = Depends(get_gemini_client),
    store: ProjectStore = Depends(get_store),
):
    try:
        project = store.read_manifest(req.project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")

    if project.action is None:
        raise HTTPException(status_code=422, detail="project has not been animated")

    total = len(project.frames)
    if not (0 <= req.index < total):
        raise HTTPException(
            status_code=422, detail=f"frame index {req.index} out of range"
        )

    try:
        base = store.load_image(req.project_id, "sprite")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project has no base sprite")

    # Target size = an existing OK sibling frame, so the regenerated frame stays
    # size-consistent with the rest of the cycle. Fall back to the base sprite's
    # trimmed size when no sibling has succeeded yet.
    target_size: tuple[int, int] | None = None
    for f in project.frames:
        if f.index != req.index and f.status is FrameStatus.OK:
            target_size = store.load_image(req.project_id, f"frame_{f.index}").size
            break
    if target_size is None:
        target_size = trim.autocrop(base, padding=0).size

    remover = getattr(request.app.state, "remover", None)
    prompt = prompt_builder.frame_prompt(project.action, req.index, total)
    try:
        edited = gemini.edit(base, prompt)
        cut = background.remove(edited, remover=remover)
        sprite = _fit_to_size(cut, target_size)
        if project.style is Style.PIXEL:
            sprite = pixelate.quantize(sprite)
        status = FrameStatus.OK
    except (GeminiError, SafetyBlockedError, EmptyImageError, DegenerateBBoxError):
        status = FrameStatus.FAILED

    if status is FrameStatus.OK:
        name = f"frame_{req.index}"
        store.save_image(req.project_id, name, sprite)
        frame = Frame(
            index=req.index,
            url=f"/projects/{req.project_id}/{name}.png",
            status=FrameStatus.OK,
        )
    else:
        frame = Frame(index=req.index, url=None, status=FrameStatus.FAILED)

    project.frames[req.index] = frame
    store.write_manifest(req.project_id, project)
    return frame.model_dump()


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
        project = store.read_manifest(req.project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")

    if project.action is None:
        raise HTTPException(status_code=422, detail="project has not been animated")

    total = len(project.frames)
    if not (0 <= req.index < total):
        raise HTTPException(
            status_code=422, detail=f"frame index {req.index} out of range"
        )

    survivors = [f for f in project.frames if f.index != req.index]

    # Load every surviving OK image into memory *before* touching disk, keyed by
    # its new (post-delete) index, so re-numbering can't collide with a file that
    # hasn't been moved yet (e.g. frame_2 -> frame_1 while frame_1 still exists).
    loaded: dict[int, Image.Image] = {}
    for new_index, frame in enumerate(survivors):
        if frame.status is FrameStatus.OK:
            loaded[new_index] = store.load_image(req.project_id, f"frame_{frame.index}")

    # Clear all existing frame files, then rewrite the survivors at their new
    # contiguous indices.
    for frame in project.frames:
        store.delete_image(req.project_id, f"frame_{frame.index}")

    new_frames: list[Frame] = []
    for new_index, frame in enumerate(survivors):
        if new_index in loaded:
            name = f"frame_{new_index}"
            store.save_image(req.project_id, name, loaded[new_index])
            new_frames.append(
                Frame(
                    index=new_index,
                    url=f"/projects/{req.project_id}/{name}.png",
                    status=FrameStatus.OK,
                )
            )
        else:
            new_frames.append(
                Frame(index=new_index, url=None, status=FrameStatus.FAILED)
            )

    project.frames = new_frames
    store.write_manifest(req.project_id, project)

    return {
        "project_id": req.project_id,
        "action": project.action,
        "fps": project.fps,
        "frames": [f.model_dump() for f in new_frames],
    }
