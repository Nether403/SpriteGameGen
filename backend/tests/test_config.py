"""Provider-independent application configuration."""

import importlib
from pathlib import Path

import pytest


_CONFIG_KEYS = (
    "SPRITE_ENV_FILE",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_REGION",
    "GEMINI_MODEL_GENERATE",
    "GEMINI_MODEL_EDIT",
    "GEMINI_MODEL_TEXT",
    "PROJECTS_DIR",
    "MAX_UPLOAD_BYTES",
    "GEMINI_TIMEOUT_SECONDS",
    "GEMINI_MAX_RETRIES",
    "GEMINI_BACKOFF_SECONDS",
    "GEMINI_QUOTA_BACKOFF_SECONDS",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_IMAGE_QUALITY",
    "AZURE_IMAGE_TIMEOUT_SECONDS",
    "AZURE_IMAGE_MAX_RETRIES",
    "AZURE_IMAGE_MAX_CONCURRENCY",
    "CREATIVE_OPERATION_TIMEOUT_SECONDS",
    "CREATIVE_OPERATION_MAX_CONCURRENCY",
)


def _clear_env(monkeypatch):
    for key in _CONFIG_KEYS:
        monkeypatch.delenv(key, raising=False)


def _fresh_config():
    """Reload the module so the cached settings don't leak between tests."""
    import app.config as config

    importlib.reload(config)
    return config


def _select_env_file(monkeypatch, tmp_path: Path, contents: str = "") -> Path:
    _clear_env(monkeypatch)
    env_file = tmp_path / "config" / "sprite.env"
    env_file.parent.mkdir()
    env_file.write_text(contents, encoding="utf-8")
    monkeypatch.setenv("SPRITE_ENV_FILE", str(env_file))
    return env_file


def test_selected_env_file_and_relative_paths_are_independent_of_cwd(
    monkeypatch, tmp_path
):
    env_file = _select_env_file(
        monkeypatch,
        tmp_path,
        "\n".join(
            (
                "GOOGLE_APPLICATION_CREDENTIALS=credentials/service-account.json",
                "GOOGLE_CLOUD_PROJECT=my-project",
                "PROJECTS_DIR=data/projects",
            )
        ),
    )
    credentials = env_file.parent / "credentials" / "service-account.json"
    credentials.parent.mkdir()
    credentials.write_text("{}", encoding="utf-8")
    foreign_cwd = tmp_path / "foreign-cwd"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)
    config = _fresh_config()

    settings = config.get_settings()

    assert settings.google_application_credentials == str(credentials.resolve())
    assert settings.projects_dir == str((env_file.parent / "data/projects").resolve())
    assert settings.gemini_readiness().available is True


def test_default_env_file_is_anchored_to_backend_not_process_cwd(
    monkeypatch, tmp_path
):
    _clear_env(monkeypatch)
    config = _fresh_config()
    assert config.DEFAULT_ENV_FILE == Path(config.__file__).resolve().parents[1] / ".env"

    default_env = tmp_path / "backend" / ".env"
    default_env.parent.mkdir()
    default_env.write_text("PROJECTS_DIR=default-projects\n", encoding="utf-8")
    monkeypatch.setattr(config, "DEFAULT_ENV_FILE", default_env)
    foreign_cwd = tmp_path / "foreign-cwd"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)

    settings = config.get_settings()

    assert settings.projects_dir == str(
        (default_env.parent / "default-projects").resolve()
    )


def test_storage_only_settings_and_store_do_not_require_google_project(
    monkeypatch, tmp_path
):
    env_file = _select_env_file(monkeypatch, tmp_path, "PROJECTS_DIR=projects\n")
    config = _fresh_config()

    settings = config.get_settings()

    import app.deps as deps

    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    deps._default_store.cache_clear()
    try:
        store = deps._default_store()
        assert store.root == (env_file.parent / "projects").resolve()
        assert settings.gemini_readiness().available is False
        assert settings.azure_readiness().available is False
    finally:
        deps._default_store.cache_clear()


