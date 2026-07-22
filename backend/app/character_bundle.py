"""Deterministic engine-neutral character bundle V1 exporter."""
from __future__ import annotations

from datetime import datetime
import hashlib
from io import BytesIO
import json
from pathlib import Path
import zipfile
from PIL import Image

from pydantic import BaseModel, ConfigDict, Field

from app.models import AnimationClip, FrameStatus, LoopMode, Project
from app.storage.project_store import ProjectStore
from app.pipeline.frame_render import compose

BUNDLE_FORMAT = "sprite-character-bundle"
BUNDLE_VERSION = 1


class BundleFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0)
    path: str
    duration_ms: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(default=1, ge=1)
    height: int = Field(default=1, ge=1)


class BundleClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    action: str
    direction: str
    loop_mode: LoopMode
    loop_start: int
    loop_end: int | None
    frames: list[BundleFrame]


class CharacterBundleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = BUNDLE_FORMAT
    format_version: int = BUNDLE_VERSION
    project_id: str
    project_revision: int
    pivot: tuple[float, float]
    baseline: int
    clips: list[BundleClip]
    engine_profile: str | None = None


class CharacterBundleError(ValueError):
    pass


def build_character_bundle(
    store: ProjectStore,
    project: Project,
    *,
    scope: str = "active",
    clip_id: str | None = None,
    engine_profile: str | None = None,
) -> bytes:
    clips = _select_clips(project, scope=scope, clip_id=clip_id)
    max_width = 1
    max_height = 1
    for selected_clip in clips:
        for selected_frame in selected_clip.frames:
            if not selected_frame.enabled or not selected_frame.rendered_filename:
                continue
            with Image.open(
                store.asset_path(project.id, selected_frame.rendered_filename)
            ) as probe:
                max_width = max(max_width, probe.width)
                max_height = max(max_height, probe.height)
    files: dict[str, bytes] = {}
    bundle_clips: list[BundleClip] = []
    for clip in clips:
        failed = [
            frame.index
            for frame in clip.frames
            if frame.enabled and frame.status is FrameStatus.FAILED
        ]
        if failed:
            raise CharacterBundleError(
                f"clip {clip.id!r} has enabled failed frames: {failed}"
            )
        bundle_frames = []
        for frame in clip.frames:
            if not frame.enabled:
                continue
            if not frame.rendered_filename:
                raise CharacterBundleError(
                    f"clip {clip.id!r} frame {frame.index} has no rendered asset"
                )
            archive_path = f"frames/{clip.id}/{frame.index:04d}.png"
            original = store.asset_path(project.id, frame.rendered_filename).read_bytes()
            with Image.open(BytesIO(original)) as decoded:
                normalized = compose(
                    decoded.convert("RGBA"), (max_width, max_height)
                )
            encoded = BytesIO()
            normalized.save(encoded, format="PNG", optimize=False)
            payload = encoded.getvalue()
            digest = hashlib.sha256(payload).hexdigest()
            files[archive_path] = payload
            bundle_frames.append(
                BundleFrame(
                    index=frame.index,
                    path=archive_path,
                    duration_ms=frame.duration_ms or max(1, round(1000 / clip.fps)),
                    sha256=digest,
                    width=max_width,
                    height=max_height,
                )
            )
        if not bundle_frames:
            raise CharacterBundleError(f"clip {clip.id!r} has no enabled frames")
        bundle_clips.append(
            BundleClip(
                id=clip.id,
                name=clip.name,
                action=clip.action,
                direction=clip.direction.value,
                loop_mode=clip.loop_mode,
                loop_start=clip.loop_start,
                loop_end=clip.loop_end,
                frames=bundle_frames,
            )
        )

    manifest = CharacterBundleManifest(
        project_id=project.id,
        project_revision=project.revision,
        pivot=(project.pivot_x, project.pivot_y),
        baseline=project.baseline,
        clips=bundle_clips,
        engine_profile=engine_profile,
    )
    files["character.bundle.json"] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if engine_profile is not None:
        if engine_profile != "godot4_animatedsprite2d":
            raise CharacterBundleError(f"unknown engine profile: {engine_profile!r}")
        files.update(
            _godot_files(
                bundle_clips,
                pivot=(project.pivot_x, project.pivot_y),
                baseline=project.baseline,
            )
        )

    checksummed = sorted(
        (name, hashlib.sha256(payload).hexdigest())
        for name, payload in files.items()
    )
    files["SHA256SUMS"] = "".join(
        f"{digest}  {name}\n" for name, digest in checksummed
    ).encode("utf-8")
    return _deterministic_zip(files)


