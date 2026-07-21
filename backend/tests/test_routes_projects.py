"""Project catalog and resume API tests."""
import json

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.deps import get_store
from app.main import create_app
from app.models import Frame, FrameStatus, Project, Style
from app.storage.project_store import ProjectStore


@pytest.fixture
def app_and_store(tmp_path):
    store = ProjectStore(root=tmp_path)
    app = create_app()
    app.dependency_overrides[get_store] = lambda: store
    return app, store


@pytest.fixture
async def client(app_and_store):
    app, _ = app_and_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _write_project(store: ProjectStore, *, action: str | None = None) -> str:
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (8, 8), (255, 0, 0, 255)))
    frames = [Frame(index=0, url=f"/projects/{pid}/sprite.png")]
    if action is not None:
        store.save_image(pid, "frame_0", Image.new("RGBA", (8, 8), (255, 0, 0, 255)))
        store.save_image(pid, "frame_1", Image.new("RGBA", (8, 8), (255, 0, 0, 255)))
        frames = [
            Frame(index=0, url=f"/projects/{pid}/frame_0.png"),
            Frame(index=1, url=None, status=FrameStatus.FAILED),
        ]
    store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a knight",
            style=Style.PIXEL,
            frames=frames,
            action=action,
            fps=8 if action else None,
        ),
    )
    return pid


async def test_list_and_detail_return_resume_ready_project_data(client, app_and_store):
    _, store = app_and_store
    pid = _write_project(store, action="walk")

    listed = await client.get("/projects")
    assert listed.status_code == 200
    summary = next(item for item in listed.json() if item["id"] == pid)
    assert summary["prompt_preview"] == "a knight"
    assert summary["frame_count"] == 2
    assert summary["ok_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["health"] == "ready"
    assert summary["resume_available"] is True
    assert "v=" in summary["thumbnail_url"]

    detail = await client.get(f"/projects/{pid}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == pid
    assert body["action"] == "walk"
    assert body["fps"] == 8
    assert body["sprite_url"].split("?", 1)[0].endswith("/sprite.png")
    assert "v=" in body["sprite_url"]
    assert body["frames"][0]["url"].split("?", 1)[0].endswith("frame_0.png")
    assert body["frames"][1]["url"] is None


async def test_catalog_isolates_incomplete_and_corrupt_projects(client, app_and_store):
    _, store = app_and_store
    valid_id = _write_project(store)
    incomplete_id = store.create()
    corrupt_id = store.create()
    (store.root / corrupt_id / "project.json").write_text("{not-json", encoding="utf-8")

    listed = await client.get("/projects")
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()}
    assert by_id[valid_id]["health"] == "ready"
    assert by_id[incomplete_id]["health"] == "incomplete"
    assert by_id[incomplete_id]["resume_available"] is False
    assert by_id[corrupt_id]["health"] == "corrupt"
    assert by_id[corrupt_id]["resume_available"] is False

    assert (await client.get(f"/projects/{incomplete_id}")).status_code == 409
    assert (await client.get(f"/projects/{corrupt_id}")).status_code == 409


async def test_project_detail_and_delete_report_missing_projects(client, app_and_store):
    _, store = app_and_store
    pid = _write_project(store)

    assert (await client.get("/projects/missing")).status_code == 404
    assert (await client.delete("/projects/missing")).status_code == 404

    deleted = await client.delete(f"/projects/{pid}")
    assert deleted.status_code == 200
    assert not (store.root / pid).exists()


async def test_old_manifest_is_resumeable_with_derived_metadata(client, app_and_store):
    _, store = app_and_store
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (8, 8), (255, 0, 0, 255)))
    (store.root / pid / "project.json").write_text(
        json.dumps(
            {
                "id": pid,
                "prompt": "legacy sprite",
                "style": "hires",
                "frames": [{"index": 0, "url": f"/projects/{pid}/sprite.png"}],
            }
        ),
        encoding="utf-8",
    )

    response = await client.get(f"/projects/{pid}")
    assert response.status_code == 200
    assert response.json()["prompt"] == "legacy sprite"
    assert response.json()["schema_version"] == 1
    assert response.json()["resume_available"] is True
