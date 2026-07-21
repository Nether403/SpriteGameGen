"""Explicit prompt-enhancement preview endpoint."""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_gemini_client
from app.models import EnhancePromptRequest, EnhancePromptResult
from app.services.gemini_client import GeminiClient, GeminiError, SafetyBlockedError

router = APIRouter(prefix="/prompts")


@router.post("/enhance", response_model=EnhancePromptResult)
def enhance_prompt(
    request: EnhancePromptRequest,
    gemini: GeminiClient = Depends(get_gemini_client),
):
    try:
        enhanced = gemini.enhance_prompt(
            request.prompt,
            request.style,
            request.view_mode,
            request.direction,
        )
    except SafetyBlockedError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return EnhancePromptResult(
        original_prompt=request.prompt,
        enhanced_prompt=enhanced,
    )
