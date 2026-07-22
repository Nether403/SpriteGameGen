"""Strict, non-executable action-pack catalog."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ACTION_PACK_BYTES = 512 * 1024
ACTION_PACK_FORMAT = "sprite-action-pack"
ACTION_PACK_VERSION = 1


class ActionGuide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^(pose|baseline)$")
    points: list[tuple[float, float]] = Field(default_factory=list, max_length=64)

    @field_validator("points")
    @classmethod
    def normalized_finite_points(
        cls, points: list[tuple[float, float]]
    ) -> list[tuple[float, float]]:
        if any(
            not math.isfinite(value) or not 0 <= value <= 1
            for point in points
            for value in point
        ):
            raise ValueError("guide points must be finite values from 0 to 1")
        return points


class ActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    version: str = Field(default="1", min_length=1, max_length=32)
    motion: str = Field(min_length=1, max_length=2000)
    min_frames: int = Field(ge=1, le=64)
    max_frames: int = Field(ge=1, le=64)
    default_frames: int = Field(ge=1, le=64)
    default_fps: int = Field(default=8, ge=1, le=60)
    loop: bool = True
    phases: list[str] = Field(default_factory=list, max_length=64)
    change_directive: str | None = Field(default=None, max_length=2000)
    guides: list[ActionGuide] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ActionDefinition":
        if not self.min_frames <= self.default_frames <= self.max_frames:
            raise ValueError("default_frames must be within min/max bounds")
        return self

    def digest(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class ActionPack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = Field(default=ACTION_PACK_FORMAT, pattern=r"^sprite-action-pack$")
    format_version: int = Field(default=ACTION_PACK_VERSION, ge=1, le=1)
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    version: str = Field(min_length=1, max_length=32)
    actions: list[ActionDefinition] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def unique_actions(self) -> "ActionPack":
        ids = [action.id for action in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("action IDs must be unique within a pack")
        return self


class ActionCatalog(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    actions: dict[str, ActionDefinition]
    references: dict[str, str]
    errors: list[str] = Field(default_factory=list)

    def get(self, action_id: str) -> ActionDefinition:
        try:
            return self.actions[action_id]
        except KeyError as exc:
            raise KeyError(action_id) from exc


def load_action_catalog(external_dir: str | Path | None = None) -> ActionCatalog:
    builtin = load_pack(Path(__file__).with_name("data") / "actions.v1.json")
    actions = {action.id: action for action in builtin.actions}
    refs = {action.id: f"{builtin.id}@{builtin.version}:{action.id}" for action in builtin.actions}
    reserved_actions = set(actions)
    reserved_packs = {builtin.id}
    errors: list[str] = []
    if external_dir is None:
        return ActionCatalog(actions=actions, references=refs, errors=errors)
    root = Path(external_dir)
    if not root.exists():
        return ActionCatalog(actions=actions, references=refs, errors=errors)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("ACTION_PACKS_DIR must be a regular directory")
    accepted_pack_ids = set(reserved_packs)
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.suffix.lower() != ".json":
            continue
        if path.is_symlink() or not path.is_file():
            errors.append(f"{path.name}: not a regular JSON file")
            continue
        try:
            pack = load_pack(path)
            ids = {action.id for action in pack.actions}
            if pack.id in accepted_pack_ids or ids & reserved_actions or ids & set(actions):
                raise ValueError("pack or action ID collides with an installed ID")
            for action in pack.actions:
                actions[action.id] = action
                refs[action.id] = f"{pack.id}@{pack.version}:{action.id}"
            accepted_pack_ids.add(pack.id)
        except (OSError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
    return ActionCatalog(actions=actions, references=refs, errors=errors)


def load_pack(path: Path) -> ActionPack:
    size = path.stat().st_size
    if size > MAX_ACTION_PACK_BYTES:
        raise ValueError(f"action pack exceeds {MAX_ACTION_PACK_BYTES} bytes")
    data = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError(f"non-finite JSON value: {value}")
        ),
    )
    return ActionPack.model_validate(data)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result