def test_azure_only_configuration_is_available(monkeypatch, tmp_path):
    _select_env_file(
        monkeypatch,
        tmp_path,
        "\n".join(
            (
                "AZURE_OPENAI_ENDPOINT=https://sprites.openai.azure.com",
                "AZURE_OPENAI_API_KEY=secret",
                "AZURE_OPENAI_DEPLOYMENT=gpt-image-2-2",
            )
        ),
    )
    config = _fresh_config()

    settings = config.get_settings()

    assert settings.gemini_readiness().available is False
    assert settings.azure_readiness().available is True
    assert settings.require_azure() is settings
    assert settings.provider_availability()["azure"].available is True


def test_partial_azure_configuration_fails_loud(monkeypatch, tmp_path):
    _select_env_file(
        monkeypatch,
        tmp_path,
        "AZURE_OPENAI_ENDPOINT=https://sprites.openai.azure.com\n",
    )
    config = _fresh_config()

    with pytest.raises(RuntimeError, match="Azure image configuration is incomplete"):
        config.get_settings()


def test_gemini_readiness_requires_project_but_allows_adc(monkeypatch, tmp_path):
    _select_env_file(monkeypatch, tmp_path)
    config = _fresh_config()
    unconfigured = config.get_settings()

    assert unconfigured.gemini_readiness().available is False
    with pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"):
        unconfigured.require_gemini()

    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    config = _fresh_config()
    configured = config.get_settings()

    assert configured.google_application_credentials == ""
    assert configured.gemini_readiness().available is True
    assert configured.require_gemini() is configured


def test_invalid_relative_credential_path_is_reported_by_gemini_readiness(
    monkeypatch, tmp_path
):
    env_file = _select_env_file(
        monkeypatch,
        tmp_path,
        "\n".join(
            (
                "GOOGLE_APPLICATION_CREDENTIALS=credentials/missing.json",
                "GOOGLE_CLOUD_PROJECT=my-project",
            )
        ),
    )
    config = _fresh_config()

    settings = config.get_settings()

    expected_path = (env_file.parent / "credentials/missing.json").resolve()
    assert settings.google_application_credentials == str(expected_path)
    assert settings.gemini_readiness().available is False
    with pytest.raises(RuntimeError, match="GOOGLE_APPLICATION_CREDENTIALS"):
        settings.require_gemini()


def test_reads_defaults_and_overrides(monkeypatch, tmp_path):
    _select_env_file(monkeypatch, tmp_path)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    monkeypatch.setenv("GOOGLE_CLOUD_REGION", "europe-west4")
    monkeypatch.setenv("GEMINI_MODEL_GENERATE", "gemini-image-custom")
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "37")
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "7")
    monkeypatch.setenv("CREATIVE_OPERATION_TIMEOUT_SECONDS", "240")
    monkeypatch.setenv("CREATIVE_OPERATION_MAX_CONCURRENCY", "3")
    config = _fresh_config()

    settings = config.get_settings()

    assert settings.google_cloud_region == "europe-west4"
    assert settings.gemini_model_generate == "gemini-image-custom"
    assert settings.gemini_model_edit == "gemini-3.1-flash-image"
    assert settings.gemini_model_text == "gemini-3.5-flash"
    assert settings.gemini_timeout_seconds == 37
    assert settings.gemini_max_retries == 7
    assert settings.gemini_backoff_seconds == 1
    assert settings.gemini_quota_backoff_seconds == 15
    assert settings.creative_operation_timeout_seconds == 240
    assert settings.creative_operation_max_concurrency == 3


def test_get_settings_is_cached(monkeypatch, tmp_path):
    _select_env_file(monkeypatch, tmp_path)
    config = _fresh_config()

    assert config.get_settings() is config.get_settings()


def test_sprite_env_file_must_be_absolute(monkeypatch, tmp_path):
    _clear_env(monkeypatch)
    monkeypatch.setenv("SPRITE_ENV_FILE", "relative.env")
    config = _fresh_config()

    with pytest.raises(RuntimeError, match="SPRITE_ENV_FILE must be an absolute path"):
        config.get_settings()
