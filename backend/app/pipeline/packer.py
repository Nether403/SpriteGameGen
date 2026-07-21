"""Sprite-sheet packer (pure, deterministic).

Assumes frames are already uniformly sized (Stage 2 runs shared-bbox alignment
first). Lays frames left-to-right, top-to-bottom into a grid; each cell gets a
uniform ``padding`` gutter. Returns the sheet plus a lightweight layout list
(plain dicts, not pydantic — this feeds the atlas writer).
"""
from __future__ import annotations

import math

from PIL import Image

from app.models import (
    MAX_EXPORT_COLS,
    MAX_EXPORT_PADDING,
    MAX_SHEET_BYTES,
    MAX_SHEET_DIMENSION,
    MAX_SHEET_PIXELS,
)

Layout = list[dict[str, int]]


def _grid_cols(n: int, cols: int | None) -> int:
    if cols is not None:
        return cols
    # auto: near-square, favoring width
    return max(1, math.ceil(math.sqrt(n)))


def pack(
    frames: list[Image.Image], cols: int | None = None, padding: int = 0
) -> tuple[Image.Image, Layout]:
    """Pack frames into a single sheet.

    Args:
        frames: uniformly-sized RGBA frames (index order preserved).
        cols: columns in the grid, or None for a near-square auto layout.
        padding: transparent gutter around every cell (>= 0).

    Returns:
        (sheet, layout) where layout is a list of
        ``{"index", "x", "y", "w", "h"}`` giving each frame's pixel rect.
    """
    if not frames:
        raise ValueError("pack requires at least one frame")
    if cols is not None and cols < 1:
        raise ValueError("cols must be >= 1 or None")
    if cols is not None and cols > MAX_EXPORT_COLS:
        raise ValueError(f"cols must be <= {MAX_EXPORT_COLS}")
    if padding < 0:
        raise ValueError("padding must be >= 0")
    if padding > MAX_EXPORT_PADDING:
        raise ValueError(f"padding must be <= {MAX_EXPORT_PADDING}")

    n = len(frames)
    ncols = _grid_cols(n, cols)
    nrows = math.ceil(n / ncols)

    # Cell size is the largest frame + padding on all sides (frames are usually
    # uniform, but max() keeps it correct if they are not).
    fw = max(f.width for f in frames)
    fh = max(f.height for f in frames)
    cell_w = fw + 2 * padding
    cell_h = fh + 2 * padding
    sheet_width = ncols * cell_w
    sheet_height = nrows * cell_h
    if sheet_width > MAX_SHEET_DIMENSION or sheet_height > MAX_SHEET_DIMENSION:
        raise ValueError(
            f"sprite sheet dimension exceeds {MAX_SHEET_DIMENSION} pixels"
        )
    sheet_pixels = sheet_width * sheet_height
    if sheet_pixels > MAX_SHEET_PIXELS:
        raise ValueError(f"sprite sheet pixels exceed {MAX_SHEET_PIXELS}")
    sheet_bytes = sheet_pixels * 4
    if sheet_bytes > MAX_SHEET_BYTES:
        raise ValueError(f"sprite sheet bytes exceed {MAX_SHEET_BYTES}")

    sheet = Image.new("RGBA", (sheet_width, sheet_height), (0, 0, 0, 0))
    layout: Layout = []

    for i, frame in enumerate(frames):
        col = i % ncols
        row = i // ncols
        x = col * cell_w + padding
        y = row * cell_h + padding
        rgba = frame if frame.mode == "RGBA" else frame.convert("RGBA")
        sheet.paste(rgba, (x, y))
        layout.append(
            {"index": i, "x": x, "y": y, "w": rgba.width, "h": rgba.height}
        )

    return sheet, layout
