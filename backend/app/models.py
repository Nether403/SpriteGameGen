"""Pydantic domain models (spec §3).

These describe the persisted project manifest and the export request shape.
Kept intentionally small; Stage 2 extends ``Frame`` and adds ``AnimateRequest``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_PROMPT_LENGTH = 2000
MAX_EXPORT_PADDING = 256
MAX_EXPORT_COLS = 64
MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 16 * 1024 * 1024
MAX_SHEET_DIMENSION = 8192
MAX_SHEET_PIXELS = 32 * 1024 * 1024
MAX_SHEET_BYTES = 64 * 1024 * 1024
MAX_FRAME_ERROR_MESSAGE_LENGTH = 200
MANIFEST_SCHEMA_VERSION = 2
MAX_CLIPS = 128
MAX_FRAMES_PER_CLIP = 64


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


class ImageProviderName(str, Enum):
    AUTO = "auto"
    AZURE = "azure"
    GEMINI = "gemini"
    HYPERAGENT = "hyperagent"
    COMFYUI = "comfyui"


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


class FrameErrorCode(str, Enum):
    PROVIDER = "provider"
    SAFETY = "safety"
    BACKGROUND = "background"
    EMPTY = "empty"
    PIXELATE = "pixelate"


class ProjectHealth(str, Enum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    CORRUPT = "corrupt"


class ExportFormat(str, Enum):
    JSON = "json"
    XML = "xml"


class LoopMode(str, Enum):
    LOOP = "loop"
    ONCE = "once"


class PaletteMode(str, Enum):
    AUTO = "auto"
    SHARED_AUTO = "shared_auto"
    PRESET = "preset"
    CUSTOM = "custom"


class RenderSettings(BaseModel):
    """Deterministic settings applied to retained source images."""

    model_config = ConfigDict(extra="forbid")

    target_width: int | None = Field(default=None, ge=1, le=1024)
    target_height: int | None = Field(default=None, ge=1, le=1024)
    output_scale: int = Field(default=1, ge=1, le=16)
    color_limit: int = Field(default=32, ge=1, le=256)
    palette_mode: PaletteMode = PaletteMode.AUTO
    preset_palette: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,32}$")
    custom_palette: list[str] = Field(default_factory=list, max_length=256)

    @field_validator("custom_palette")
    @classmethod
    def validate_palette_colors(cls, values: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", value) for value in values):
            raise ValueError("custom palette colors must use #RRGGBB")
        return [value.upper() for value in values]

    @model_validator(mode="after")
    def validate_palette_mode(self) -> "RenderSettings":
        if (self.target_width is None) != (self.target_height is None):
            raise ValueError("target_width and target_height must be set together")
        if self.palette_mode is PaletteMode.PRESET and not self.preset_palette:
            raise ValueError("preset palette mode requires preset_palette")
        if self.palette_mode is PaletteMode.CUSTOM and not self.custom_palette:
            raise ValueError("custom palette mode requires custom_palette")
        if self.target_width and self.target_height:
            width = self.target_width * self.output_scale
            height = self.target_height * self.output_scale
            if (
                width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise ValueError("rendered target exceeds image resource limits")
        return self


class Frame(BaseModel):
    """One frame of an animation (a single static sprite is one frame at index 0)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    url: str | None = Field(default=None, exclude=True)
    source_filename: str | None = None
    rendered_filename: str | None = None
    enabled: bool = True
    nudge_x: int = Field(default=0, ge=-4096, le=4096)
    nudge_y: int = Field(default=0, ge=-4096, le=4096)
    duration_ms: int | None = Field(default=None, ge=1, le=60_000)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    status: FrameStatus = FrameStatus.OK
    error_code: FrameErrorCode | None = None
    error_message: str | None = Field(
        default=None, max_length=MAX_FRAME_ERROR_MESSAGE_LENGTH
    )


class ActionSnapshot(BaseModel):
    """Complete data needed to regenerate a clip after its source pack changes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    version: str = Field(default="1", min_length=1, max_length=32)
    motion: str = Field(min_length=1, max_length=2000)
    min_frames: int = Field(default=2, ge=1, le=MAX_FRAMES_PER_CLIP)
    max_frames: int = Field(default=8, ge=1, le=MAX_FRAMES_PER_CLIP)
    default_frames: int = Field(default=4, ge=1, le=MAX_FRAMES_PER_CLIP)
    fps: int = Field(default=8, ge=1, le=60)
    loop_mode: LoopMode = LoopMode.LOOP
    phases: list[str] = Field(default_factory=list, max_length=MAX_FRAMES_PER_CLIP)
    first_pose: str | None = Field(default=None, max_length=1000)
    last_pose: str | None = Field(default=None, max_length=1000)
    change_directive: str | None = Field(default=None, max_length=2000)
    guides: list[dict] = Field(default_factory=list, max_length=64)


class AnimationClip(BaseModel):
    """One independently editable animation in a character project."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=64)
    action_ref: str | None = Field(default=None, max_length=200)
    action_version: str | None = Field(default=None, max_length=32)
    action_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    action_snapshot: ActionSnapshot | None = None
    direction: Direction = Direction.LEFT
    fps: int = Field(default=8, ge=1, le=60)
    loop_mode: LoopMode = LoopMode.LOOP
    loop_start: int = Field(default=0, ge=0)
    loop_end: int | None = Field(default=None, ge=0)
    enabled: bool = True
    horizontal_flip: bool = False
    frames: list[Frame] = Field(default_factory=list, max_length=MAX_FRAMES_PER_CLIP)
    image_provider: ImageProviderName = ImageProviderName.GEMINI
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_frame_range(self) -> "AnimationClip":
        indices = [frame.index for frame in self.frames]
        if indices != list(range(len(indices))):
            raise ValueError("clip frame indices must be contiguous from zero")
        if self.loop_end is not None and (
            self.loop_end < self.loop_start or self.loop_end >= len(self.frames)
        ):
            raise ValueError("loop range must refer to existing frames")
        return self


