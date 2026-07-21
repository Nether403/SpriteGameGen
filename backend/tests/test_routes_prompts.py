"""Prompt enhancement preview route: explicit, non-persisting, and recoverable."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_gemini_client, get_store
from app.main import create_app
from app.models import Direction, Style, ViewMode
from app.services.gemini_client import GeminiError, SafetyBlockedError
from app.storage.project_store import ProjectStore


class FakeGemini:
    def __init__(self, result="A silver-armored knight with a bold blue silhouette"):
        self.result = result
        self.calls = []

    def enhance_prompt(self, prompt, style, view_mode, direction):
        self.calls.append((prompt, style, view_mode, direction))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _make(tmp_path, result=None):
    store = ProjectStore(root=tmp_path)
    fake = FakeGemini() if result is None else FakeGemini(result)
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_gemini_client] = lambda: fake
    return app, store, fake


@pytest.mark.asyncio
async def test_enhance_returns_preview_without_creating_project(tmp_path):
    app, store, fake = _make(tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/prompts/enhance",
            json={
                "prompt": "a knight",
                "style": "pixel",
                "view_mode": "top_down_2_5d",
                "direction": "up_left",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "original_prompt": "a knight",
        "enhanced_prompt": fake.result,
    }
    assert fake.calls == [
        ("a knight", Style.PIXEL, ViewMode.TOP_DOWN_2_5D, Direction.UP_LEFT)
    ]
    assert list(store.root.iterdir()) == []


@pytest.mark.asyncio
async def test_enhance_validates_context_before_model_call(tmp_path):
    app, store, fake = _make(tmp_path)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/prompts/enhance",
            json={
                "prompt": "a knight",
                "style": "pixel",
                "view_mode": "side_scroller",
                "direction": "up",
            },
        )

    assert response.status_code == 422
    assert fake.calls == []
    assert list(store.root.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status"),
    [(GeminiError("offline"), 502), (SafetyBlockedError("blocked"), 422)],
)
async def test_enhance_failure_is_non_persisting(tmp_path, failure, status):
    app, store, _ = _make(tmp_path, failure)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/prompts/enhance",
            json={"prompt": "a knight", "style": "pixel"},
        )

    assert response.status_code == status
    assert list(store.root.iterdir()) == []
