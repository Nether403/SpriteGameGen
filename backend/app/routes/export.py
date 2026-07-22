"""POST /export — pack a project's frames into a sheet + atlas.

Stage 1 exports a single frame; the packer/atlas already handle N frames, so
Task 16 (multi-frame) needs no route change beyond reading all frames.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
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


class CharacterBundleRequest(BaseModel):
    project_id: str
    scope: str = "active"
    clip_id: str | None = None
    engine_profile: str | None = None


@router.post("/export")
def export(req: ExportRequest, store: ProjectStore = Depends(get_store)):
    try:
        result = SpriteService(store=store).export_sheet(
            req.project_id,
            ExportOptions(
                format=req.format,
                padding=req.padding,
                cols=req.cols,
                clip_id=req.clip_id,
            ),
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
        "frames_url": asset_url(req.project_id, result.frames_filename),
    }


@router.post("/exports/character-bundle")
def export_character_bundle(
    req: CharacterBundleRequest, store: ProjectStore = Depends(get_store)
):
    try:
        result = SpriteService(store=store).export_character_bundle(
            req.project_id,
            scope=req.scope,
            clip_id=req.clip_id,
            engine_profile=req.engine_profile,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ProjectUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (ValidationServiceError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ProjectConflictServiceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"bundle_url": asset_url(req.project_id, result.bundle_filename)}
