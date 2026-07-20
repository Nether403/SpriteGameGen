"""Domain model validation."""
import pytest
from pydantic import ValidationError

from app.models import (
    ExportFormat,
    ExportOptions,
    Frame,
    FrameStatus,
    Project,
    Style,
)


def test_style_enum_values():
    assert Style.PIXEL.value == "pixel"
    assert Style.HIRES.value == "hires"
    assert Style("pixel") is Style.PIXEL


def test_frame_status_values():
    assert FrameStatus.OK.value == "ok"
    assert FrameStatus.FAILED.value == "failed"


def test_frame_defaults_and_construction():
    frame = Frame(index=0, url="/projects/x/frame_0.png")
    assert frame.index == 0
    assert frame.status is FrameStatus.OK
    assert frame.url == "/projects/x/frame_0.png"

    failed = Frame(index=2, url=None, status=FrameStatus.FAILED)
    assert failed.status is FrameStatus.FAILED
    assert failed.url is None


def test_frame_rejects_negative_index():
    with pytest.raises(ValidationError):
        Frame(index=-1, url="x.png")


def test_project_construction():
    project = Project(
        id="abc-123",
        prompt="a knight",
        style=Style.PIXEL,
        frames=[Frame(index=0, url="f0.png")],
    )
    assert project.id == "abc-123"
    assert project.style is Style.PIXEL
    assert len(project.frames) == 1
    # frames default to empty list
    assert Project(id="x", prompt="p", style=Style.HIRES).frames == []


def test_export_options_defaults():
    opts = ExportOptions()
    assert opts.format is ExportFormat.JSON
    assert opts.padding == 0
    assert opts.cols is None  # auto grid


def test_export_options_validates():
    opts = ExportOptions(format="xml", padding=4, cols=3)
    assert opts.format is ExportFormat.XML
    assert opts.padding == 4
    assert opts.cols == 3


def test_export_options_rejects_negative_padding():
    with pytest.raises(ValidationError):
        ExportOptions(padding=-1)


def test_export_options_rejects_bad_format():
    with pytest.raises(ValidationError):
        ExportOptions(format="tga")


def test_export_options_rejects_zero_cols():
    with pytest.raises(ValidationError):
        ExportOptions(cols=0)