def _select_clips(project: Project, *, scope: str, clip_id: str | None) -> list[AnimationClip]:
    if scope == "all_enabled":
        clips = [clip for clip in project.clips.values() if clip.enabled]
    elif scope in {"active", "one"}:
        selected = clip_id or project.active_clip_id
        clips = [project.clips[selected]] if selected in project.clips else []
    else:
        raise CharacterBundleError("scope must be active, one, or all_enabled")
    if not clips:
        raise CharacterBundleError("bundle scope selected no clips")
    return sorted(clips, key=lambda clip: clip.id)


def _deterministic_zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[name], compresslevel=9)
    return output.getvalue()


def _godot_files(
    clips: list[BundleClip],
    *,
    pivot: tuple[float, float] = (0.5, 1.0),
    baseline: int = 0,
) -> dict[str, bytes]:
    ext_resources: list[str] = []
    animations: list[str] = []
    resource_number = 1
    used_names: set[str] = set()
    for clip in clips:
        entries_by_index: dict[int, str] = {}
        for frame in clip.frames:
            ext_id = f"tex_{resource_number}"
            ext_resources.append(
                f'[ext_resource type="Texture2D" path="res://{frame.path}" id="{ext_id}"]'
            )
            entries_by_index[frame.index] = (
                '{"duration": %.6f, "texture": ExtResource("%s")}'
                % (frame.duration_ms / 1000, ext_id)
            )
            resource_number += 1
        safe_name = "".join(
            character if character.isalnum() or character in " _-" else "_"
            for character in clip.name
        ).strip() or clip.id
        if safe_name in used_names:
            safe_name = f"{safe_name}_{clip.id}"
        used_names.add(safe_name)
        full_entries = [entries_by_index[frame.index] for frame in clip.frames]
        partial_loop = (
            clip.loop_mode is LoopMode.LOOP
            and clip.loop_end is not None
            and (clip.loop_start > 0 or clip.loop_end < len(clip.frames) - 1)
        )
        animations.append(
            '{"frames": [%s], "loop": %s, "name": &"%s", "speed": 1.0}'
            % (
                ", ".join(full_entries),
                "true" if clip.loop_mode is LoopMode.LOOP and not partial_loop else "false",
                safe_name,
            )
        )
        if partial_loop:
            loop_entries = [
                entries_by_index[frame.index]
                for frame in clip.frames
                if clip.loop_start <= frame.index <= (clip.loop_end or 0)
            ]
            animations.append(
                '{"frames": [%s], "loop": true, "name": &"%s_loop", "speed": 1.0}'
                % (", ".join(loop_entries), safe_name)
            )
    tres = "\n".join(
        [
            f'[gd_resource type="SpriteFrames" load_steps={resource_number} format=3]',
            "",
            *ext_resources,
            "",
            "[resource]",
            "animations = [%s]" % ", ".join(animations),
            "",
        ]
    )
    first_frame = clips[0].frames[0]
    offset_x = (0.5 - pivot[0]) * first_frame.width
    offset_y = (0.5 - pivot[1]) * first_frame.height + baseline
    scene = f"""[gd_scene load_steps=2 format=3]

[ext_resource type="SpriteFrames" path="res://character_sprite_frames.tres" id="1"]

[node name="CharacterAnimatedSprite2D" type="AnimatedSprite2D"]
sprite_frames = ExtResource("1")
centered = true
offset = Vector2({offset_x:.6f}, {offset_y:.6f})
"""
    importer = """@tool
extends EditorScript

func _run() -> void:
    print("SpriteGameGen bundle resources are ready to import from the extracted folder.")
    get_editor_interface().scan_sources()
"""
    return {
        "character_sprite_frames.tres": tres.encode("utf-8"),
        "character_animated_sprite_2d.tscn": scene.encode("utf-8"),
        "import_character_bundle.gd": importer.encode("utf-8"),
    }
