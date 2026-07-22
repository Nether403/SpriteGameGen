"""Pure bottom-center composition for deterministic frame repair."""
from __future__ import annotations

from PIL import Image, ImageOps


def compose(
    source: Image.Image,
    canvas_size: tuple[int, int],
    *,
    horizontal_flip: bool = False,
    nudge_x: int = 0,
    nudge_y: int = 0,
) -> Image.Image:
    if canvas_size[0] < 1 or canvas_size[1] < 1:
        raise ValueError("canvas dimensions must be positive")
    image = source.convert("RGBA")
    if horizontal_flip:
        image = ImageOps.mirror(image)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    x = (canvas_size[0] - image.width) // 2 + int(nudge_x)
    y = canvas_size[1] - image.height + int(nudge_y)
    canvas.alpha_composite(image, (x, y))
    return canvas
