"""Pixel-art conversion: integer downscale + color quantization (pure).

This is the single post-processing step that distinguishes the ``pixel`` style
from ``hires``. Deterministic: median-cut quantization with dithering disabled,
nearest-neighbor resampling. Alpha is preserved (quantization touches RGB only).
"""
from __future__ import annotations

from PIL import Image


PRESET_PALETTES: dict[str, tuple[str, ...]] = {
    "gameboy": ("#0F380F", "#306230", "#8BAC0F", "#9BBC0F"),
    "pico8": (
        "#000000", "#1D2B53", "#7E2553", "#008751", "#AB5236", "#5F574F",
        "#C2C3C7", "#FFF1E8", "#FF004D", "#FFA300", "#FFEC27", "#00E436",
        "#29ADFF", "#83769C", "#FF77A8", "#FFCCAA",
    ),
}


class PixelateError(RuntimeError):
    """A recoverable failure while processing one frame for pixel-art output."""


def quantize(
    img: Image.Image,
    colors: int = 32,
    downscale: int = 1,
    *,
    target_size: tuple[int, int] | None = None,
    output_scale: int = 1,
    palette: list[str] | tuple[str, ...] | None = None,
) -> Image.Image:
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
    if output_scale < 1:
        raise ValueError("output_scale must be >= 1")
    if target_size is not None and (target_size[0] < 1 or target_size[1] < 1):
        raise ValueError("target_size dimensions must be >= 1")

    try:
        rgba = img if img.mode == "RGBA" else img.convert("RGBA")
        if target_size is not None:
            rgba = rgba.resize(target_size, Image.Resampling.NEAREST)
        w, h = rgba.size

        if downscale > 1:
            small = rgba.resize(
                (max(1, w // downscale), max(1, h // downscale)), Image.NEAREST
            )
        else:
            small = rgba

        r, g, b, a = small.split()
        rgb = Image.merge("RGB", (r, g, b))
        if palette:
            palette_img = rgb.quantize(
                palette=_palette_image(palette), dither=Image.Dither.NONE
            )
        else:
            palette_img = rgb.quantize(
                colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
            )
        rgb_q = palette_img.convert("RGB")
        result = Image.merge("RGBA", (*rgb_q.split(), a))

        if downscale > 1:
            result = result.resize((w, h), Image.NEAREST)
        if output_scale > 1:
            result = result.resize(
                (w * output_scale, h * output_scale), Image.Resampling.NEAREST
            )
        return result
    except Exception as exc:  # noqa: BLE001 - isolate Pillow processing per frame
        raise PixelateError(f"pixel-art processing failed: {exc}") from exc


def build_shared_palette(images: list[Image.Image], colors: int) -> list[str]:
    """Extract one deterministic palette from a sequence of RGBA sources."""

    if not images:
        raise ValueError("at least one image is required")
    if not 1 <= colors <= 256:
        raise ValueError("colors must be between 1 and 256")
    ordered = sorted(
        (image.convert("RGBA") for image in images),
        key=lambda image: (image.size, image.tobytes()),
    )
    widths = [image.width for image in ordered]
    strip = Image.new("RGB", (sum(widths), max(image.height for image in ordered)))
    x = 0
    for image in ordered:
        rgb = image.convert("RGB")
        strip.paste(rgb, (x, 0))
        x += image.width
    reduced = strip.quantize(
        colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )
    raw = reduced.getpalette() or []
    flattened = getattr(reduced, "get_flattened_data", reduced.getdata)()
    used = sorted(set(flattened))
    return [
        f"#{raw[index * 3]:02X}{raw[index * 3 + 1]:02X}{raw[index * 3 + 2]:02X}"
        for index in used
    ]


extract_shared_palette = build_shared_palette


def _palette_image(colors: list[str] | tuple[str, ...]) -> Image.Image:
    if not 1 <= len(colors) <= 256:
        raise ValueError("palette must contain between 1 and 256 colors")
    entries: list[int] = []
    for color in colors:
        if len(color) != 7 or not color.startswith("#"):
            raise ValueError("palette colors must use #RRGGBB")
        entries.extend(int(color[offset : offset + 2], 16) for offset in (1, 3, 5))
    entries.extend([0] * (768 - len(entries)))
    palette_image = Image.new("P", (1, 1))
    palette_image.putpalette(entries)
    return palette_image
