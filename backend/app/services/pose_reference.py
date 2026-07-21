"""Deterministic pose guides for Gemini image edits.

Gemini preserves character identity well from a source image, but complex pose
changes are substantially more reliable when a separate structural reference is
provided.  These intentionally plain stick figures communicate geometry only;
the edit prompt tells Gemini to retain the art and identity from the base sprite.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from app.models import Direction

_SIZE = 256
_GROUND_Y = 226

# (near knee, near foot, far knee, far foot), authored facing right.  Frames
# four through seven mirror which leg leads so the loop has two real steps.
_WALK_LEGS: tuple[
    tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]], ...
] = (
    ((160, 170), (202, _GROUND_Y), (98, 170), (56, _GROUND_Y)),
    ((154, 180), (180, _GROUND_Y), (102, 178), (78, 207)),
    ((116, 174), (122, _GROUND_Y), (172, 148), (164, 191)),
    ((118, 176), (140, _GROUND_Y), (174, 142), (151, 171)),
    ((98, 170), (56, _GROUND_Y), (160, 170), (202, _GROUND_Y)),
    ((102, 178), (78, 207), (154, 180), (180, _GROUND_Y)),
    ((172, 148), (164, 191), (116, 174), (122, _GROUND_Y)),
    ((174, 142), (151, 171), (118, 176), (140, _GROUND_Y)),
)


def walk_pose_reference(index: int, total: int, direction: Direction) -> Image.Image:
    """Return a side-profile walk skeleton for a requested animation frame."""
    if total < 1:
        raise ValueError("total must be >= 1")
    if not 0 <= index < total:
        raise ValueError(f"index {index} out of range for total {total}")
    if direction not in (Direction.LEFT, Direction.RIGHT):
        raise ValueError("walk pose references support left/right directions only")

    phase = (index * len(_WALK_LEGS)) // total
    near_knee, near_foot, far_knee, far_foot = _WALK_LEGS[phase]
    shoulder = (128, 78)
    hip = (128, 125)
    image = Image.new("RGB", (_SIZE, _SIZE), "white")
    draw = ImageDraw.Draw(image)
    # Simple upper body gives the model scale and joint placement without
    # competing with the source character's design or equipment.
    draw.line((shoulder, hip), fill="#111111", width=12)
    head_center = (128, 45)
    draw.ellipse(
        (
            head_center[0] - 17,
            head_center[1] - 17,
            head_center[0] + 17,
            head_center[1] + 17,
        ),
        outline="#111111",
        width=8,
    )
    arm_sign = 1 if phase < 4 else -1
    draw.line(
        (shoulder, (128 + 38 * arm_sign, 116), (128 + 18 * arm_sign, 158)),
        fill="#111111",
        width=10,
    )
    draw.line(
        (shoulder, (128 - 36 * arm_sign, 118), (128 - 16 * arm_sign, 160)),
        fill="#666666",
        width=10,
    )

    # Draw the far limb first so the near/far layering remains readable.
    draw.line((hip, far_knee, far_foot), fill="#666666", width=14)
    draw.line((hip, near_knee, near_foot), fill="#111111", width=14)
    for joint in (hip, far_knee, near_knee):
        draw.ellipse(
            (joint[0] - 8, joint[1] - 8, joint[0] + 8, joint[1] + 8),
            fill="white",
            outline="#111111",
            width=4,
        )
    for foot, color in ((far_foot, "#666666"), (near_foot, "#111111")):
        toe = (foot[0] + 30, foot[1])
        draw.line((foot, toe), fill=color, width=14)
    if direction is Direction.LEFT:
        return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
    return image
