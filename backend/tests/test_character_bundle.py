from io import BytesIO
import json
import zipfile

from PIL import Image

from app.character_bundle import build_character_bundle
from app.models import AnimationClip, Direction, Frame, FrameStatus, Project, Style
from app.storage.project_store import ProjectStore


def _project(store: ProjectStore) -> Project:
    project_id = store.create()
    clip = AnimationClip(
        id="walk-a",
        name="Walk",
        action="walk",
        direction=Direction.RIGHT,
        fps=8,
        frames=[
            Frame(
                index=0,
                rendered_filename="clip_walk-a_0000.png",
                source_filename="source_clip_walk-a_0000.png",
                duration_ms=125,
            ),
            Frame(
                index=1,
                rendered_filename="clip_walk-a_0001.png",
                source_filename="source_clip_walk-a_0001.png",
                duration_ms=150,
            ),
        ],
    )
    project = Project(
        id=project_id,
        prompt="must not enter bundle",
        style=Style.PIXEL,
        clips={clip.id: clip},
        active_clip_id=clip.id,
    )
    image = Image.new("RGBA", (2, 2), "red")
    store.commit_project(
        project_id,
        project,
        expected_revision=0,
        images={
            "sprite": image,
            "source_sprite": image,
            "clip_walk-a_0000": image,
            "source_clip_walk-a_0000": image,
            "clip_walk-a_0001": image,
            "source_clip_walk-a_0001": image,
        },
    )
    return project


def test_bundle_is_byte_identical_and_contains_checksums(tmp_path):
    store = ProjectStore(tmp_path)
    project = _project(store)

    first = build_character_bundle(store, project)
    second = build_character_bundle(store, project)

    assert first == second
    with zipfile.ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        manifest = json.loads(archive.read("character.bundle.json"))
        assert manifest["format"] == "sprite-character-bundle"
        assert manifest["format_version"] == 1
        assert "prompt" not in manifest
        assert archive.read("SHA256SUMS")


def test_godot_profile_contains_resources_and_importer(tmp_path):
    store = ProjectStore(tmp_path)
    project = _project(store)

    payload = build_character_bundle(
        store, project, engine_profile="godot4_animatedsprite2d"
    )

    with zipfile.ZipFile(BytesIO(payload)) as archive:
        assert "character_sprite_frames.tres" in archive.namelist()
        assert "character_animated_sprite_2d.tscn" in archive.namelist()
        assert "import_character_bundle.gd" in archive.namelist()
        assert b'&"Walk"' in archive.read("character_sprite_frames.tres")


def test_single_clip_scope_ignores_unselected_failure_but_all_enabled_rejects(tmp_path):
    store = ProjectStore(tmp_path)
    project = _project(store)
    failed = AnimationClip(
        id="broken",
        name="Broken",
        action="run",
        frames=[Frame(index=0, status=FrameStatus.FAILED)],
    )
    project.clips[failed.id] = failed

    assert build_character_bundle(store, project, scope="one", clip_id="walk-a")
    import pytest
    from app.character_bundle import CharacterBundleError

    with pytest.raises(CharacterBundleError, match="failed"):
        build_character_bundle(store, project, scope="all_enabled")
