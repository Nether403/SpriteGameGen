"""Image-provider availability and deterministic selection policy."""
from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from app.models import ImageProviderName
from app.services.image_provider import (
    ImageProvider,
    PromptEnhancer,
    ProviderCapability,
)


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
    capabilities: list[ProviderCapability] = []


@dataclass(frozen=True)
class ProviderRequirements:
    capabilities: frozenset[ProviderCapability] = frozenset()


@dataclass(frozen=True)
class ProviderRegistry:
    """One provider-selection policy shared by every transport adapter."""

    gemini: ImageProvider | None
    azure: ImageProvider | None
    comfyui: ImageProvider | None = None

    @property
    def prompt_enhancer(self) -> PromptEnhancer | None:
        return self.gemini

    def resolve(
        self,
        requested: ImageProviderName,
        requirements: ProviderRequirements | None = None,
    ) -> ResolvedProvider:
        return resolve_image_provider(
            requested, self.gemini, self.azure, self.comfyui, requirements
        )

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
            comfyui_available=(
                self.comfyui is not None
                and not getattr(self.comfyui, "_draining", False)
            ),
            providers={
                ImageProviderName.AZURE: self.azure,
                ImageProviderName.GEMINI: self.gemini,
                ImageProviderName.COMFYUI: self.comfyui,
            },
        )


def resolve_image_provider(
    requested: ImageProviderName,
    gemini: ImageProvider | None,
    azure: ImageProvider | None,
    comfyui: ImageProvider | None = None,
    requirements: ProviderRequirements | None = None,
) -> ResolvedProvider:
    required = (requirements or ProviderRequirements()).capabilities
    def supports(provider: ImageProvider | None) -> bool:
        if provider is None:
            return False
        if getattr(provider, "_draining", False):
            return False
        capabilities = getattr(provider, "capabilities", frozenset(ProviderCapability))
        return required <= capabilities

    if requested is ImageProviderName.AUTO:
        if supports(azure):
            return ResolvedProvider(ImageProviderName.AZURE, azure)
        if supports(gemini):
            return ResolvedProvider(ImageProviderName.GEMINI, gemini)
        if supports(comfyui):
            return ResolvedProvider(ImageProviderName.COMFYUI, comfyui)
        raise ProviderUnavailableError(
            "No image provider is configured with the requested capabilities."
        )
    if requested is ImageProviderName.GEMINI:
        if not supports(gemini):
            raise ProviderUnavailableError(
                "Gemini is not configured on this backend."
            )
        return ResolvedProvider(ImageProviderName.GEMINI, gemini)
    if requested is ImageProviderName.AZURE:
        if not supports(azure):
            raise ProviderUnavailableError(
                "Azure GPT Image is not configured on this backend."
            )
        return ResolvedProvider(ImageProviderName.AZURE, azure)
    if requested is ImageProviderName.COMFYUI:
        if not supports(comfyui):
            raise ProviderUnavailableError(
                "ComfyUI is not configured or lacks a required capability."
            )
        return ResolvedProvider(ImageProviderName.COMFYUI, comfyui)
    raise ProviderUnavailableError(
        "Hyperagent Experimental is not runtime-ready: its image capability is "
        "agent-mediated and the dedicated sprite agent has not yet been validated."
    )


def list_provider_options(
    *,
    azure_available: bool,
    gemini_available: bool,
    comfyui_available: bool = False,
    providers: dict[ImageProviderName, ImageProvider | None] | None = None,
) -> list[ProviderOption]:
    providers = providers or {}
    def caps(name: ImageProviderName) -> list[ProviderCapability]:
        provider = providers.get(name)
        return sorted(
            getattr(provider, "capabilities", frozenset(ProviderCapability))
            if provider is not None else [],
            key=lambda value: value.value,
        )
    return [
        ProviderOption(
            id=ImageProviderName.AUTO,
            label="Auto",
            available=azure_available or gemini_available or comfyui_available,
            description=(
                "Uses Azure, then Gemini, then a configured local ComfyUI workflow."
            ),
        ),
        ProviderOption(
            id=ImageProviderName.AZURE,
            label="Azure GPT Image 2",
            available=azure_available,
            description="Best current throughput; up to three frame edits at once.",
            capabilities=caps(ImageProviderName.AZURE),
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
            capabilities=caps(ImageProviderName.GEMINI),
            unavailable_reason=(
                None
                if gemini_available
                else "Google Cloud project and credentials are not configured."
            ),
        ),
        ProviderOption(
            id=ImageProviderName.COMFYUI,
            label="ComfyUI (Local)",
            available=comfyui_available,
            description="Operator-owned loopback workflow; capabilities depend on bindings.",
            unavailable_reason=(None if comfyui_available else "Local ComfyUI workflow is not configured."),
            capabilities=caps(ImageProviderName.COMFYUI),
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
