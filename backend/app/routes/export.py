"""POST /export — pack a project's frames into a sheet + atlas.

Stage 1 exports a single frame; the packer/atlas already handle N frames, so
Task 16 (multi-frame) needs no route change beyond reading all frames.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.deps import get_store
from app.models import ExportFormat, FrameStatus
from app.pipeline import atlas, packer
from app.services.asset_urls import asset_url
from app.storage.project_store import ProjectStore

router = APIRouter()


class ExportRequest(BaseModel):
    project_id: str
    format: ExportFormat = ExportFormat.JSON
    padding: int = Field(default=0, ge=0)
    cols: int | None = Field(default=None, ge=1)


@router.post("/export")
def export(req: ExportRequest, store: ProjectStore = Depends(get_store)):
    try:
        project = store.read_manifest(req.project_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="project not found")

    failed_count = sum(1 for f in project.frames if f.status is FrameStatus.FAILED)
    if failed_count:
        plural = "frame" if failed_count == 1 else "frames"
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project has {failed_count} failed {plural}; "
                "regenerate or delete them before export."
            ),
        )

    ok_frames = [f for f in project.frames if f.status is FrameStatus.OK]
    if not ok_frames:
        raise HTTPException(status_code=422, detail="project has no usable frames")

    images = []
    for frame in sorted(ok_frames, key=lambda f: f.index):
        name = "sprite" if len(project.frames) == 1 else f"frame_{frame.index}"
        images.append(store.load_image(req.project_id, name))

    sheet, layout = packer.pack(images, cols=req.cols, padding=req.padding)
    atlas_str = atlas.write_atlas(layout, sheet.size, fmt=req.format.value)

    store.save_image(req.project_id, "sprite_sheet", sheet)
    atlas_name = f"sprite.{req.format.value}"
    store.write_text(req.project_id, atlas_name, atlas_str)

    return {
        "sheet_url": asset_url(req.project_id, "sprite_sheet.png"),
        "atlas_url": asset_url(req.project_id, atlas_name),
    }
