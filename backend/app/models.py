"""Pydantic domain models (spec §3).

These describe the persisted project manifest and the export request shape.
Kept intentionally small; Stage 2 extends ``Frame`` and adds ``AnimateRequest``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Style(str, Enum):
    """Art style — differs mainly in one post-processing step (quantize)."""

    PIXEL = "pixel"
    HIRES = "hires"


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
    style: Style
    schema_version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    frames: list[Frame] = Field(default_factory=list)
    action: str | None = None
    fps: int | None = Field(default=None, ge=1, le=60)


class ProjectSummary(BaseModel):
    """Compact catalog entry used by the project browser."""

    id: str
    prompt_preview: str | None = None
    style: Style | None = None
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
