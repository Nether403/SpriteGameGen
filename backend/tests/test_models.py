"""Domain model validation."""
from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models import (
    AnimateRequest,
    Direction,
    ExportFormat,
    ExportOptions,
    Frame,
    FrameStatus,
    Project,
    Style,
    ViewMode,
    directions_for,
)


def test_style_enum_values():
    assert Style.PIXEL.value == "pixel"
    assert Style.HIRES.value == "hires"
    assert Style("pixel") is Style.PIXEL


def test_direction_rules_match_camera_modes():
    assert directions_for(ViewMode.SIDE_SCROLLER) == (
        Direction.LEFT,
        Direction.RIGHT,
    )
    assert set(directions_for(ViewMode.TOP_DOWN_2_5D)) == set(Direction)


@pytest.mark.parametrize(
    "direction",
    [
        Direction.UP,
        Direction.DOWN,
        Direction.UP_LEFT,
        Direction.UP_RIGHT,
        Direction.DOWN_LEFT,
        Direction.DOWN_RIGHT,
    ],
)
def test_side_scroller_project_rejects_non_horizontal_direction(direction):
    with pytest.raises(ValidationError):
        Project(
            id="x",
            prompt="p",
            style=Style.PIXEL,
            view_mode=ViewMode.SIDE_SCROLLER,
            direction=direction,
        )


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
    assert project.view_mode is ViewMode.SIDE_SCROLLER
    assert project.direction is Direction.LEFT
    # frames default to empty list
    assert Project(id="x", prompt="p", style=Style.HIRES).frames == []


def test_project_metadata_defaults_are_utc_and_versioned():
    project = Project(id="x", prompt="p", style=Style.PIXEL)

    assert project.schema_version == 1
    assert project.created_at.tzinfo == timezone.utc
    assert project.updated_at.tzinfo == timezone.utc
    assert isinstance(project.created_at, datetime)


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


def test_animate_request_defaults():
    req = AnimateRequest(project_id="p1", action="walk")
    assert req.frames is None  # route fills preset default
    assert req.fps == 8
    assert req.direction is Direction.LEFT


def test_animate_request_explicit():
    req = AnimateRequest(project_id="p1", action="run", frames=6, fps=12)
    assert req.frames == 6
    assert req.fps == 12


def test_animate_request_rejects_empty_action():
    with pytest.raises(ValidationError):
        AnimateRequest(project_id="p1", action="")


@pytest.mark.parametrize("frames", [1, 9])
def test_animate_request_rejects_out_of_range_frames(frames):
    with pytest.raises(ValidationError):
        AnimateRequest(project_id="p1", action="walk", frames=frames)


@pytest.mark.parametrize("fps", [0, 61])
def test_animate_request_rejects_out_of_range_fps(fps):
    with pytest.raises(ValidationError):
        AnimateRequest(project_id="p1", action="walk", fps=fps)


def test_project_animation_fields_optional():
    project = Project(id="x", prompt="p", style=Style.PIXEL)
    assert project.action is None
    assert project.fps is None

    animated = Project(id="x", prompt="p", style=Style.PIXEL, action="walk", fps=10)
    assert animated.action == "walk"
    assert animated.fps == 10
