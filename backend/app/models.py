"""Pydantic domain models (spec §3).

These describe the persisted project manifest and the export request shape.
Kept intentionally small; Stage 2 extends ``Frame`` and adds ``AnimateRequest``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


class Style(str, Enum):
    """Art style — differs mainly in one post-processing step (quantize)."""

    PIXEL = "pixel"
    HIRES = "hires"


class ViewMode(str, Enum):
    """Camera perspective used by the base sprite and all derived frames."""

    SIDE_SCROLLER = "side_scroller"
    TOP_DOWN_2_5D = "top_down_2_5d"


class Direction(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"
    UP_LEFT = "up_left"
    UP_RIGHT = "up_right"
    DOWN_LEFT = "down_left"
    DOWN_RIGHT = "down_right"


class PromptSource(str, Enum):
    RAW = "raw"
    ENHANCED = "enhanced"


_DIRECTIONS_BY_VIEW: dict[ViewMode, tuple[Direction, ...]] = {
    ViewMode.SIDE_SCROLLER: (Direction.LEFT, Direction.RIGHT),
    ViewMode.TOP_DOWN_2_5D: tuple(Direction),
}


def directions_for(view_mode: ViewMode) -> tuple[Direction, ...]:
    """Return the authoritative directions allowed for a camera mode."""

    return _DIRECTIONS_BY_VIEW[view_mode]


def validate_direction(view_mode: ViewMode, direction: Direction) -> Direction:
    """Validate a mode/direction pair and return the direction for composition."""

    if direction not in directions_for(view_mode):
        raise ValueError(
            f"direction '{direction.value}' is not valid for view mode "
            f"'{view_mode.value}'"
        )
    return direction


class FrameStatus(str, Enum):
    """A generated frame either succeeded or failed (partial-failure tolerant)."""

    OK = "ok"
    FAILED = "failed"


class ProjectHealth(str, Enum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"


class ExportFormat(str, Enum):
    JSON = "json"
    XML = "xml"


class Frame(BaseModel):
    """One frame of an animation (a single static sprite is one frame at index 0)."""

    index: int = Field(ge=0)
    url: str | None = None
    status: FrameStatus = FrameStatus.OK


class Project(BaseModel):
    """Filesystem project manifest, persisted as ``project.json``.

    ``action`` and ``fps`` are set once a project has been animated (Stage 2);
    a freshly generated single-sprite project leaves them unset.
    """

    id: str
    prompt: str
    enhanced_prompt: str | None = None
    prompt_source: PromptSource = PromptSource.RAW
    style: Style
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER
    direction: Direction = Direction.LEFT
    schema_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frames: list[Frame] = Field(default_factory=list)
    action: str | None = None
    fps: int | None = Field(default=None, ge=1, le=60)

    @model_validator(mode="after")
    def validate_camera_direction(self) -> Project:
        validate_direction(self.view_mode, self.direction)
        if self.prompt_source is PromptSource.ENHANCED and not self.enhanced_prompt:
            raise ValueError("enhanced prompt source requires enhanced_prompt")
        return self


class ProjectSummary(BaseModel):
    """Compact catalog entry used by the project browser."""

    id: str
    prompt_preview: str | None = None
    style: Style | None = None
    view_mode: ViewMode | None = None
    direction: Direction | None = None
    thumbnail_url: str | None = None
    action: str | None = None
    fps: int | None = None
    frame_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    created_at: datetime
    updated_at: datetime
    health: ProjectHealth
    resume_available: bool = False


class ProjectDetail(Project):
    """Full project state with browser metadata and fresh asset URLs."""

    sprite_url: str | None = None
    health: ProjectHealth = ProjectHealth.READY
    resume_available: bool = True


class ExportOptions(BaseModel):
    """Options for packing frames into a sheet + atlas."""

    format: ExportFormat = ExportFormat.JSON
    padding: int = Field(default=0, ge=0)
    cols: int | None = Field(default=None, ge=1)  # None => auto near-square grid


class AnimateRequest(BaseModel):
    """Request to expand a project's base sprite into an animation (spec §3).

    ``action`` is a preset name (walk/run/idle/…) validated against the preset
    table at the route layer. ``frames`` is optional: when omitted the route
    fills in the preset's default frame count. ``fps`` drives playback in the
    preview and is stored on the manifest for export tooling.
    """

    project_id: str
    action: str = Field(min_length=1)
    frames: int | None = Field(default=None, ge=2, le=8)
    fps: int = Field(default=8, ge=1, le=60)
    direction: Direction = Direction.LEFT


class EnhancePromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    style: Style
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER
    direction: Direction = Direction.LEFT

    @field_validator("prompt")
    @classmethod
    def prompt_must_have_content(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("prompt must not be empty")
        return value

    @model_validator(mode="after")
    def validate_camera_direction(self) -> EnhancePromptRequest:
        validate_direction(self.view_mode, self.direction)
        return self


class EnhancePromptResult(BaseModel):
    original_prompt: str
    enhanced_prompt: str
