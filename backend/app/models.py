"""Pydantic domain models (spec §3).

These describe the persisted project manifest and the export request shape.
Kept intentionally small; Stage 2 extends ``Frame`` and adds ``AnimateRequest``.
"""
from __future__ import annotations

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
    frames: list[Frame] = Field(default_factory=list)
    action: str | None = None
    fps: int | None = Field(default=None, ge=1, le=60)


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
