"""Prompt construction (pure strings).

Style directives and per-frame animation prompts are built here. Presets live in
a data table (``PRESETS``) — adding an action is adding a row, not writing code.
The frame template is base-anchored ("same character ...") so Gemini edits stay
consistent with the original sprite.
"""
from __future__ import annotations

from app.models import Style

# Shared directives that make the deterministic pipeline (bg removal + trim)
# reliable regardless of style.
_BASE_DIRECTIVES = (
    "A single centered subject, full body in frame, facing left, "
    "on a plain flat solid-color background with no scenery or shadow."
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
    "Same character, identical design and colors, {pose}. "
    "Animation frame {i} of {n} in a {action} cycle. "
    "Keep pose count consistent so frames loop smoothly."
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


def build_generate_prompt(description: str, style: Style) -> str:
    """Compose the text-to-image prompt from a user description + style directives."""
    style_directive = _STYLE_DIRECTIVES[style]
    return f"{description.strip()}. {_BASE_DIRECTIVES} {style_directive}"


def list_presets() -> list[dict]:
    """Return the preset action table (copied so callers can't mutate it)."""
    return [dict(p) for p in PRESETS]


def get_preset(action: str) -> dict:
    """Return a copy of the preset for ``action``. Raises KeyError if unknown."""
    return dict(_PRESETS_BY_ACTION[action])


def frame_prompt(action: str, index: int, total: int) -> str:
    """Render the per-frame base-anchored prompt for ``action`` frame ``index``.

    ``index`` is 0-based internally; the rendered prompt shows a 1-based number.
    Raises KeyError for unknown actions, ValueError for out-of-range indices.
    """
    preset = _PRESETS_BY_ACTION[action]
    if total < 1:
        raise ValueError("total must be >= 1")
    if not (0 <= index < total):
        raise ValueError(f"index {index} out of range for total {total}")
    return _FRAME_TEMPLATE.format(
        pose=preset["pose"], i=index + 1, n=total, action=action
    )
