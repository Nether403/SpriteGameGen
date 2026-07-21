"""Image-provider availability and deterministic selection policy."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.models import ImageProviderName
from app.services.image_provider import ImageProvider


class ProviderUnavailableError(RuntimeError):
    """A requested provider is not configured or not runtime-ready."""


@dataclass(frozen=True)
class ResolvedProvider:
    name: ImageProviderName
    provider: ImageProvider


class ProviderOption(BaseModel):
    id: ImageProviderName
    label: str
    available: bool
    experimental: bool = False
    description: str
    unavailable_reason: str | None = None


def resolve_image_provider(
    requested: ImageProviderName,
    gemini: ImageProvider,
    azure: ImageProvider | None,
) -> ResolvedProvider:
    if requested is ImageProviderName.AUTO:
        return ResolvedProvider(
            ImageProviderName.AZURE if azure is not None else ImageProviderName.GEMINI,
            azure if azure is not None else gemini,
        )
    if requested is ImageProviderName.GEMINI:
        return ResolvedProvider(ImageProviderName.GEMINI, gemini)
    if requested is ImageProviderName.AZURE:
        if azure is None:
            raise ProviderUnavailableError(
                "Azure GPT Image is not configured on this backend."
            )
        return ResolvedProvider(ImageProviderName.AZURE, azure)
    raise ProviderUnavailableError(
        "Hyperagent Experimental is not runtime-ready: its image capability is "
        "agent-mediated and the dedicated sprite agent has not yet been validated."
    )


def list_provider_options(*, azure_available: bool) -> list[ProviderOption]:
    return [
        ProviderOption(
            id=ImageProviderName.AUTO,
            label="Auto",
            available=True,
            description=(
                "Uses Azure GPT Image when configured, otherwise Gemini."
            ),
        ),
        ProviderOption(
            id=ImageProviderName.AZURE,
            label="Azure GPT Image 2",
            available=azure_available,
            description="Best current throughput; up to three frame edits at once.",
            unavailable_reason=(
                None
                if azure_available
                else "Azure endpoint, deployment, and API key are not configured."
            ),
        ),
        ProviderOption(
            id=ImageProviderName.GEMINI,
            label="Gemini",
            available=True,
            description="Existing Vertex AI image pipeline; frame edits remain sequential.",
        ),
        ProviderOption(
            id=ImageProviderName.HYPERAGENT,
            label="Hyperagent Experimental",
            available=False,
            experimental=True,
            description="Agent-mediated Gemini image generation for evaluation only.",
            unavailable_reason="Dedicated image agent and runtime authentication are not validated.",
        ),
    ]
