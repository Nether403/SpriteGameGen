"""POST /export — pack a project's frames into a sheet + atlas.

Stage 1 exports a single frame; the packer/atlas already handle N frames, so
Task 16 (multi-frame) needs no route change beyond reading all frames.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_store
from app.models import ExportOptions
from app.services.asset_urls import asset_url
from app.services.sprite_service import (
    ProjectConflictServiceError,
    ProjectNotFoundError,
    ProjectUnavailableError,
    SpriteService,
    ValidationServiceError,
)
from app.storage.project_store import ProjectStore

router = APIRouter()


class ExportRequest(ExportOptions):
    project_id: str


@router.post("/export")
def export(req: ExportRequest, store: ProjectStore = Depends(get_store)):
    try:
        result = SpriteService(store=store).export_sheet(
            req.project_id,
            ExportOptions(format=req.format, padding=req.padding, cols=req.cols),
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValidationServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectConflictServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {
        "sheet_url": asset_url(req.project_id, result.sheet_filename),
        "atlas_url": asset_url(req.project_id, result.atlas_filename),
    }