class Project(BaseModel):
    """Filesystem project manifest, persisted as ``project.json``.

    ``action`` and ``fps`` are set once a project has been animated (Stage 2);
    a freshly generated single-sprite project leaves them unset.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    enhanced_prompt: str | None = Field(default=None, max_length=MAX_PROMPT_LENGTH)
    prompt_source: PromptSource = PromptSource.RAW
    image_provider: ImageProviderName = ImageProviderName.GEMINI
    style: Style
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER
    direction: Direction = Direction.LEFT
    schema_version: int = Field(default=MANIFEST_SCHEMA_VERSION, ge=1)
    revision: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_sprite_filename: str = "source_sprite.png"
    sprite_filename: str = "sprite.png"
    render_settings: RenderSettings = Field(default_factory=RenderSettings)
    pivot_x: float = Field(default=0.5, ge=0, le=1)
    pivot_y: float = Field(default=1.0, ge=0, le=1)
    baseline: int = 0
    clips: dict[str, AnimationClip] = Field(default_factory=dict, max_length=MAX_CLIPS)
    active_clip_id: str | None = None
    recipe_provenance: dict[str, str] | None = None
    # One-release compatibility projection. These fields are accepted by old
    # callers but excluded from canonical V2 serialization.
    frames: list[Frame] = Field(default_factory=list, exclude=True)
    action: str | None = Field(default=None, exclude=True)
    fps: int | None = Field(default=None, ge=1, le=60, exclude=True)

    @model_validator(mode="after")
    def validate_camera_direction(self) -> Project:
        validate_direction(self.view_mode, self.direction)
        if self.prompt_source is PromptSource.ENHANCED and not self.enhanced_prompt:
            raise ValueError("enhanced prompt source requires enhanced_prompt")
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported manifest schema version {self.schema_version}; "
                f"expected {MANIFEST_SCHEMA_VERSION}"
            )
        if any(key != clip.id for key, clip in self.clips.items()):
            raise ValueError("clip map keys must match clip IDs")
        if self.active_clip_id is not None and self.active_clip_id not in self.clips:
            raise ValueError("active_clip_id must refer to an existing clip")
        if self.action and not self.clips:
            clip_id = "legacy"
            migrated_frames = []
            for frame in self.frames:
                copy = frame.model_copy(deep=True)
                copy.source_filename = copy.source_filename or f"frame_{copy.index}.png"
                copy.rendered_filename = copy.rendered_filename or f"frame_{copy.index}.png"
                migrated_frames.append(copy)
            self.clips[clip_id] = AnimationClip(
                id=clip_id,
                name=self.action.replace("_", " ").title(),
                action=self.action,
                direction=self.direction,
                fps=self.fps or 8,
                frames=migrated_frames,
                image_provider=self.image_provider,
            )
            self.active_clip_id = clip_id
        active = self.clips.get(self.active_clip_id) if self.active_clip_id else None
        if active is not None:
            self.frames = active.frames
            self.action = active.action
            self.fps = active.fps
        return self

    @property
    def active_clip(self) -> AnimationClip | None:
        return self.clips.get(self.active_clip_id) if self.active_clip_id else None


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
    clip_count: int = 0
    active_clip_id: str | None = None


class ProjectDetail(Project):
    """Full project state with browser metadata and fresh asset URLs."""

    sprite_url: str | None = None
    health: ProjectHealth = ProjectHealth.READY
    resume_available: bool = True


class ExportOptions(BaseModel):
    """Options for packing frames into a sheet + atlas."""

    format: ExportFormat = ExportFormat.JSON
    padding: int = Field(default=0, ge=0, le=MAX_EXPORT_PADDING)
    cols: int | None = Field(
        default=None, ge=1, le=MAX_EXPORT_COLS
    )  # None => auto near-square grid
    clip_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")


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
    provider: ImageProviderName | None = None
    clip_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]+$")
    clip_name: str | None = Field(default=None, min_length=1, max_length=100)
    loop_mode: LoopMode = LoopMode.LOOP
    custom_motion: str | None = Field(default=None, min_length=1, max_length=2000)
    first_pose: str | None = Field(default=None, max_length=1000)
    last_pose: str | None = Field(default=None, max_length=1000)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)


class EnhancePromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
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
    original_prompt: str = Field(max_length=MAX_PROMPT_LENGTH)
    enhanced_prompt: str = Field(max_length=MAX_PROMPT_LENGTH)
