"""Trim pipeline: alpha autocrop + shared-bbox frame alignment (pure)."""
import pytest
from PIL import Image

from app.pipeline.trim import (
    DegenerateBBoxError,
    EmptyImageError,
    align_to_bbox,
    autocrop,
    content_bbox,
    shared_bbox,
)


def _canvas(size=(20, 20)):
    """Fully transparent RGBA canvas."""
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _with_block(box, canvas_size=(20, 20), color=(255, 0, 0, 255)):
    """RGBA canvas with an opaque rectangle at ``box`` (l, t, r, b) exclusive-right/bottom."""
    img = _canvas(canvas_size)
    l, t, r, b = box
    block = Image.new("RGBA", (r - l, b - t), color)
    img.paste(block, (l, t))
    return img


def test_content_bbox_finds_opaque_region():
    img = _with_block((5, 6, 12, 15))  # opaque pixels x:5..11, y:6..14
    assert content_bbox(img) == (5, 6, 12, 15)


def test_content_bbox_raises_on_empty():
    with pytest.raises(EmptyImageError):
        content_bbox(_canvas())


def test_autocrop_no_padding_exact_size():
    img = _with_block((5, 6, 12, 15))
    out = autocrop(img, padding=0)
    assert out.size == (7, 9)  # (12-5, 15-6)
    # top-left of cropped output is opaque
    assert out.getpixel((0, 0))[3] == 255


def test_autocrop_padding_adds_uniform_border():
    img = _with_block((5, 6, 12, 15))
    out = autocrop(img, padding=2)
    assert out.size == (7 + 4, 9 + 4)  # padding on all four sides
    # padded border is transparent
    assert out.getpixel((0, 0))[3] == 0
    # content shifted in by padding
    assert out.getpixel((2, 2))[3] == 255


def test_autocrop_padding_clamps_at_canvas_edge():
    # Block touches the left/top edge; padding must not read outside the image.
    img = _with_block((0, 0, 5, 5))
    out = autocrop(img, padding=3)
    # requested padding is clamped by the canvas on the edge sides
    assert out.size[0] >= 5 and out.size[1] >= 5


def test_autocrop_raises_on_empty():
    with pytest.raises(EmptyImageError):
        autocrop(_canvas(), padding=0)


def test_shared_bbox_covers_all_frames():
    a = _with_block((5, 5, 8, 8))
    b = _with_block((10, 2, 14, 6))
    c = _with_block((3, 9, 7, 12))
    # union: left=3, top=2, right=14, bottom=12
    assert shared_bbox([a, b, c]) == (3, 2, 14, 12)


def test_shared_bbox_raises_on_all_empty():
    with pytest.raises(EmptyImageError):
        shared_bbox([_canvas(), _canvas()])


def test_shared_bbox_raises_on_empty_list():
    with pytest.raises(ValueError):
        shared_bbox([])


def test_align_to_bbox_yields_identical_sizes():
    a = _with_block((5, 5, 8, 8))
    b = _with_block((10, 2, 14, 6))
    c = _with_block((3, 9, 7, 12))
    frames = [a, b, c]
    box = shared_bbox(frames)
    aligned = align_to_bbox(frames, box, padding=1)

    sizes = {img.size for img in aligned}
    assert len(sizes) == 1  # anti-jitter: every frame identical size
    w, h = (box[2] - box[0]), (box[3] - box[1])
    assert sizes.pop() == (w + 2, h + 2)


def test_align_to_bbox_preserves_relative_position():
    # A frame whose content sits at the shared-box origin keeps its content
    # at (padding, padding) after alignment.
    a = _with_block((3, 2, 6, 5))
    b = _with_block((3, 2, 14, 12))  # defines the full shared box
    box = shared_bbox([a, b])
    aligned = align_to_bbox([a], box, padding=0)
    assert aligned[0].getpixel((0, 0))[3] == 255


def test_degenerate_bbox_raises():
    # A zero-area explicit bbox is degenerate.
    img = _with_block((5, 5, 8, 8))
    with pytest.raises(DegenerateBBoxError):
        align_to_bbox([img], (5, 5, 5, 5), padding=0)
