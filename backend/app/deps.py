"""FastAPI dependency providers.

Defined separately so tests can override them (``app.dependency_overrides``)
without importing route modules. The default providers lazily construct the real
store and Gemini client from settings; tests swap in fakes.
"""
from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.services.gemini_client import GeminiClient, build_default_client
from app.storage.project_store import ProjectStore


@lru_cache(maxsize=1)
def _default_store() -> ProjectStore:
    return ProjectStore(root=get_settings().projects_dir)


@lru_cache(maxsize=1)
def _default_gemini() -> GeminiClient:
    return build_default_client()


def get_store() -> ProjectStore:
    """Provide the project store (overridden in tests)."""
    return _default_store()


def get_gemini_client() -> GeminiClient:
    """Provide the Gemini client (overridden in tests)."""
    return _default_gemini()
