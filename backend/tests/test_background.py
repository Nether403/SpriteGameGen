"""Background removal wrapper (injected remover — no real rembg load in tests)."""
import numpy as np
from PIL import Image

import pytest

from app.pipeline.background import BackgroundRemovalError, remove


def test_remove_uses_injected_remover_and_returns_rgba():
    src = Image.new("RGB", (10, 10), (120, 30, 200))

    captured = {}

    def fake_remover(img: Image.Image) -> Image.Image:
        captured["called_with_mode"] = img.mode
        # simulate a cutout: left half opaque, right half transparent
        out = img.convert("RGBA")
        arr = np.asarray(out).copy()
        arr[:, 5:, 3] = 0
        return Image.fromarray(arr, "RGBA")

    result = remove(src, remover=fake_remover)

    assert captured["called_with_mode"] in ("RGB", "RGBA")
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 255   # opaque left
    assert result.getpixel((9, 0))[3] == 0     # transparent right


def test_remove_coerces_non_rgba_remover_output():
    src = Image.new("RGB", (4, 4), (10, 20, 30))

    def rgb_remover(img: Image.Image) -> Image.Image:
        # a remover that (wrongly) returns RGB — wrapper must still yield RGBA
        return img.convert("RGB")

    result = remove(src, remover=rgb_remover)
    assert result.mode == "RGBA"


def test_remove_preserves_dimensions():
    src = Image.new("RGB", (13, 7), (0, 0, 0))
    result = remove(src, remover=lambda im: im.convert("RGBA"))
    assert result.size == (13, 7)


def test_remove_wraps_remover_failure():
    with pytest.raises(BackgroundRemovalError):
        remove(Image.new("RGBA", (4, 4)), remover=lambda _img: (_ for _ in ()).throw(RuntimeError("rembg failed")))
