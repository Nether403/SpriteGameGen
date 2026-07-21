"""Application configuration.

Auth model: Vertex AI / Google Agent Platform. Preferred path is an explicit
service-account JSON key (``GOOGLE_APPLICATION_CREDENTIALS``); when that is unset
the SDK falls back to Application Default Credentials (e.g. a ``gcloud`` login).
The credentials path, GCP project, and region are read from the environment here
and nowhere else. Model IDs also live only here and are read solely by
``gemini_client.py``.

Validation is fail-loud: a credentials path that points at a missing file, or an
unset project, raises at settings-construction time (app startup), never
mid-request. An empty credentials path is allowed (ADC fallback).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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

    # --- Storage / limits ---
    projects_dir: str = Field(default="./projects")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024)  # 10 MiB

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        # The service-account key is OPTIONAL: when set it is used explicitly,
        # and when empty the SDK falls back to Application Default Credentials
        # (e.g. a gcloud login). Either way a project is required for Vertex.
        if self.google_application_credentials:
            cred_path = Path(self.google_application_credentials)
            if not cred_path.is_file():
                raise ValueError(
                    f"GOOGLE_APPLICATION_CREDENTIALS points at a missing file: "
                    f"{cred_path}"
                )
        if not self.google_cloud_project:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is not set. Vertex AI requires a GCP project ID."
            )
        azure_identity = (
            self.azure_openai_endpoint,
            self.azure_openai_api_key,
            self.azure_openai_deployment,
        )
        if any(azure_identity) and not all(azure_identity):
            raise ValueError(
                "Azure image configuration is incomplete. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT together."
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings, failing loudly on invalid/missing auth config."""
    try:
        return Settings()
    except ValidationError as exc:
        # Re-raise as a plain, actionable RuntimeError so startup failure is clear
        # and not buried in a pydantic traceback.
        messages = "; ".join(err["msg"].removeprefix("Value error, ") for err in exc.errors())
        raise RuntimeError(f"Invalid configuration: {messages}") from exc
