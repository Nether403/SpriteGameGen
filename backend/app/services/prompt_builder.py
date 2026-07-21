"""Prompt construction (pure strings).

Style directives and per-frame animation prompts are built here. Presets live in
a data table (``PRESETS``) — adding an action is adding a row, not writing code.
The frame template is base-anchored ("same character ...") so Gemini edits stay
consistent with the original sprite.
"""
from __future__ import annotations

from app.models import Direction, Style, ViewMode, validate_direction

# Shared directives that make the deterministic pipeline (bg removal + trim)
# reliable regardless of style.
_BASE_DIRECTIVES = (
    "A single centered subject, full body in frame, "
    "on a plain flat solid-color background with no scenery or shadow."
)

_CAMERA_DIRECTIVES: dict[ViewMode, str] = {
    ViewMode.SIDE_SCROLLER: (
        "Strict side-profile side-scroller view with a fixed orthographic camera"
    ),
    ViewMode.TOP_DOWN_2_5D: (
        "Three-quarter top-down 2.5D game view with a fixed camera"
    ),
}


def _camera_direction(view_mode: ViewMode, direction: Direction) -> str:
    validate_direction(view_mode, direction)
    readable_direction = direction.value.replace("_", "-")
    return (
        f"{_CAMERA_DIRECTIVES[view_mode]}, facing and moving "
        f"{readable_direction}."
    )

_STYLE_DIRECTIVES: dict[Style, str] = {
    Style.PIXEL: (
        "Pixel art style, limited palette, crisp hard edges, no anti-aliasing, "
        "retro 16-bit game sprite."
    ),
    Style.HIRES: (
        "High-resolution clean vector-like game art, smooth shading, "
        "crisp silhouette, modern 2D game asset."
    ),
}

# Preset action table. Each row: prompt template + frame bounds/defaults.
# `{i}` = 1-based frame number, `{n}` = total frames, `{pose}` = motion cue.
_FRAME_TEMPLATE = (
    "POSE GOAL: {pose}. {change_directive} Keep the same character and preserve "
    "the exact design, proportions, equipment, colors, lighting, and rendering "
    "style. Keep the complete character centered and inside the canvas on a fixed "
    "ground line. Do not merely repaint or restyle the source. Animation frame "
    "{i} of {n} in a {action} cycle, designed to loop smoothly."
)

_DEFAULT_POSE_CHANGE = (
    "Redraw the articulated body so its moving parts clearly match this phase. "
    "Use the supplied sprite as a character-design reference while visibly "
    "changing the pose."
)

_WALK_POSE_CHANGE = (
    "Redraw the articulated body so both legs and both feet clearly occupy those "
    "positions. Use the supplied sprite only as a character-design reference, "
    "not as a pose reference; a frame that keeps the supplied stance is invalid. "
    "Make the new limb silhouette exaggerated and unmistakable at thumbnail size."
)

_WALK_PHASES = (
    "Contact pose A: an exaggerated wide scissor stance; the near leg reaches "
    "far forward with its heel touching down while the far leg stretches far "
    "backward with only its toe touching",
    "Compression pose A: body lowered, weight over the planted near foot, both "
    "knees deeply bent, and the far foot visibly lifted behind",
    "Passing pose A: the far thigh swings forward under the torso, its knee "
    "lifted high and its foot clearly off the ground; the near leg is the only "
    "ground contact and is nearly straight",
    "Lift pose A: the far knee leads forward at waist height with its lower leg "
    "folded back; the near leg's heel lifts as the body reaches its highest point",
    "Contact pose B: the opposite exaggerated wide scissor stance; the far leg "
    "reaches far forward with its heel touching down while the near leg stretches "
    "far backward with only its toe touching",
    "Compression pose B: body lowered, weight over the planted far foot, both "
    "knees deeply bent, and the near foot visibly lifted behind",
    "Passing pose B: the near thigh swings forward under the torso, its knee "
    "lifted high and its foot clearly off the ground; the far leg is the only "
    "ground contact and is nearly straight",
    "Lift pose B: the near knee leads forward at waist height with its lower leg "
    "folded back; the far leg's heel lifts as the body reaches its highest point",
)

PRESETS: list[dict] = [
    {
        "action": "idle",
        "min_frames": 2,
        "max_frames": 4,
        "default_frames": 2,
        "pose": "in a subtle idle breathing pose",
    },
    {
        "action": "walk",
        "min_frames": 4,
        "max_frames": 8,
        "default_frames": 6,
        "pose": "mid-stride walking, one foot forward",
        "phases": _WALK_PHASES,
        "change_directive": _WALK_POSE_CHANGE,
    },
    {
        "action": "run",
        "min_frames": 4,
        "max_frames": 8,
        "default_frames": 6,
        "pose": "in a dynamic running stride, leaning forward",
    },
    {
        "action": "attack",
        "min_frames": 4,
        "max_frames": 6,
        "default_frames": 4,
        "pose": "in an attack swing motion",
    },
    {
        "action": "jump",
        "min_frames": 4,
        "max_frames": 6,
        "default_frames": 4,
        "pose": "in a jumping motion, airborne",
    },
]

_PRESETS_BY_ACTION: dict[str, dict] = {p["action"]: p for p in PRESETS}


def build_generate_prompt(
    description: str,
    style: Style,
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
    direction: Direction = Direction.LEFT,
) -> str:
    """Compose the text-to-image prompt from a user description + style directives."""
    style_directive = _STYLE_DIRECTIVES[style]
    camera_directive = _camera_direction(view_mode, direction)
    return (
        f"{description.strip()}. {_BASE_DIRECTIVES} {camera_directive} "
        f"{style_directive}"
    )


def list_presets() -> list[dict]:
    """Return the preset action table (copied so callers can't mutate it)."""
    return [dict(p) for p in PRESETS]


def get_preset(action: str) -> dict:
    """Return a copy of the preset for ``action``. Raises KeyError if unknown."""
    return dict(_PRESETS_BY_ACTION[action])


def frame_prompt(
    action: str,
    index: int,
    total: int,
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
    direction: Direction = Direction.LEFT,
) -> str:
    """Render the per-frame base-anchored prompt for ``action`` frame ``index``.

    ``index`` is 0-based internally; the rendered prompt shows a 1-based number.
    Raises KeyError for unknown actions, ValueError for out-of-range indices.
    """
    preset = _PRESETS_BY_ACTION[action]
    if total < 1:
        raise ValueError("total must be >= 1")
    if not (0 <= index < total):
        raise ValueError(f"index {index} out of range for total {total}")
    phases = preset.get("phases")
    pose = phases[(index * len(phases)) // total] if phases else preset["pose"]
    animation_prompt = _FRAME_TEMPLATE.format(
        pose=pose,
        change_directive=preset.get("change_directive", _DEFAULT_POSE_CHANGE),
        i=index + 1,
        n=total,
        action=action,
    )
    return f"{animation_prompt} {_camera_direction(view_mode, direction)}"
