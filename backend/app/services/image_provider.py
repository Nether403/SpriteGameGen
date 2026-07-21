"""Provider-neutral image generation contracts and errors.

Concrete providers keep their SDK and transport details behind this boundary so
the sprite pipeline can select a provider without knowing how it authenticates
or parses responses.
"""
from __future__ import annotations

from typing import Protocol

from PIL import Image

from app.models import Direction, Style, ViewMode


class ImageProviderError(RuntimeError):
    """A provider failed to return a usable image after its retry policy."""


class ImageSafetyBlockedError(ImageProviderError):
    """A provider rejected the request for safety reasons; do not retry it."""


class ImageProviderTimeoutError(ImageProviderError):
    """A provider request exceeded its configured timeout."""


class ImageProvider(Protocol):
    """The image operations required by the sprite workflow."""

    def generate(
        self,
        prompt: str,
        style: Style,
        reference: Image.Image | None = None,
        *,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> Image.Image: ...

    def edit(
        self,
        base_img: Image.Image,
        prompt: str,
        *,
        pose_reference: Image.Image | None = None,
    ) -> Image.Image: ...


class PromptEnhancer(Protocol):
    """The text-only prompt enhancement operation, independent of image choice."""

    def enhance_prompt(
        self,
        prompt: str,
        style: Style,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> str: ...
