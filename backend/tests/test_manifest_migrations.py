import json

import pytest
from PIL import Image

from app.models import AnimationClip, Frame, Project, Style
from app.storage.project_store import ProjectStore


def test_legacy_read_migrates_in_memory_without_rewriting(tmp_path):
    store = ProjectStore(tmp_path)
    project_id = store.create()
    manifest = tmp_path / project_id / "project.json"
    manifest.write_text(
        json.dumps(
            {
                "id": project_id,
                "prompt": "runner",
                "style": "pixel",
                "action": "run",
                "fps": 12,
                "frames": [{"index": 0}, {"index": 1}],
            }
        ),
        encoding="utf-8",
    )
    before = manifest.read_bytes()

    project = store.read_manifest(project_id)

    assert project.schema_version == 2
    assert project.action == "run"
    assert project.fps == 12
    assert [frame.index for frame in project.frames] == [0, 1]
    assert manifest.read_bytes() == before


def test_first_legacy_mutation_writes_only_v2_fields(tmp_path):
    store = ProjectStore(tmp_path)
    project_id = store.create()
    manifest = tmp_path / project_id / "project.json"
    manifest.write_text(
        json.dumps(
            {
                "id": project_id,
                "prompt": "runner",
                "style": "pixel",
                "action": "run",
                "frames": [{"index": 0}],
            }
        ),
        encoding="utf-8",
    )
    project = store.read_manifest(project_id)

    store.write_manifest(project_id, project, expected_revision=0)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["schema_version"] == 2
    assert data["active_clip_id"] in data["clips"]
    assert "frames" not in data
    assert "action" not in data
    assert "fps" not in data


def test_future_manifest_is_rejected(tmp_path):
    store = ProjectStore(tmp_path)
    project_id = store.create()
    (tmp_path / project_id / "project.json").write_text(
        json.dumps(
            {
                "id": project_id,
                "prompt": "future",
                "style": "pixel",
                "schema_version": 99,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="newer than supported"):
        store.read_manifest(project_id)


def test_non_contiguous_legacy_frames_are_rejected(tmp_path):
    store = ProjectStore(tmp_path)
    project_id = store.create()
    (tmp_path / project_id / "project.json").write_text(
        json.dumps(
            {
                "id": project_id,
                "prompt": "broken",
                "style": "pixel",
                "action": "run",
                "frames": [{"index": 1}],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="contiguous"):
        store.read_manifest(project_id)


def test_blob_commit_is_revision_checked_and_atomic(tmp_path):
    store = ProjectStore(tmp_path)
    project_id = store.create()
    project = Project(id=project_id, prompt="sprite", style=Style.PIXEL)
    store.commit_project(
        project_id,
        project,
        expected_revision=0,
        images={"sprite": Image.new("RGBA", (1, 1))},
    )

    store.commit_assets(
        project_id,
        expected_revision=1,
        blobs={"frames.zip": b"archive"},
    )

    assert store.asset_path(project_id, "frames.zip").read_bytes() == b"archive"
