"""Pixelate pipeline: color quantization + integer downscale/upscale (pure)."""
import numpy as np
import pytest
from PIL import Image

from app.pipeline.pixelate import quantize


def _gradient(size=(32, 32)):
    """RGBA image with many distinct colors and a partially transparent region."""
    w, h = size
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            arr[y, x] = (x * 8 % 256, y * 8 % 256, (x + y) * 4 % 256, 255)
    # carve a transparent hole
    arr[0:8, 0:8, 3] = 0
    return Image.fromarray(arr, "RGBA")


def _distinct_opaque_colors(img: Image.Image) -> int:
    arr = np.asarray(img.convert("RGBA"))
    opaque = arr[arr[:, :, 3] > 0][:, :3]
    return len({tuple(c) for c in opaque})


def test_quantize_reduces_color_count():
    img = _gradient()
    out = quantize(img, colors=8, downscale=1)
    assert _distinct_opaque_colors(out) <= 8


def test_quantize_preserves_size_when_downscale_1():
    img = _gradient((32, 32))
    out = quantize(img, colors=16, downscale=1)
    assert out.size == (32, 32)


def test_quantize_preserves_alpha_hole():
    img = _gradient()
    out = quantize(img, colors=8, downscale=1)
    # the transparent hole stays transparent
    assert out.getpixel((2, 2))[3] == 0
    # an opaque area stays opaque
    assert out.getpixel((20, 20))[3] == 255


def test_quantize_downscale_keeps_output_dimensions():
    # Downscale by 4 then nearest-neighbor back to original -> crisp pixels,
    # original dimensions preserved.
    img = _gradient((32, 32))
    out = quantize(img, colors=16, downscale=4)
    assert out.size == (32, 32)


def test_quantize_downscale_creates_blocky_pixels():
    img = _gradient((32, 32))
    out = quantize(img, colors=16, downscale=4)
    arr = np.asarray(out.convert("RGBA"))
    # within a 4x4 block the color should be uniform (nearest-neighbor upscale)
    block = arr[16:20, 16:20, :3]
    assert np.all(block == block[0, 0])


def test_quantize_is_deterministic():
    img = _gradient()
    a = quantize(img, colors=8, downscale=2)
    b = quantize(img, colors=8, downscale=2)
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_quantize_output_is_rgba():
    out = quantize(_gradient(), colors=8, downscale=1)
    assert out.mode == "RGBA"


def test_quantize_rejects_bad_params():
    img = _gradient()
    with pytest.raises(ValueError):
        quantize(img, colors=0, downscale=1)
    with pytest.raises(ValueError):
        quantize(img, colors=8, downscale=0)
