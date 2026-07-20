"""GET /projects/{id}/{filename} — serve saved sprite/atlas files."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.deps import get_store
from app.storage.project_store import ProjectStore

router = APIRouter()


@router.get("/projects/{project_id}/{filename}")
def get_asset(
    project_id: str, filename: str, store: ProjectStore = Depends(get_store)
):
    try:
        path = store.asset_path(project_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="asset not found")
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid asset path")
    return FileResponse(path)
