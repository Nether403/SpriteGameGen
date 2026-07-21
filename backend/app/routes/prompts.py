"""Explicit prompt-enhancement preview endpoint."""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_gemini_client, get_store
from app.models import EnhancePromptRequest, EnhancePromptResult
from app.services.gemini_client import GeminiClient
from app.services.sprite_service import (
    SafetyServiceError,
    SpriteService,
    UpstreamServiceError,
)
from app.storage.project_store import ProjectStore

router = APIRouter(prefix="/prompts")


@router.post("/enhance", response_model=EnhancePromptResult)
def enhance_prompt(
    request: EnhancePromptRequest,
    gemini: GeminiClient = Depends(get_gemini_client),
    store: ProjectStore = Depends(get_store),
):
    try:
        return SpriteService(store=store, gemini=gemini).enhance_prompt(request)
    except SafetyServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
