from PIL import Image

from app.pipeline.frame_render import compose


def test_compositor_places_source_at_bottom_center():
    source = Image.new("RGBA", (2, 2), "red")

    result = compose(source, (6, 5))

    assert result.getbbox() == (2, 3, 4, 5)


def test_compositor_applies_flip_and_integer_nudges_without_mutating_source():
    source = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    source.putpixel((0, 0), (255, 0, 0, 255))
    before = source.tobytes()

    result = compose(source, (4, 3), horizontal_flip=True, nudge_x=1, nudge_y=-1)

    assert result.getpixel((3, 1)) == (255, 0, 0, 255)
    assert source.tobytes() == before


def test_compositor_is_byte_deterministic():
    source = Image.new("RGBA", (3, 2), (10, 20, 30, 255))

    first = compose(source, (8, 8), nudge_x=-1)
    second = compose(source, (8, 8), nudge_x=-1)

    assert first.tobytes() == second.tobytes()
