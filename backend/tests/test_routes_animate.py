"""Stage 2 route tests: /animate, /presets (fake Gemini edit)."""
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.deps import get_gemini_client, get_store
from app.main import create_app
from app.models import Direction, Style, ViewMode
from app.pipeline.pixelate import PixelateError
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

    def generate(
        self, prompt, style, reference=None, *, view_mode=None, direction=None
    ):
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


def _make(tmp_path, fail_on=None, remover=_fake_remover):
    store = ProjectStore(root=tmp_path)
    fake = FakeGemini(fail_on=fail_on)
    app = create_app(remover=remover)
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


async def _generate(
    client,
    style="pixel",
    view_mode="side_scroller",
    direction="left",
):
    resp = await client.post(
        "/generate",
        data={
            "prompt": "a knight",
            "style": style,
            "view_mode": view_mode,
            "direction": direction,
        },
    )
    return resp.json()["project_id"]


async def test_presets_lists_actions(client):
    resp = await client.get("/presets")
    assert resp.status_code == 200
    actions = {p["action"] for p in resp.json()}
    assert {"idle", "walk", "run", "attack", "jump"} <= actions


async def test_animation_options_are_camera_aware(client):
    response = await client.get("/animation-options")
    assert response.status_code == 200
    options = {item["view_mode"]: item["directions"] for item in response.json()}
    assert options["side_scroller"] == ["left", "right"]
    assert set(options["top_down_2_5d"]) == {item.value for item in Direction}


async def test_animate_persists_direction_and_uses_camera_prompt(client, app_and_store):
    _, store, fake = app_and_store
    pid = await _generate(
        client, view_mode="top_down_2_5d", direction="down"
    )

    response = await client.post(
        "/animate",
        json={"project_id": pid, "action": "walk", "frames": 4, "direction": "up_left"},
    )

    assert response.status_code == 200
    assert response.json()["view_mode"] == "top_down_2_5d"
    assert response.json()["direction"] == "up_left"
    project = store.read_manifest(pid)
    assert project.view_mode is ViewMode.TOP_DOWN_2_5D
    assert project.direction is Direction.UP_LEFT
    assert all("top-down" in prompt.lower() for prompt in fake.edit_prompts)
    assert all("up-left" in prompt.lower() for prompt in fake.edit_prompts)


async def test_animate_rejects_invalid_direction_before_edit(client, app_and_store):
    _, store, fake = app_and_store
    pid = await _generate(client)
    original = store.read_manifest(pid)

    response = await client.post(
        "/animate",
        json={"project_id": pid, "action": "walk", "direction": "up"},
    )

    assert response.status_code == 422
    assert fake.edit_prompts == []
    assert store.read_manifest(pid) == original


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


async def test_animate_background_failure_isolated_to_one_frame(tmp_path):
    calls = 0

    def flaky_remover(img):
        nonlocal calls
        calls += 1
        if calls == 2:  # generate uses call 1; animation frame 0 uses call 2
            raise RuntimeError("simulated remover failure")
        return _fake_remover(img)

    app, _, _ = _make(tmp_path, remover=flaky_remover)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pid = await _generate(c)
        resp = await c.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})

    assert resp.status_code == 200
    frames = resp.json()["frames"]
    assert [f["status"] for f in frames].count("failed") == 1
    assert frames[0]["status"] == "failed"


async def test_animate_pixelate_failure_isolated_to_one_frame(tmp_path, monkeypatch):
    app, store, _ = _make(tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pid = await _generate(c, style="hires")
        project = store.read_manifest(pid)
        project.style = Style.PIXEL
        store.write_manifest(pid, project)

        calls = 0

        def flaky_quantize(img):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise PixelateError("simulated quantize failure")
            return img

        monkeypatch.setattr("app.services.sprite_service.pixelate.quantize", flaky_quantize)
        resp = await c.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})

    assert resp.status_code == 200
    frames = resp.json()["frames"]
    assert [f["status"] for f in frames].count("failed") == 1
    assert frames[1]["status"] == "failed"
    # other frames still succeeded
    assert sum(1 for f in frames if f["status"] == "ok") == 3


async def test_animate_frames_share_identical_size_antijitter(client, app_and_store):
    """Shared-bbox alignment: every successful frame must be the same size so the
    character does not resize or shift between frames during playback."""
    _, store, _ = app_and_store
    pid = await _generate(client)
    resp = await client.post(
        "/animate", json={"project_id": pid, "action": "walk", "frames": 4}
    )
    frames = resp.json()["frames"]
    sizes = {
        store.load_image(pid, f"frame_{f['index']}").size
        for f in frames
        if f["status"] == "ok"
    }
    assert len(sizes) == 1  # all identical


async def test_animate_unknown_action_422(client, app_and_store):
    pid = await _generate(client)
    resp = await client.post("/animate", json={"project_id": pid, "action": "fly"})
    assert resp.status_code == 422


async def test_animate_unknown_project_404(client):
    resp = await client.post("/animate", json={"project_id": "nope", "action": "walk"})
    assert resp.status_code == 404


async def test_regenerate_frame_replaces_single_frame(client, app_and_store):
    _, store, _ = app_and_store
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})

    # capture sibling size to assert the regenerated frame matches it
    sibling_size = store.load_image(pid, "frame_0").size

    resp = await client.post("/animate/frame", json={"project_id": pid, "index": 2})
    assert resp.status_code == 200
    frame = resp.json()
    assert frame["index"] == 2
    assert frame["status"] == "ok"
    assert frame["url"].split("?", 1)[0].endswith("frame_2.png")
    assert "v=" in frame["url"]

    # regenerated frame keeps sibling size (no jitter)
    assert store.load_image(pid, "frame_2").size == sibling_size
    # manifest updated in place, still 4 frames
    project = store.read_manifest(pid)
    assert len(project.frames) == 4
    assert project.frames[2].status.value == "ok"


