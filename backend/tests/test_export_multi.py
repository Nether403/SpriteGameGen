"""Task 16 — multi-frame sprite-sheet export (JSON + XML, grid/padding options).

Builds a project, animates it to N frames, then exercises /export end-to-end and
inspects the resulting sheet + atlas.
"""
import json
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.deps import get_gemini_client, get_store
from app.main import create_app
from app.storage.project_store import ProjectStore


class FakeGemini:
    def _sprite(self):
        img = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
        img.paste(Image.new("RGBA", (20, 20), (255, 0, 0, 255)), (22, 20))
        return img

    def generate(
        self, prompt, style, reference=None, *, view_mode=None, direction=None
    ):
        return self._sprite()

    def edit(self, base_img, prompt, *, pose_reference=None):
        return self._sprite()


def _fake_remover(img: Image.Image) -> Image.Image:
    arr = np.asarray(img.convert("RGBA")).copy()
    green = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 0)
    arr[green, 3] = 0
    return Image.fromarray(arr, "RGBA")


def _read_atlas(store, pid, filename):
    return store.asset_path(pid, filename).read_text(encoding="utf-8")


@pytest.fixture
def app_and_store(tmp_path):
    store = ProjectStore(root=tmp_path)
    app = create_app(remover=_fake_remover)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_gemini_client] = lambda: FakeGemini()
    return app, store


@pytest.fixture
async def client(app_and_store):
    app, _ = app_and_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _animated_project(client, frames=4, action="walk"):
    pid = (
        await client.post("/generate", data={"prompt": "a knight", "style": "pixel"})
    ).json()["project_id"]
    resp = await client.post(
        "/animate", json={"project_id": pid, "action": action, "frames": frames}
    )
    assert resp.status_code == 200
    return pid


async def test_export_multi_frame_json_atlas_lists_all_frames(client, app_and_store):
    _, store = app_and_store
    pid = await _animated_project(client, frames=4)

    resp = await client.post("/export", json={"project_id": pid, "format": "json"})
    assert resp.status_code == 200

    atlas = json.loads(_read_atlas(store, pid, "sprite.json"))
    assert len(atlas["frames"]) == 4
    # every frame has a non-degenerate rect
    for fr in atlas["frames"]:
        assert fr["frame"]["w"] > 0 and fr["frame"]["h"] > 0


async def test_export_multi_frame_grid_cols_honored(client, app_and_store):
    _, store = app_and_store
    pid = await _animated_project(client, frames=4)

    resp = await client.post(
        "/export", json={"project_id": pid, "format": "json", "cols": 2}
    )
    assert resp.status_code == 200
    atlas = json.loads(_read_atlas(store, pid, "sprite.json"))

    # cols=2 over 4 frames => 2 distinct x columns, 2 distinct y rows
    xs = {f["frame"]["x"] for f in atlas["frames"]}
    ys = {f["frame"]["y"] for f in atlas["frames"]}
    assert len(xs) == 2
    assert len(ys) == 2


async def test_export_multi_frame_padding_expands_sheet(client, app_and_store):
    _, store = app_and_store
    pid = await _animated_project(client, frames=4)

    no_pad = (await client.post("/export", json={"project_id": pid, "cols": 4})).json()
    padded = (
        await client.post(
            "/export", json={"project_id": pid, "cols": 4, "padding": 5}
        )
    ).json()
    assert no_pad["sheet_url"] and padded["sheet_url"]

    sheet = store.load_image(pid, "sprite_sheet")
    # with padding=5 and cols=4, first frame is offset by the gutter
    atlas = json.loads(_read_atlas(store, pid, "sprite.json"))
    first = min(atlas["frames"], key=lambda f: f["index"])
    assert first["frame"]["x"] == 5
    assert first["frame"]["y"] == 5
    assert sheet.width > 0


async def test_export_multi_frame_xml(client, app_and_store):
    _, store = app_and_store
    pid = await _animated_project(client, frames=4)

    resp = await client.post("/export", json={"project_id": pid, "format": "xml"})
    assert resp.status_code == 200
    assert resp.json()["atlas_url"].split("?", 1)[0].endswith(".xml")

    root = ET.fromstring(_read_atlas(store, pid, "sprite.xml"))
    assert root.tag == "TextureAtlas"
    assert root.attrib["imagePath"] == "sprite_sheet.png"
    assert len(root.findall("SubTexture")) == 4
