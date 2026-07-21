"""Image-provider availability and deterministic selection policy."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.models import ImageProviderName
from app.services.image_provider import ImageProvider, PromptEnhancer


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


@dataclass(frozen=True)
class ProviderRegistry:
    """One provider-selection policy shared by every transport adapter."""

    gemini: ImageProvider | None
    azure: ImageProvider | None

    @property
    def prompt_enhancer(self) -> PromptEnhancer | None:
        return self.gemini

    def resolve(self, requested: ImageProviderName) -> ResolvedProvider:
        return resolve_image_provider(requested, self.gemini, self.azure)

    def resolve_stored(self, stored: ImageProviderName) -> ResolvedProvider:
        """Resolve a project's concrete provider without applying auto fallback."""

        if stored is ImageProviderName.AUTO:
            raise ProviderUnavailableError(
                "Project does not record a concrete image provider; choose a provider "
                "when generating a replacement project."
            )
        return self.resolve(stored)

    def options(self) -> list[ProviderOption]:
        return list_provider_options(
            azure_available=self.azure is not None,
            gemini_available=self.gemini is not None,
        )


def resolve_image_provider(
    requested: ImageProviderName,
    gemini: ImageProvider | None,
    azure: ImageProvider | None,
) -> ResolvedProvider:
    if requested is ImageProviderName.AUTO:
        if azure is not None:
            return ResolvedProvider(ImageProviderName.AZURE, azure)
        if gemini is not None:
            return ResolvedProvider(ImageProviderName.GEMINI, gemini)
        raise ProviderUnavailableError("No image provider is configured on this backend.")
    if requested is ImageProviderName.GEMINI:
        if gemini is None:
            raise ProviderUnavailableError(
                "Gemini is not configured on this backend."
            )
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


def list_provider_options(
    *, azure_available: bool, gemini_available: bool
) -> list[ProviderOption]:
    return [
        ProviderOption(
            id=ImageProviderName.AUTO,
            label="Auto",
            available=azure_available or gemini_available,
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
            available=gemini_available,
            description="Existing Vertex AI image pipeline; frame edits remain sequential.",
            unavailable_reason=(
                None
                if gemini_available
                else "Google Cloud project and credentials are not configured."
            ),
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
