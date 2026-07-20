"""Pixel-art conversion: integer downscale + color quantization (pure).

This is the single post-processing step that distinguishes the ``pixel`` style
from ``hires``. Deterministic: median-cut quantization with dithering disabled,
nearest-neighbor resampling. Alpha is preserved (quantization touches RGB only).
"""
from __future__ import annotations

from PIL import Image


def quantize(img: Image.Image, colors: int = 32, downscale: int = 1) -> Image.Image:
    """Reduce ``img`` to a pixel-art look.

    Steps: optional integer downscale (nearest) -> reduce to ``colors`` distinct
    RGB colors (median cut, no dither) -> nearest-neighbor upscale back to the
    original size, giving crisp blocky pixels. The alpha channel is carried
    through unquantized so transparency is preserved exactly.

    Args:
        colors: max distinct opaque colors (>= 1).
        downscale: integer downscale factor (>= 1); 1 leaves size unchanged.
    """
    if colors < 1:
        raise ValueError("colors must be >= 1")
    if downscale < 1:
        raise ValueError("downscale must be >= 1")

    rgba = img if img.mode == "RGBA" else img.convert("RGBA")
    w, h = rgba.size

    if downscale > 1:
        small = rgba.resize(
            (max(1, w // downscale), max(1, h // downscale)), Image.NEAREST
        )
    else:
        small = rgba

    r, g, b, a = small.split()
    rgb = Image.merge("RGB", (r, g, b))
    palette_img = rgb.quantize(
        colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    rgb_q = palette_img.convert("RGB")
    result = Image.merge("RGBA", (*rgb_q.split(), a))

    if downscale > 1:
        result = result.resize((w, h), Image.NEAREST)
    return result
