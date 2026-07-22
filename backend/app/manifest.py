"""Pure manifest version dispatch and legacy-to-V2 migration."""
from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any

from pydantic import ValidationError

from app.models import (
    AnimationClip,
    Direction,
    Frame,
    ImageProviderName,
    MANIFEST_SCHEMA_VERSION,
    Project,
)


class ManifestVersionError(ValueError):
    pass


def load_manifest(data: dict[str, Any], *, fallback_time: datetime) -> Project:
    """Validate V2 or migrate V1 in memory without mutating ``data``."""

    version = data.get("schema_version", 1)
    if not isinstance(version, int):
        raise ManifestVersionError("manifest schema_version must be an integer")
    if version > MANIFEST_SCHEMA_VERSION:
        raise ManifestVersionError(
            f"manifest schema version {version} is newer than supported version "
            f"{MANIFEST_SCHEMA_VERSION}"
        )
    if version == MANIFEST_SCHEMA_VERSION:
        return Project.model_validate(data)
    if version != 1:
        raise ManifestVersionError(f"unsupported manifest schema version {version}")
    return migrate_v1(data, fallback_time=fallback_time)


def migrate_v1(data: dict[str, Any], *, fallback_time: datetime) -> Project:
    """Return a canonical V2 projection of a legacy flat manifest."""

    allowed = {
        "id", "prompt", "enhanced_prompt", "prompt_source", "image_provider",
        "style", "view_mode", "direction", "schema_version", "revision",
        "created_at", "updated_at", "frames", "action", "fps",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"legacy manifest contains unknown fields: {sorted(unknown)!r}")
    raw_frames = data.get("frames", [])
    if not isinstance(raw_frames, list):
        raise ValueError("legacy frames must be a list")
    indices = [item.get("index") for item in raw_frames if isinstance(item, dict)]
    if len(indices) != len(raw_frames) or indices != list(range(len(raw_frames))):
        raise ValueError("legacy frame indices must be contiguous from zero")

    provider = ImageProviderName(data.get("image_provider", "gemini"))
    direction = Direction(data.get("direction", "left"))
    clips: dict[str, AnimationClip] = {}
    active_clip_id = None
    action = data.get("action")
    if action:
        clip_id = f"legacy-{uuid.uuid5(uuid.NAMESPACE_URL, str(data['id'])).hex[:12]}"
        frames = []
        for item in raw_frames:
            frame = Frame.model_validate(item)
            frame.source_filename = f"frame_{frame.index}.png"
            frame.rendered_filename = f"frame_{frame.index}.png"
            frames.append(frame)
        clip = AnimationClip(
            id=clip_id,
            name=str(action).replace("_", " ").title(),
            action=str(action),
            direction=direction,
            fps=int(data.get("fps") or 8),
            frames=frames,
            image_provider=provider,
            created_at=data.get("created_at", fallback_time),
            updated_at=data.get("updated_at", fallback_time),
        )
        clips[clip_id] = clip
        active_clip_id = clip_id

    payload = {
        "id": data["id"],
        "prompt": data["prompt"],
        "enhanced_prompt": data.get("enhanced_prompt"),
        "prompt_source": data.get("prompt_source", "raw"),
        "image_provider": provider,
        "style": data["style"],
        "view_mode": data.get("view_mode", "side_scroller"),
        "direction": direction,
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "revision": data.get("revision", 0),
        "created_at": data.get("created_at", fallback_time),
        "updated_at": data.get("updated_at", fallback_time),
        "clips": clips,
        "active_clip_id": active_clip_id,
    }
    try:
        return Project.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("legacy manifest is malformed") from exc
