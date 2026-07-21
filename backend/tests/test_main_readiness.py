"""Application liveness, readiness, and module-level configuration wiring."""

import importlib

from httpx import ASGITransport, AsyncClient

from app.deps import get_provider_availability, get_store
from app.main import create_app
from app.storage.project_store import ProjectStore


async def test_health_is_unconditional_and_ready_is_client_free(tmp_path):
    app = create_app()
    store = ProjectStore(tmp_path / "projects")
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_provider_availability] = lambda: {
        "gemini": {"available": False, "detail": "not configured"},
        "azure": {"available": True, "detail": "configured"},
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        health = await client.get("/health")
        ready = await client.get("/ready")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "storage": {"ready": True, "projects_dir": str(store.root)},
        "providers": {
            "gemini": {"available": False, "detail": "not configured"},
            "azure": {"available": True, "detail": "configured"},
        },
    }


async def test_missing_storage_fails_readiness_but_not_liveness(tmp_path):
    app = create_app()
    store = ProjectStore(tmp_path / "projects")
    store.root.rmdir()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_provider_availability] = lambda: {}

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        health = await client.get("/health")
        ready = await client.get("/ready")

    assert health.status_code == 200
    assert ready.status_code == 503
    assert ready.json()["status"] == "not_ready"
    assert ready.json()["storage"] == {
        "ready": False,
        "projects_dir": str(store.root),
    }


def test_module_app_uses_configured_upload_limit(monkeypatch, tmp_path):
    env_file = tmp_path / "sprite.env"
    env_file.write_text(
        f"PROJECTS_DIR={tmp_path / 'projects'}\nMAX_UPLOAD_BYTES=12345\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SPRITE_ENV_FILE", str(env_file))

    import app.config as config
    import app.main as main

    config.get_settings.cache_clear()
    importlib.reload(main)
    try:
        assert main.app.state.max_upload_bytes == 12345
    finally:
        config.get_settings.cache_clear()
