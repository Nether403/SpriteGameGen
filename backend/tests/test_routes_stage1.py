"""Stage 1 route tests: /generate, /export, projects list/delete (fake Gemini)."""
import io

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.deps import get_gemini_client, get_store
from app.main import create_app
from app.models import Direction, Style, ViewMode
from app.storage.project_store import ProjectStore


class FakeGemini:
    """Returns a sprite: opaque disk on a solid (removable) background, with margins."""

    def __init__(self):
        self.generate_calls = []

    def generate(
        self, prompt, style, reference=None, *, view_mode=None, direction=None
    ):
        self.generate_calls.append(
            {
                "prompt": prompt,
                "style": style,
                "reference": reference,
                "view_mode": view_mode,
                "direction": direction,
            }
        )
        img = Image.new("RGBA", (64, 64), (0, 255, 0, 255))  # green bg
        # draw an opaque red square in the middle (the "subject")
        block = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
        img.paste(block, (22, 20))
        return img

    def edit(self, base_img, prompt):  # not used in Stage 1
        raise NotImplementedError


def _fake_remover(img: Image.Image) -> Image.Image:
    """Green-screen remover: makes pure-green pixels transparent."""
    arr = np.asarray(img.convert("RGBA")).copy()
    green = (arr[:, :, 0] == 0) & (arr[:, :, 1] == 255) & (arr[:, :, 2] == 0)
    arr[green, 3] = 0
    return Image.fromarray(arr, "RGBA")


@pytest.fixture
def app_and_store(tmp_path, monkeypatch):
    store = ProjectStore(root=tmp_path)
    fake = FakeGemini()

    app = create_app(remover=_fake_remover)
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_gemini_client] = lambda: fake
    return app, store, fake


@pytest.fixture
async def client(app_and_store):
    app, _, _ = app_and_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_generate_returns_project_and_sprite_url(client, app_and_store):
    _, store, fake = app_and_store
    resp = await client.post("/generate", data={"prompt": "a knight", "style": "pixel"})
    assert resp.status_code == 200
    body = resp.json()
    assert "project_id" in body and "sprite_url" in body
    assert body["sprite_url"].split("?", 1)[0].endswith(".png")
    assert "v=" in body["sprite_url"]

    # gemini was asked with the right style
    assert fake.generate_calls[0]["style"] is Style.PIXEL

    # saved sprite is RGBA and trimmed (bg removed -> cropped to the 20x20 subject)
    sprite = store.load_image(body["project_id"], "sprite")
    assert sprite.mode == "RGBA"
    assert sprite.size == (20, 20)


async def test_generate_hires_skips_quantize(client, app_and_store):
    _, store, fake = app_and_store
    resp = await client.post("/generate", data={"prompt": "a knight", "style": "hires"})
    assert resp.status_code == 200
    assert fake.generate_calls[0]["style"] is Style.HIRES


async def test_generate_persists_manifest(client, app_and_store):
    _, store, _ = app_and_store
    body = (await client.post("/generate", data={"prompt": "p", "style": "pixel"})).json()
    project = store.read_manifest(body["project_id"])
    assert project.prompt == "p"
    assert len(project.frames) == 1
    assert project.frames[0].index == 0
    assert project.enhanced_prompt is None
    assert project.prompt_source.value == "raw"


async def test_generate_uses_and_persists_explicit_enhanced_prompt(
    client, app_and_store
):
    _, store, fake = app_and_store
    response = await client.post(
        "/generate",
        data={
            "prompt": "a knight",
            "enhanced_prompt": "a silver-armored knight with a bold silhouette",
            "style": "pixel",
        },
    )

    assert response.status_code == 200
    project = store.read_manifest(response.json()["project_id"])
    assert project.prompt == "a knight"
    assert project.enhanced_prompt == "a silver-armored knight with a bold silhouette"
    assert project.prompt_source.value == "enhanced"
    assert fake.generate_calls[-1]["prompt"] == project.enhanced_prompt


async def test_generate_persists_camera_and_direction(client, app_and_store):
    _, store, fake = app_and_store
    response = await client.post(
        "/generate",
        data={
            "prompt": "p",
            "style": "pixel",
            "view_mode": "top_down_2_5d",
            "direction": "up_left",
        },
    )

    assert response.status_code == 200
    project = store.read_manifest(response.json()["project_id"])
    assert project.view_mode is ViewMode.TOP_DOWN_2_5D
    assert project.direction is Direction.UP_LEFT
    assert fake.generate_calls[-1]["view_mode"] is ViewMode.TOP_DOWN_2_5D
    assert fake.generate_calls[-1]["direction"] is Direction.UP_LEFT


async def test_generate_rejects_invalid_camera_direction_before_model_call(
    client, app_and_store
):
    _, store, fake = app_and_store
    before = len(fake.generate_calls)

    response = await client.post(
        "/generate",
        data={
            "prompt": "p",
            "style": "pixel",
            "view_mode": "side_scroller",
            "direction": "up",
        },
    )

    assert response.status_code == 422
    assert len(fake.generate_calls) == before
    assert list(store.root.iterdir()) == []


async def test_generate_rejects_empty_prompt(client):
    resp = await client.post("/generate", data={"prompt": "  ", "style": "pixel"})
    assert resp.status_code == 422


async def test_export_single_frame_returns_sheet_and_atlas(client, app_and_store):
    _, store, _ = app_and_store
    pid = (await client.post("/generate", data={"prompt": "p", "style": "pixel"})).json()["project_id"]

    resp = await client.post("/export", json={"project_id": pid, "format": "json"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sheet_url"].split("?", 1)[0].endswith("sprite_sheet.png")
    assert body["atlas_url"].split("?", 1)[0].endswith(".json")
    assert "v=" in body["sheet_url"] and "v=" in body["atlas_url"]

    # sheet + atlas were written to the project dir
    sheet = store.load_image(pid, "sprite_sheet")
    assert sheet.mode == "RGBA"


async def test_export_xml_format(client, app_and_store):
    _, store, _ = app_and_store
    pid = (await client.post("/generate", data={"prompt": "p", "style": "pixel"})).json()["project_id"]
    resp = await client.post("/export", json={"project_id": pid, "format": "xml"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["atlas_url"].split("?", 1)[0].endswith(".xml")
    assert "v=" in body["atlas_url"]


async def test_export_unknown_project_404(client):
    resp = await client.post("/export", json={"project_id": "deadbeef", "format": "json"})
    assert resp.status_code == 404


async def test_list_and_delete_projects(client, app_and_store):
    _, store, _ = app_and_store
    pid = (await client.post("/generate", data={"prompt": "p", "style": "pixel"})).json()["project_id"]

    listed = (await client.get("/projects")).json()
    assert any(p["id"] == pid for p in listed)

    resp = await client.delete(f"/projects/{pid}")
    assert resp.status_code == 200
    assert all(p["id"] != pid for p in (await client.get("/projects")).json())


async def test_oversized_upload_rejected(client, app_and_store):
    app, _, _ = app_and_store
    # multipart generate with an oversized file
    big = b"\x00" * (11 * 1024 * 1024)
    resp = await client.post(
        "/generate",
        data={"prompt": "a knight", "style": "pixel"},
        files={"reference": ("big.png", io.BytesIO(big), "image/png")},
    )
    assert resp.status_code == 413
