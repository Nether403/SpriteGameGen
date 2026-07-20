"""Alpha-based trimming and shared-bbox alignment.

Pure functions: ``Image -> Image`` / ``[Image] -> [Image]``. No network, no disk,
no config. The alpha channel is the source of truth for "content". Deterministic:
identical input always yields identical output.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

BBox = tuple[int, int, int, int]  # (left, top, right, bottom), right/bottom exclusive


class EmptyImageError(ValueError):
    """Raised when an image has no opaque (non-zero-alpha) pixels."""


class DegenerateBBoxError(ValueError):
    """Raised when a bounding box has zero or negative area."""


def _alpha_array(img: Image.Image) -> np.ndarray:
    """Return the alpha channel as a 2-D uint8 array (H, W)."""
    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    return np.asarray(rgba)[:, :, 3]


def content_bbox(img: Image.Image) -> BBox:
    """Bounding box of opaque pixels as (left, top, right, bottom), right/bottom exclusive.

    Raises ``EmptyImageError`` if the image is fully transparent.
    """
    alpha = _alpha_array(img)
    rows = np.any(alpha > 0, axis=1)
    cols = np.any(alpha > 0, axis=0)
    if not rows.any():
        raise EmptyImageError("image has no opaque pixels")

    top, bottom = np.where(rows)[0][[0, -1]]
    left, right = np.where(cols)[0][[0, -1]]
    return int(left), int(top), int(right) + 1, int(bottom) + 1


def autocrop(img: Image.Image, padding: int = 0) -> Image.Image:
    """Crop ``img`` to its content bounding box plus a uniform ``padding`` border.

    Padding is clamped at the canvas edges (never reads outside the image).
    Raises ``EmptyImageError`` on a fully transparent image.
    """
    left, top, right, bottom = content_bbox(img)
    w, h = img.size
    box = (
        max(0, left - padding),
        max(0, top - padding),
        min(w, right + padding),
        min(h, bottom + padding),
    )
    return img.crop(box)


def shared_bbox(images: list[Image.Image]) -> BBox:
    """Compute one bounding box covering the content of every frame (anti-jitter).

    Raises ``ValueError`` on an empty list and ``EmptyImageError`` if no frame has
    any opaque pixels.
    """
    if not images:
        raise ValueError("shared_bbox requires at least one image")

    boxes: list[BBox] = []
    for img in images:
        try:
            boxes.append(content_bbox(img))
        except EmptyImageError:
            continue
    if not boxes:
        raise EmptyImageError("no frame has any opaque pixels")

    left = min(b[0] for b in boxes)
    top = min(b[1] for b in boxes)
    right = max(b[2] for b in boxes)
    bottom = max(b[3] for b in boxes)
    return left, top, right, bottom


def align_to_bbox(
    images: list[Image.Image], box: BBox, padding: int = 0
) -> list[Image.Image]:
    """Crop every frame to the same ``box`` (+ padding), yielding identical sizes.

    This is the anti-jitter step: with one shared box, the character does not
    resize or shift between frames. Raises ``DegenerateBBoxError`` for a
    zero/negative-area box.
    """
    left, top, right, bottom = box
    if right <= left or bottom <= top:
        raise DegenerateBBoxError(f"degenerate bounding box: {box}")

    w, h = (right - left), (bottom - top)
    out_size = (w + 2 * padding, h + 2 * padding)

    aligned: list[Image.Image] = []
    for img in images:
        rgba = img if img.mode == "RGBA" else img.convert("RGBA")
        cropped = rgba.crop((left, top, right, bottom))
        if padding == 0:
            aligned.append(cropped)
        else:
            canvas = Image.new("RGBA", out_size, (0, 0, 0, 0))
            canvas.paste(cropped, (padding, padding))
            aligned.append(canvas)
    return aligned
