"""Provider-independent application configuration.

The dotenv file is selected deterministically: ``SPRITE_ENV_FILE`` may point to
an absolute file, otherwise ``backend/.env`` is used regardless of process CWD.
Relative filesystem settings are resolved from that file's directory.

Constructing settings validates common configuration and Azure's all-or-empty
identity tuple. Provider-specific requirements are checked explicitly through
the readiness and require methods, allowing storage-only operation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class ProviderReadiness:
    """Configuration-only provider availability, safe to expose in health data."""

    available: bool
    detail: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Vertex AI auth ---
    google_application_credentials: str = Field(default="")
    google_cloud_project: str = Field(default="")
    google_cloud_region: str = Field(default="global")

    # --- Model IDs (config-only; read only by gemini_client) ---
    gemini_model_generate: str = Field(default="gemini-3.1-flash-image")
    gemini_model_edit: str = Field(default="gemini-3.1-flash-image")
    gemini_model_text: str = Field(default="gemini-3.5-flash")
    gemini_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    gemini_max_retries: int = Field(default=5, ge=1, le=10)
    gemini_backoff_seconds: float = Field(default=1.0, gt=0, le=30)
    gemini_quota_backoff_seconds: float = Field(default=15.0, gt=0, le=120)

    # --- Azure OpenAI GPT Image (optional; all three identity fields together) ---
    azure_openai_endpoint: str = Field(default="")
    azure_openai_api_key: str = Field(default="")
    azure_openai_deployment: str = Field(default="")
    azure_image_quality: str = Field(default="low", pattern="^(low|medium|high|auto)$")
    azure_image_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    azure_image_max_retries: int = Field(default=2, ge=1, le=5)
    azure_image_max_concurrency: int = Field(default=3, ge=1, le=10)

    # --- Optional operator-owned local ComfyUI server ---
    comfyui_url: str = Field(default="")
    comfyui_workflow_descriptor: str = Field(default="")
    comfyui_timeout_seconds: float = Field(default=180.0, gt=0, le=3600)
    comfyui_poll_interval_seconds: float = Field(default=0.25, gt=0, le=10)

    # --- Storage / limits ---
    projects_dir: str = Field(default="./projects")
    action_packs_dir: str = Field(default="")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)  # 10 MiB
    creative_operation_timeout_seconds: float = Field(default=900.0, gt=0, le=3600)
    creative_operation_max_concurrency: int = Field(default=2, ge=1, le=32)

    @model_validator(mode="after")
    def _validate_azure_identity(self) -> "Settings":
        azure_identity = (
            self.azure_openai_endpoint.strip(),
            self.azure_openai_api_key.strip(),
            self.azure_openai_deployment.strip(),
        )
        if any(azure_identity) and not all(azure_identity):
            raise ValueError(
                "Azure image configuration is incomplete. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT together."
            )
        return self

    def gemini_readiness(self) -> ProviderReadiness:
        """Report whether Gemini can be constructed, without constructing it."""
        if self.google_application_credentials:
            credentials = Path(self.google_application_credentials)
            if not credentials.is_file():
                return ProviderReadiness(
                    available=False,
                    detail="GOOGLE_APPLICATION_CREDENTIALS points at a missing file",
                )
        if not self.google_cloud_project.strip():
            return ProviderReadiness(
                available=False,
                detail=(
                    "GOOGLE_CLOUD_PROJECT is not set. Vertex AI requires a GCP "
                    "project ID."
                ),
            )
        auth = (
            "service-account credentials configured"
            if self.google_application_credentials
            else "configured with Application Default Credentials"
        )
        return ProviderReadiness(available=True, detail=auth)

    def require_gemini(self) -> "Settings":
        """Raise an actionable error unless Gemini configuration is ready."""
        readiness = self.gemini_readiness()
        if not readiness.available:
            raise RuntimeError(f"Gemini is unavailable: {readiness.detail}")
        return self

    def azure_readiness(self) -> ProviderReadiness:
        """Report whether Azure GPT Image is configured, without constructing it."""
        if not self.azure_openai_endpoint.strip():
            return ProviderReadiness(
                available=False,
                detail="Azure OpenAI image provider is not configured",
            )
        return ProviderReadiness(
            available=True,
            detail="Azure OpenAI image provider is configured",
        )

    def require_azure(self) -> "Settings":
        """Raise an actionable error unless Azure image configuration is ready."""
        readiness = self.azure_readiness()
        if not readiness.available:
            raise RuntimeError(f"Azure image provider is unavailable: {readiness.detail}")
        return self

    def provider_availability(self) -> dict[str, ProviderReadiness]:
        """Return all provider readiness metadata without constructing clients."""
        return {
            "gemini": self.gemini_readiness(),
            "azure": self.azure_readiness(),
            "comfyui": self.comfyui_readiness(),
        }

    def comfyui_readiness(self) -> ProviderReadiness:
        if not self.comfyui_url.strip() and not self.comfyui_workflow_descriptor.strip():
            return ProviderReadiness(False, "ComfyUI is not configured")
        if not self.comfyui_url.strip() or not self.comfyui_workflow_descriptor.strip():
            return ProviderReadiness(False, "ComfyUI configuration is incomplete")
        try:
            from app.services.comfyui_provider import validate_loopback_url

            validate_loopback_url(self.comfyui_url)
        except ValueError:
            return ProviderReadiness(False, "ComfyUI URL is not an explicit loopback URL")
        if not Path(self.comfyui_workflow_descriptor).is_file():
            return ProviderReadiness(False, "ComfyUI workflow descriptor is missing")
        return ProviderReadiness(True, "ComfyUI loopback workflow is configured")


def _selected_env_file() -> Path:
    configured = os.environ.get("SPRITE_ENV_FILE")
    if not configured:
        return DEFAULT_ENV_FILE
    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise RuntimeError("SPRITE_ENV_FILE must be an absolute path")
    return path.resolve()


def _resolve_path(value: str, base_dir: Path) -> str:
    if not value:
        return value
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return str(path.resolve())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached common settings from the deterministic dotenv location."""
    env_file = _selected_env_file()
    try:
        settings = Settings(_env_file=env_file, _env_file_encoding="utf-8")
    except ValidationError as exc:
        messages = "; ".join(
            err["msg"].removeprefix("Value error, ") for err in exc.errors()
        )
        raise RuntimeError(f"Invalid configuration: {messages}") from exc

    base_dir = env_file.parent
    settings.google_application_credentials = _resolve_path(
        settings.google_application_credentials, base_dir
    )
    settings.projects_dir = _resolve_path(settings.projects_dir, base_dir)
    settings.action_packs_dir = _resolve_path(settings.action_packs_dir, base_dir)
    settings.comfyui_workflow_descriptor = _resolve_path(
        settings.comfyui_workflow_descriptor, base_dir
    )
    return settings
