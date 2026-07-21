"""FastAPI dependency providers.

Defined separately so tests can override them (``app.dependency_overrides``)
without importing route modules. The default providers lazily construct the real
store and Gemini client from settings; tests swap in fakes.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.azure_image_provider import AzureImageProvider
from app.services.gemini_client import GeminiClient, build_default_client
from app.storage.project_store import ProjectStore


@lru_cache(maxsize=1)
def _default_store() -> ProjectStore:
    return ProjectStore(root=get_settings().projects_dir)


@lru_cache(maxsize=1)
def _default_gemini() -> GeminiClient:
    return build_default_client()


@lru_cache(maxsize=1)
def _default_azure() -> AzureImageProvider | None:
    settings = get_settings()
    if not settings.azure_openai_endpoint:
        return None
    return AzureImageProvider(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_deployment,
        quality=settings.azure_image_quality,
        timeout_s=settings.azure_image_timeout_seconds,
        max_retries=settings.azure_image_max_retries,
        max_concurrency=settings.azure_image_max_concurrency,
    )


def get_store() -> ProjectStore:
    """Provide the project store (overridden in tests)."""
    return _default_store()


def get_gemini_client() -> GeminiClient:
    """Provide the Gemini client (overridden in tests)."""
    return _default_gemini()


def get_azure_image_provider() -> AzureImageProvider | None:
    """Provide Azure GPT Image when its three required settings are present."""
    return _default_azure()
