"""FastAPI dependency providers.

Defined separately so tests can override them (``app.dependency_overrides``)
without importing route modules. The default providers lazily construct the real
store and Gemini client from settings; tests swap in fakes.
"""
from __future__ import annotations

from functools import lru_cache

from fastapi import Depends

from app.config import ProviderReadiness, get_settings
from app.services.azure_image_provider import AzureImageProvider
from app.services.gemini_client import GeminiClient, build_default_client
from app.services.comfyui_provider import ComfyUIProvider
from app.services.provider_selection import ProviderRegistry
from app.storage.project_store import ProjectStore


@lru_cache(maxsize=1)
def _default_store() -> ProjectStore:
    return ProjectStore(root=get_settings().projects_dir)


@lru_cache(maxsize=1)
def _default_gemini() -> GeminiClient | None:
    if not get_settings().gemini_readiness().available:
        return None
    return build_default_client()


@lru_cache(maxsize=1)
def _default_azure() -> AzureImageProvider | None:
    settings = get_settings()
    if not settings.azure_readiness().available:
        return None
    settings.require_azure()
    return AzureImageProvider(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_deployment,
        quality=settings.azure_image_quality,
        timeout_s=settings.azure_image_timeout_seconds,
        max_retries=settings.azure_image_max_retries,
        max_concurrency=settings.azure_image_max_concurrency,
    )


@lru_cache(maxsize=1)
def _default_comfyui() -> ComfyUIProvider | None:
    settings = get_settings()
    if not settings.comfyui_readiness().available:
        return None
    return ComfyUIProvider(
        base_url=settings.comfyui_url,
        descriptor_path=settings.comfyui_workflow_descriptor,
        timeout_s=settings.comfyui_timeout_seconds,
        poll_interval_s=settings.comfyui_poll_interval_seconds,
    )


def get_store() -> ProjectStore:
    """Provide the project store (overridden in tests)."""
    return _default_store()


def get_gemini_client() -> GeminiClient | None:
    """Provide Gemini when configured (overridden in tests)."""
    return _default_gemini()


def get_azure_image_provider() -> AzureImageProvider | None:
    """Provide Azure GPT Image when its three required settings are present."""
    return _default_azure()


def get_comfyui_provider() -> ComfyUIProvider | None:
    return _default_comfyui()


def build_provider_registry() -> ProviderRegistry:
    """Build the registry outside FastAPI dependency injection."""

    return ProviderRegistry(
        gemini=get_gemini_client(),
        azure=get_azure_image_provider(),
        comfyui=get_comfyui_provider(),
    )


def get_provider_registry(
    gemini: GeminiClient | None = Depends(get_gemini_client),
    azure: AzureImageProvider | None = Depends(get_azure_image_provider),
    comfyui: ComfyUIProvider | None = Depends(get_comfyui_provider),
) -> ProviderRegistry:
    """Provide the shared image-provider selection registry."""

    return ProviderRegistry(gemini=gemini, azure=azure, comfyui=comfyui)


def get_provider_availability() -> dict[str, ProviderReadiness]:
    """Expose configuration readiness without constructing provider clients."""
    return get_settings().provider_availability()
