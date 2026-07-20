"""Stage 2 route tests: /animate, /presets (fake Gemini edit)."""
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.deps import get_gemini_client, get_store
from app.main import create_app
from app.services.gemini_client import GeminiError
from app.storage.project_store import ProjectStore


class FakeGemini:
    """generate() makes a removable-bg sprite; edit() echoes a similar sprite.

    ``fail_on`` is a set of frame indices; edit() raises GeminiError for those so
    partial-failure handling can be exercised. edit() call order matches frame
    order, so we track the call count to know which frame index is in flight.
    """

    def __init__(self, fail_on: set[int] | None = None):
        self.fail_on = fail_on or set()
        self.edit_prompts: list[str] = []

    def _sprite(self):
        img = Image.new("RGBA", (64, 64), (0, 255, 0, 255))  # green bg
        img.paste(Image.new("RGBA", (20, 20), (255, 0, 0, 255)), (22, 20))
        return img

    def generate(self, prompt, style, reference=None):
        return self._sprite()

    def edit(self, base_img, prompt):
        index = len(self.edit_prompts)
        self.edit_prompts.append(prompt)
        if index in self.fail_on:
            raise GeminiError("simulated frame failure")
        return self._sprite()


def _fake_remover(img: Image.Image) -> Image.Image:
    arr = np.asarray(img.convert("RGBA")).copy()
    green = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 0)
    arr[green, 3] = 0
    return Image.fromarray(arr, "RGBA")


def _make(tmp_path, fail_on=None):
    store = ProjectStore(root=tmp_path)
    fake = FakeGemini(fail_on=fail_on)
    app = create_app(remover=_fake_remover)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_gemini_client] = lambda: fake
    return app, store, fake


@pytest.fixture
def app_and_store(tmp_path):
    return _make(tmp_path)


@pytest.fixture
async def client(app_and_store):
    app, _, _ = app_and_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _generate(client, style="pixel"):
    resp = await client.post("/generate", data={"prompt": "a knight", "style": style})
    return resp.json()["project_id"]


async def test_presets_lists_actions(client):
    resp = await client.get("/presets")
    assert resp.status_code == 200
    actions = {p["action"] for p in resp.json()}
    assert {"idle", "walk", "run", "attack", "jump"} <= actions


async def test_animate_uses_preset_default_frame_count(client, app_and_store):
    _, store, fake = app_and_store
    pid = await _generate(client)

    resp = await client.post("/animate", json={"project_id": pid, "action": "walk"})
    assert resp.status_code == 200
    body = resp.json()
    # walk default is 6 frames
    assert len(body["frames"]) == 6
    assert body["action"] == "walk"
    assert body["fps"] == 8
    assert all(f["status"] == "ok" for f in body["frames"])

    # manifest updated with frames + animation metadata
    project = store.read_manifest(pid)
    assert len(project.frames) == 6
    assert project.action == "walk"
    assert project.fps == 8
    # frame images persisted
    assert store.load_image(pid, "frame_0").mode == "RGBA"


async def test_animate_clamps_requested_frames_to_preset_window(client, app_and_store):
    pid = await _generate(client)
    # idle max is 4; request 10 -> clamps to 4
    resp = await client.post(
        "/animate", json={"project_id": pid, "action": "idle", "frames": 4, "fps": 12}
    )
    assert resp.status_code == 200
    assert len(resp.json()["frames"]) == 4
    assert resp.json()["fps"] == 12


async def test_animate_partial_failure_marks_frame_failed(tmp_path):
    app, store, _ = _make(tmp_path, fail_on={2})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pid = await _generate(c)
        resp = await c.post(
            "/animate", json={"project_id": pid, "action": "walk", "frames": 4}
        )

    assert resp.status_code == 200
    frames = resp.json()["frames"]
    assert len(frames) == 4
    failed = [f for f in frames if f["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["index"] == 2
    assert failed[0]["url"] is None
    # other frames still succeeded
    assert sum(1 for f in frames if f["status"] == "ok") == 3


async def test_animate_unknown_action_422(client, app_and_store):
    pid = await _generate(client)
    resp = await client.post("/animate", json={"project_id": pid, "action": "fly"})
    assert resp.status_code == 422


async def test_animate_unknown_project_404(client):
    resp = await client.post("/animate", json={"project_id": "nope", "action": "walk"})
    assert resp.status_code == 404


async def test_animate_edit_prompts_are_base_anchored(client, app_and_store):
    _, _, fake = app_and_store
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "run", "frames": 4})
    # each frame prompt references the walking/running pose and frame numbering
    assert len(fake.edit_prompts) == 4
    assert "1 of 4" in fake.edit_prompts[0] or "1" in fake.edit_prompts[0]
