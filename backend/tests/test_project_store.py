"""Filesystem project store: dirs, image round-trip, manifest, list/delete."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from PIL import Image

from app.models import Frame, Project, Style
from app.storage.project_store import ProjectStore


@pytest.fixture
def store(tmp_path):
    return ProjectStore(root=tmp_path)


def test_create_makes_directory(store, tmp_path):
    pid = store.create()
    assert isinstance(pid, str) and pid
    assert (tmp_path / pid).is_dir()
    assert (tmp_path / pid / ".sprite-project").read_text(encoding="utf-8") == pid


def test_create_returns_unique_ids(store):
    assert store.create() != store.create()


def test_save_and_load_image_roundtrip(store):
    pid = store.create()
    img = Image.new("RGBA", (8, 6), (10, 20, 30, 255))
    path = store.save_image(pid, "sprite", img)
    assert path.exists()

    loaded = store.load_image(pid, "sprite")
    assert loaded.mode == "RGBA"
    assert loaded.size == (8, 6)
    assert loaded.getpixel((0, 0)) == (10, 20, 30, 255)


def test_save_image_writes_png(store):
    pid = store.create()
    path = store.save_image(pid, "frame_0", Image.new("RGBA", (4, 4)))
    assert path.suffix == ".png"
    assert path.name == "frame_0.png"


def test_manifest_roundtrip(store):
    pid = store.create()
    project = Project(
        id=pid,
        prompt="a knight",
        style=Style.PIXEL,
        frames=[Frame(index=0, url=f"/projects/{pid}/frame_0.png")],
    )
    store.write_manifest(pid, project)

    read = store.read_manifest(pid)
    assert read == project
    assert read.style is Style.PIXEL
    assert read.frames[0].index == 0
    assert read.revision == 1


def test_read_manifest_backfills_old_metadata_without_rewriting(store, tmp_path):
    pid = store.create()
    manifest_path = tmp_path / pid / "project.json"
    manifest_path.write_text(
        json.dumps({"id": pid, "prompt": "old sprite", "style": "pixel"}),
        encoding="utf-8",
    )
    before = manifest_path.read_bytes()

    first = store.read_manifest(pid)
    second = store.read_manifest(pid)

    assert first.schema_version == 1
    assert first.revision == 0
    assert first.created_at.tzinfo == timezone.utc
    assert first.updated_at.tzinfo == timezone.utc
    assert first.created_at == second.created_at
    assert first.updated_at == second.updated_at
    assert manifest_path.read_bytes() == before


def test_write_manifest_preserves_creation_and_advances_update(store):
    pid = store.create()
    created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    project = Project(
        id=pid,
        prompt="p",
        style=Style.PIXEL,
        created_at=created,
        updated_at=created,
    )

    store.write_manifest(pid, project)

    read = store.read_manifest(pid)
    assert read.created_at == created
    assert read.updated_at > created
    assert read.revision == 1


def test_write_manifest_rejects_stale_revision(store):
    pid = store.create()
    project = Project(id=pid, prompt="first", style=Style.PIXEL)
    store.write_manifest(pid, project)

    stale = project.model_copy(deep=True)
    current = store.read_manifest(pid)
    current.prompt = "current"
    store.write_manifest(pid, current, expected_revision=1)

    stale.prompt = "stale"
    with pytest.raises(RuntimeError, match="changed during the operation"):
        store.write_manifest(pid, stale, expected_revision=1)

    assert store.read_manifest(pid).prompt == "current"


def test_commit_project_checks_revision_before_replacing_assets(store):
    pid = store.create()
    project = Project(id=pid, prompt="first", style=Style.PIXEL)
    store.commit_project(
        pid,
        project,
        expected_revision=0,
        images={"sprite": Image.new("RGBA", (2, 2), "red")},
    )
    stale = project.model_copy(deep=True)
    current = store.read_manifest(pid)
    current.prompt = "newer"
    store.write_manifest(pid, current, expected_revision=1)

    with pytest.raises(RuntimeError, match="changed during the operation"):
        store.commit_project(
            pid,
            stale,
            expected_revision=1,
            images={"sprite": Image.new("RGBA", (2, 2), "blue")},
        )

    assert store.load_image(pid, "sprite").getpixel((0, 0)) == (255, 0, 0, 255)


def test_commit_project_rolls_back_assets_when_manifest_write_fails(store, monkeypatch):
    pid = store.create()
    project = Project(id=pid, prompt="first", style=Style.PIXEL)
    store.commit_project(
        pid,
        project,
        expected_revision=0,
        images={"sprite": Image.new("RGBA", (2, 2), "red")},
    )

    def fail_manifest(*args, **kwargs):
        raise OSError("manifest disk failure")

    monkeypatch.setattr(store, "_write_manifest_unlocked", fail_manifest)
    with pytest.raises(OSError, match="manifest disk failure"):
        store.commit_project(
            pid,
            project,
            expected_revision=1,
            images={"sprite": Image.new("RGBA", (2, 2), "blue")},
        )

    assert store.load_image(pid, "sprite").getpixel((0, 0)) == (255, 0, 0, 255)


def test_list_projects(store):
    ids = {store.create() for _ in range(3)}
    for pid in ids:
        store.write_manifest(
            pid, Project(id=pid, prompt="p", style=Style.HIRES)
        )
    listed = store.list_projects()
    assert {p.id for p in listed} == ids


def test_list_projects_skips_dirs_without_manifest(store):
    pid = store.create()  # no manifest written
    assert store.list_projects() == []


def test_delete_project(store, tmp_path):
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (4, 4)))
    assert (tmp_path / pid).exists()

    store.delete_project(pid)
    assert not (tmp_path / pid).exists()


def test_delete_missing_project_is_noop(store):
    store.delete_project("does-not-exist")  # must not raise


def test_delete_rejects_unowned_directory(store, tmp_path):
    unrelated = tmp_path / "docs"
    unrelated.mkdir()

    with pytest.raises(ValueError, match="not a sprite project"):
        store.delete_project("docs")

    assert unrelated.is_dir()


def test_catalog_skips_unowned_directories(store, tmp_path):
    (tmp_path / "docs").mkdir()
    assert store.list_project_records() == []


def test_legacy_manifest_proves_directory_ownership(store, tmp_path):
    pid = "legacy"
    project_dir = tmp_path / pid
    project_dir.mkdir()
    (project_dir / "project.json").write_text(
        Project(id=pid, prompt="legacy", style=Style.PIXEL).model_dump_json(),
        encoding="utf-8",
    )

    assert store.get_project_record(pid).id == pid
    store.delete_project(pid)
    assert not project_dir.exists()


def test_manifest_id_must_match_directory(store, tmp_path):
    pid = store.create()
    (tmp_path / pid / "project.json").write_text(
        Project(id="different", prompt="bad", style=Style.PIXEL).model_dump_json(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match"):
        store.read_manifest(pid)


def test_failed_atomic_image_write_preserves_existing_file(store):
    pid = store.create()
    original = Image.new("RGBA", (4, 4), "red")
    store.save_image(pid, "sprite", original)

    class BrokenImage:
        def save(self, path: Path, *, format: str) -> None:
            path.write_bytes(b"partial")
            raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        store.save_image(pid, "sprite", BrokenImage())

    assert store.load_image(pid, "sprite").getpixel((0, 0)) == (255, 0, 0, 255)
    assert not list((store.root / pid).glob("*.tmp"))


def test_asset_path_rejects_symlink_escape(store, tmp_path):
    pid = store.create()
    outside = tmp_path.parent / "outside-sprite-test.png"
    outside.write_bytes(b"outside")
    link = tmp_path / pid / "linked.png"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable")

    with pytest.raises(ValueError, match="outside the project root"):
        store.asset_path(pid, "linked.png")


def test_read_manifest_missing_raises(store):
    pid = store.create()
    with pytest.raises(FileNotFoundError):
        store.read_manifest(pid)


def test_load_missing_image_raises(store):
    pid = store.create()
    with pytest.raises(FileNotFoundError):
        store.load_image(pid, "nope")


def test_rejects_unsafe_ids(store):
    # path traversal / separators must be rejected in image + manifest ops
    with pytest.raises(ValueError):
        store.save_image("../evil", "x", Image.new("RGBA", (1, 1)))
    with pytest.raises(ValueError):
        store.save_image("ok", "../../x", Image.new("RGBA", (1, 1)))
