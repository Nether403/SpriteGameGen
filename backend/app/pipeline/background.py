"""Background removal wrapper.

The heavy ``rembg`` session is injected so unit tests substitute a fake and no
model is downloaded/loaded in CI. The default remover lazily builds a rembg
session on first real use. Output is always guaranteed RGBA.
"""
from __future__ import annotations

from typing import Callable

from PIL import Image

Remover = Callable[[Image.Image], Image.Image]


class BackgroundRemovalError(RuntimeError):
    """A recoverable failure from the background-removal dependency."""

# Lazily-built default rembg session (kept module-level so the model loads once).
_default_session = None


def _default_remover(img: Image.Image) -> Image.Image:
    """Remove the background using rembg. Imported lazily to avoid the heavy
    onnxruntime import (and model download) unless actually used."""
    global _default_session
    from rembg import new_session, remove as rembg_remove  # type: ignore

    if _default_session is None:
        _default_session = new_session()
    return rembg_remove(img, session=_default_session)


def remove(img: Image.Image, *, remover: Remover | None = None) -> Image.Image:
    """Return ``img`` with its background removed, always as an RGBA image.

    Args:
        remover: injectable cutout function; defaults to a lazy rembg session.
    """
    fn = remover if remover is not None else _default_remover
    try:
        result = fn(img)
    except Exception as exc:  # noqa: BLE001 - isolate the external remover boundary
        raise BackgroundRemovalError(f"background removal failed: {exc}") from exc
    if result.mode != "RGBA":
        result = result.convert("RGBA")
    return result
