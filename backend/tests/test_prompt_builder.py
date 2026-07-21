"""Prompt builder: style directives + data-driven preset table (pure)."""
import pytest

from app.models import Direction, Style, ViewMode
from app.services import prompt_builder as pb


def test_generate_prompt_includes_description():
    out = pb.build_generate_prompt("a knight with a sword", Style.PIXEL)
    assert "a knight with a sword" in out


def test_generate_prompt_pixel_vs_hires_differ():
    pixel = pb.build_generate_prompt("a knight", Style.PIXEL)
    hires = pb.build_generate_prompt("a knight", Style.HIRES)
    assert pixel != hires
    assert "pixel" in pixel.lower()


def test_generate_prompt_requests_transparent_single_subject():
    # Directives that make downstream bg-removal/trim reliable.
    out = pb.build_generate_prompt("a knight", Style.PIXEL).lower()
    assert "background" in out  # asks for plain/transparent background
    assert "single" in out or "one" in out  # single centered subject


def test_generate_prompt_describes_side_scroller_camera_and_direction():
    out = pb.build_generate_prompt(
        "a knight", Style.PIXEL, ViewMode.SIDE_SCROLLER, Direction.RIGHT
    ).lower()
    assert "side-scroller" in out
    assert "right" in out


def test_generate_prompt_describes_top_down_camera_and_diagonal_direction():
    out = pb.build_generate_prompt(
        "a knight", Style.PIXEL, ViewMode.TOP_DOWN_2_5D, Direction.UP_LEFT
    ).lower()
    assert "top-down" in out
    assert "up-left" in out


def test_list_presets_returns_core_actions():
    presets = pb.list_presets()
    names = {p["action"] for p in presets}
    assert {"idle", "walk", "run", "attack", "jump"} <= names


def test_presets_carry_frame_bounds():
    presets = {p["action"]: p for p in pb.list_presets()}
    assert presets["idle"]["min_frames"] <= presets["idle"]["max_frames"]
    assert presets["walk"]["default_frames"] == 6


def test_frame_prompt_renders_template():
    out = pb.frame_prompt("walk", 2, 6)
    low = out.lower()
    assert "walk" in low
    # frame position communicated to the model (1-based, human-friendly)
    assert "3" in out and "6" in out
    assert "same character" in low  # base-anchored consistency cue


def test_frame_prompt_preserves_camera_and_direction_context():
    out = pb.frame_prompt(
        "walk", 2, 6, ViewMode.TOP_DOWN_2_5D, Direction.DOWN_RIGHT
    ).lower()
    assert "top-down" in out
    assert "down-right" in out
    assert "frame 3 of 6" in out


def test_frame_prompt_is_data_driven_not_branched():
    # Every preset action must render without a per-action code branch.
    for p in pb.list_presets():
        out = pb.frame_prompt(p["action"], 0, p["default_frames"])
        assert p["action"] in out.lower()


def test_walk_cycle_uses_distinct_explicit_leg_phases():
    prompts = [pb.frame_prompt("walk", index, 8).lower() for index in range(8)]

    assert len(set(prompts)) == 8
    assert all("leg" in prompt or "foot" in prompt for prompt in prompts)
    assert "near leg reaches far forward" in prompts[0]
    assert "far leg reaches far forward" in prompts[4]
    assert all("not as a pose reference" in prompt for prompt in prompts)
    assert all("keeps the supplied stance is invalid" in prompt for prompt in prompts)
    assert all("unmistakable at thumbnail size" in prompt for prompt in prompts)


def test_short_walk_cycle_keeps_mirrored_contact_and_passing_poses():
    prompts = [pb.frame_prompt("walk", index, 4).lower() for index in range(4)]

    assert "near leg reaches far forward" in prompts[0]
    assert "far thigh swings forward" in prompts[1]
    assert "far leg reaches far forward" in prompts[2]
    assert "near thigh swings forward" in prompts[3]


def test_frame_prompt_unknown_action_raises():
    with pytest.raises(KeyError):
        pb.frame_prompt("moonwalk", 0, 6)


def test_frame_prompt_validates_index_bounds():
    with pytest.raises(ValueError):
        pb.frame_prompt("walk", 6, 6)  # index must be < total
    with pytest.raises(ValueError):
        pb.frame_prompt("walk", -1, 6)
