"""Filesystem project store: dirs, image round-trip, manifest, list/delete."""
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