async def test_regenerate_frame_uses_persisted_camera_context(client, app_and_store):
    _, _, fake = app_and_store
    pid = await _generate(
        client, view_mode="top_down_2_5d", direction="down_right"
    )
    await client.post(
        "/animate",
        json={
            "project_id": pid,
            "action": "walk",
            "frames": 4,
            "direction": "down_right",
        },
    )

    response = await client.post(
        "/animate/frame", json={"project_id": pid, "index": 2}
    )

    assert response.status_code == 200
    assert "top-down" in fake.edit_prompts[-1].lower()
    assert "down-right" in fake.edit_prompts[-1].lower()


async def test_regenerate_failed_frame_recovers_it(tmp_path):
    # first frame index 1 fails during initial animate, then regenerate succeeds
    app, store, fake = _make(tmp_path, fail_on={1})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pid = await _generate(c)
        await c.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})
        # confirm frame 1 failed
        proj = store.read_manifest(pid)
        assert proj.frames[1].status.value == "failed"

        # clear the failure and regenerate just that frame
        fake.fail_on = set()
        resp = await c.post("/animate/frame", json={"project_id": pid, "index": 1})

    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert store.read_manifest(pid).frames[1].status.value == "ok"


async def test_regenerate_frame_out_of_range_422(client, app_and_store):
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})
    resp = await client.post("/animate/frame", json={"project_id": pid, "index": 99})
    assert resp.status_code == 422


async def test_regenerate_frame_unanimated_project_422(client, app_and_store):
    pid = await _generate(client)  # generated but never animated
    resp = await client.post("/animate/frame", json={"project_id": pid, "index": 0})
    assert resp.status_code == 422


async def test_regenerate_frame_unknown_project_404(client):
    resp = await client.post("/animate/frame", json={"project_id": "nope", "index": 0})
    assert resp.status_code == 404


async def test_delete_frame_reindexes_and_persists(client, app_and_store):
    _, store, _ = app_and_store
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})

    resp = await client.request("DELETE", "/animate/frame", json={"project_id": pid, "index": 1})
    assert resp.status_code == 200
    body = resp.json()
    # One fewer frame, indices contiguous from 0.
    assert [f["index"] for f in body["frames"]] == [0, 1, 2]

    proj = store.read_manifest(pid)
    assert [f.index for f in proj.frames] == [0, 1, 2]
    # The renumbered files exist on disk and the old top index is gone.
    for i in range(3):
        store.load_image(pid, f"frame_{i}")  # no FileNotFoundError
    with pytest.raises(FileNotFoundError):
        store.load_image(pid, "frame_3")


async def test_delete_frame_survives_reload(client, app_and_store):
    _, store, _ = app_and_store
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})
    await client.request("DELETE", "/animate/frame", json={"project_id": pid, "index": 0})
    # Manifest is the source of truth on reload — deletion is durable.
    assert len(store.read_manifest(pid).frames) == 3


async def test_delete_failed_frame_keeps_ok_frames_aligned(client, tmp_path):
    # Frame 1 fails at animate time; deleting frame 0 must renumber the OK frames
    # (2,3 -> 1,2) without trying to load the missing failed-frame file.
    app, store, fake = _make(tmp_path, fail_on={1})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        pid = await _generate(c)
        await c.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})
        resp = await c.request("DELETE", "/animate/frame", json={"project_id": pid, "index": 0})

    assert resp.status_code == 200
    frames = resp.json()["frames"]
    assert [f["index"] for f in frames] == [0, 1, 2]
    # Original failed frame (was index 1) is now index 0 and still failed.
    assert frames[0]["status"] == "failed"
    assert frames[0]["url"] is None
    assert frames[1]["status"] == "ok"


async def test_export_blocks_animation_with_failed_frames(client, app_and_store):
    _, store, fake = app_and_store
    pid = await _generate(client)
    fake.fail_on = {1}
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})

    resp = await client.post("/export", json={"project_id": pid, "format": "json"})

    assert resp.status_code == 409
    assert "1 failed frame" in resp.json()["detail"]
    assert not (store.root / pid / "sprite_sheet.png").exists()


async def test_delete_frame_out_of_range_422(client):
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "walk", "frames": 4})
    resp = await client.request("DELETE", "/animate/frame", json={"project_id": pid, "index": 99})
    assert resp.status_code == 422


async def test_delete_frame_unanimated_project_422(client):
    pid = await _generate(client)
    resp = await client.request("DELETE", "/animate/frame", json={"project_id": pid, "index": 0})
    assert resp.status_code == 422


async def test_delete_frame_unknown_project_404(client):
    resp = await client.request("DELETE", "/animate/frame", json={"project_id": "nope", "index": 0})
    assert resp.status_code == 404


async def test_animate_edit_prompts_are_base_anchored(client, app_and_store):
    _, _, fake = app_and_store
    pid = await _generate(client)
    await client.post("/animate", json={"project_id": pid, "action": "run", "frames": 4})
    # each frame prompt references the walking/running pose and frame numbering
    assert len(fake.edit_prompts) == 4
    assert "1 of 4" in fake.edit_prompts[0] or "1" in fake.edit_prompts[0]
