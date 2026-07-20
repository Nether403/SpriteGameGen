"""Application configuration.

Auth model: Vertex AI / Google Agent Platform via a service-account JSON key
(not a GEMINI_API_KEY). The credentials path, GCP project, and region are read
from the environment here and nowhere else. Model IDs also live only here and
are read solely by ``gemini_client.py``.

Validation is fail-loud: a missing/unreadable credentials file or an unset
project raises at settings-construction time (app startup), never mid-request.
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
    google_cloud_region: str = Field(default="us-central1")

    # --- Model IDs (config-only; read only by gemini_client) ---
    gemini_model_generate: str = Field(default="gemini-3.1-flash-image")
    gemini_model_edit: str = Field(default="gemini-3.1-flash-image")

    # --- Storage / limits ---
    projects_dir: str = Field(default="./projects")
    max_upload_bytes: int = Field(default=10 * 1024 * 1024)  # 10 MiB

    @model_validator(mode="after")
    def _validate_auth(self) -> "Settings":
        if not self.google_application_credentials:
            raise ValueError(
                "GOOGLE_APPLICATION_CREDENTIALS is not set. This app authenticates "
                "to Gemini via a Vertex AI service-account JSON key; point this at "
                "the key file."
            )
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
