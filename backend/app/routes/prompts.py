"""Explicit prompt-enhancement preview endpoint."""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_provider_registry, get_store
from app.models import EnhancePromptRequest, EnhancePromptResult
from app.services.provider_selection import ProviderRegistry
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
    providers: ProviderRegistry = Depends(get_provider_registry),
    store: ProjectStore = Depends(get_store),
):
    try:
        return SpriteService(
            store=store, prompt_enhancer=providers.prompt_enhancer
        ).enhance_prompt(request)
    except SafetyServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
