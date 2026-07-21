"""Config module: fail-loud validation of Vertex AI service-account auth."""
import importlib

import pytest


def _clear_env(monkeypatch, tmp_path):
    # Run in an empty dir so pydantic's `.env` fallback can't leak the developer's
    # real backend/.env into these tests — they must depend only on env vars set
    # here.
    monkeypatch.chdir(tmp_path)
    for key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_REGION",
        "GEMINI_MODEL_GENERATE",
        "GEMINI_MODEL_EDIT",
        "PROJECTS_DIR",
        "MAX_UPLOAD_BYTES",
    ):
        monkeypatch.delenv(key, raising=False)


def _fresh_config():
    """Reload the module so the cached settings don't leak between tests."""
    import app.config as config

    importlib.reload(config)
    return config


def _valid_env(monkeypatch, tmp_path):
    _clear_env(monkeypatch, tmp_path)
    key_file = tmp_path / "sa.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key_file))
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    return key_file


def test_reads_env_and_defaults(monkeypatch, tmp_path):
    key_file = _valid_env(monkeypatch, tmp_path)
    config = _fresh_config()

    settings = config.get_settings()
    assert settings.google_application_credentials == str(key_file)
    assert settings.google_cloud_project == "my-project"
    # Region and model IDs have sane defaults.
    assert settings.google_cloud_region == "global"
    assert settings.gemini_model_generate == "gemini-3.1-flash-image"
    assert settings.gemini_model_edit == "gemini-3.1-flash-image"


def test_model_ids_and_region_overridable(monkeypatch, tmp_path):
    _valid_env(monkeypatch, tmp_path)
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "europe-west4")
    monkeypatch.setenv("GEMINI_MODEL_GENERATE", "gemini-3.1-flash-lite-image")
    monkeypatch.setenv("GEMINI_MODEL_EDIT", "gemini-3-pro-image")
    config = _fresh_config()

    settings = config.get_settings()
    assert settings.google_cloud_region == "europe-west4"
    assert settings.gemini_model_generate == "gemini-3.1-flash-lite-image"
    assert settings.gemini_model_edit == "gemini-3-pro-image"


def test_missing_project_fails_loud(monkeypatch, tmp_path):
    _valid_env(monkeypatch, tmp_path)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    config = _fresh_config()

    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        config.get_settings()


def test_missing_credentials_file_fails_loud(monkeypatch, tmp_path):
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv(
        "GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "does-not-exist.json")
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    config = _fresh_config()

    with pytest.raises(RuntimeError, match="GOOGLE_APPLICATION_CREDENTIALS"):
        config.get_settings()


def test_unset_credentials_allowed_for_adc(monkeypatch, tmp_path):
    # An empty credentials path is valid — the SDK falls back to Application
    # Default Credentials (gcloud). Only the project is required.
    _clear_env(monkeypatch, tmp_path)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    config = _fresh_config()

    settings = config.get_settings()
    assert settings.google_application_credentials == ""
    assert settings.google_cloud_project == "my-project"


def test_get_settings_is_cached(monkeypatch, tmp_path):
    _valid_env(monkeypatch, tmp_path)
    config = _fresh_config()

    assert config.get_settings() is config.get_settings()
