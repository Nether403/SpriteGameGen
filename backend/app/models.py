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
    """Filesystem project manifest, persisted as ``project.json``."""

    id: str
    prompt: str
    style: Style
    frames: list[Frame] = Field(default_factory=list)


class ExportOptions(BaseModel):
    """Options for packing frames into a sheet + atlas."""

    format: ExportFormat = ExportFormat.JSON
    padding: int = Field(default=0, ge=0)
    cols: int | None = Field(default=None, ge=1)  # None => auto near-square grid
