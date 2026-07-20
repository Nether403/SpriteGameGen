"""Sprite-sheet packer (pure, deterministic).

Assumes frames are already uniformly sized (Stage 2 runs shared-bbox alignment
first). Lays frames left-to-right, top-to-bottom into a grid; each cell gets a
uniform ``padding`` gutter. Returns the sheet plus a lightweight layout list
(plain dicts, not pydantic — this feeds the atlas writer).
"""
from __future__ import annotations

import math

from PIL import Image

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
    if padding < 0:
        raise ValueError("padding must be >= 0")

    n = len(frames)
    ncols = _grid_cols(n, cols)
    nrows = math.ceil(n / ncols)

    # Cell size is the largest frame + padding on all sides (frames are usually
    # uniform, but max() keeps it correct if they are not).
    fw = max(f.width for f in frames)
    fh = max(f.height for f in frames)
    cell_w = fw + 2 * padding
    cell_h = fh + 2 * padding

    sheet = Image.new("RGBA", (ncols * cell_w, nrows * cell_h), (0, 0, 0, 0))
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
