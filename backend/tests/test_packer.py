"""Sprite-sheet packer: grid layout + pixel offsets (pure, deterministic)."""
import numpy as np
import pytest
from PIL import Image

from app.models import (
    MAX_EXPORT_COLS,
    MAX_EXPORT_PADDING,
    MAX_SHEET_BYTES,
    MAX_SHEET_DIMENSION,
    MAX_SHEET_PIXELS,
)
from app.pipeline import packer
from app.pipeline.packer import pack


def _frames(n, size=(10, 8)):
    """n solid-color RGBA frames of identical size (as after shared-bbox align)."""
    colors = [
        (255, 0, 0, 255),
        (0, 255, 0, 255),
        (0, 0, 255, 255),
        (255, 255, 0, 255),
        (255, 0, 255, 255),
        (0, 255, 255, 255),
    ]
    return [Image.new("RGBA", size, colors[i % len(colors)]) for i in range(n)]


def test_pack_auto_grid_near_square():
    sheet, layout = pack(_frames(6), cols=None, padding=0)
    # 6 frames -> near-square grid, 3 cols x 2 rows
    assert len(layout) == 6
    max_col = max(item["x"] for item in layout)
    # with 10px-wide frames, 3 cols means max x offset == 20
    assert max_col == 20
    assert sheet.size == (30, 16)  # 3*10 wide, 2*8 tall


def test_pack_explicit_cols():
    sheet, layout = pack(_frames(6), cols=2, padding=0)
    # 2 cols x 3 rows
    assert sheet.size == (20, 24)
    assert len(layout) == 6


def test_pack_layout_offsets_exact():
    frames = _frames(4, size=(10, 8))
    sheet, layout = pack(frames, cols=2, padding=0)
    by_index = {item["index"]: item for item in layout}
    assert by_index[0] == {"index": 0, "x": 0, "y": 0, "w": 10, "h": 8}
    assert by_index[1] == {"index": 1, "x": 10, "y": 0, "w": 10, "h": 8}
    assert by_index[2] == {"index": 2, "x": 0, "y": 8, "w": 10, "h": 8}
    assert by_index[3] == {"index": 3, "x": 10, "y": 8, "w": 10, "h": 8}


def test_pack_padding_offsets_and_size():
    frames = _frames(2, size=(10, 8))
    sheet, layout = pack(frames, cols=2, padding=2)
    # padding around every cell: cell = frame + 2*padding
    # width = 2 cols * (10 + 4) = 28 ; height = 1 row * (8 + 4) = 12
    assert sheet.size == (28, 12)
    by_index = {item["index"]: item for item in layout}
    # first frame content offset by padding
    assert by_index[0]["x"] == 2 and by_index[0]["y"] == 2
    # second frame in next cell: cell width is frame+2*padding (14), so its
    # content sits at 14 + padding = 16.
    assert by_index[1]["x"] == 16 and by_index[1]["y"] == 2


def test_pack_pastes_frame_pixels():
    frames = _frames(2, size=(10, 8))
    sheet, layout = pack(frames, cols=2, padding=0)
    # frame 0 is red at its offset
    assert sheet.getpixel((0, 0)) == (255, 0, 0, 255)
    # frame 1 is green at its offset (x=10)
    assert sheet.getpixel((10, 0)) == (0, 255, 0, 255)


def test_pack_single_frame():
    sheet, layout = pack(_frames(1, size=(12, 9)), cols=None, padding=0)
    assert sheet.size == (12, 9)
    assert layout == [{"index": 0, "x": 0, "y": 0, "w": 12, "h": 9}]


def test_pack_is_deterministic():
    frames = _frames(5)
    a_sheet, a_layout = pack(frames, cols=None, padding=1)
    b_sheet, b_layout = pack(frames, cols=None, padding=1)
    assert a_layout == b_layout
    assert np.array_equal(np.asarray(a_sheet), np.asarray(b_sheet))


def test_pack_sheet_is_rgba_transparent_background():
    sheet, _ = pack(_frames(3, size=(10, 8)), cols=3, padding=2)
    assert sheet.mode == "RGBA"
    # padding gutter is transparent
    assert sheet.getpixel((0, 0))[3] == 0


def test_pack_rejects_empty():
    with pytest.raises(ValueError):
        pack([], cols=None, padding=0)


def test_pack_rejects_bad_cols_or_padding():
    with pytest.raises(ValueError):
        pack(_frames(2), cols=0, padding=0)
    with pytest.raises(ValueError):
        pack(_frames(2), cols=None, padding=-1)


@pytest.mark.parametrize(
    ("cols", "padding"),
    [(MAX_EXPORT_COLS + 1, 0), (None, MAX_EXPORT_PADDING + 1)],
)
def test_pack_enforces_export_option_upper_bounds(cols, padding):
    with pytest.raises(ValueError):
        pack(_frames(1), cols=cols, padding=padding)


class _SizedFrame:
    mode = "RGBA"

    def __init__(self, width, height):
        self.width = width
        self.height = height


@pytest.mark.parametrize(
    ("size", "message"),
    [
        ((MAX_SHEET_DIMENSION + 1, 1), "dimension"),
        ((MAX_SHEET_DIMENSION, MAX_SHEET_DIMENSION), "pixels"),
        (
            (MAX_SHEET_DIMENSION // 2 + 1, MAX_SHEET_DIMENSION // 2 + 1),
            "bytes",
        ),
    ],
)
def test_pack_rejects_oversized_sheet_before_pillow_allocation(
    monkeypatch, size, message
):
    allocated = False

    def fail_if_allocated(*args, **kwargs):
        nonlocal allocated
        allocated = True
        raise AssertionError("Pillow allocation must not be attempted")

    monkeypatch.setattr(packer.Image, "new", fail_if_allocated)

    with pytest.raises(ValueError, match=message):
        pack([_SizedFrame(*size)], cols=1, padding=0)
    assert allocated is False
