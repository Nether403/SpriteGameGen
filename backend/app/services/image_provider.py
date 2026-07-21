"""Provider-neutral image generation contracts and errors.

Concrete providers keep their SDK and transport details behind this boundary so
the sprite pipeline can select a provider without knowing how it authenticates
or parses responses.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import threading
from typing import Protocol

from PIL import Image

from app.models import Direction, Style, ViewMode


class ImageProviderError(RuntimeError):
    """A provider failed to return a usable image after its retry policy."""


class ImageSafetyBlockedError(ImageProviderError):
    """A provider rejected the request for safety reasons; do not retry it."""


class ImageProviderTimeoutError(ImageProviderError):
    """A provider request exceeded its configured timeout."""


_PROVIDER_SEMAPHORE_LOCK = threading.Lock()


@contextmanager
def provider_concurrency_slot(
    provider: object,
    *,
    check_cancelled: Callable[[], None] | None = None,
) -> Iterator[None]:
    """Bound calls across every service sharing one cached provider instance."""

    semaphore = getattr(provider, "_sprite_concurrency_semaphore", None)
    if semaphore is None:
        with _PROVIDER_SEMAPHORE_LOCK:
            semaphore = getattr(provider, "_sprite_concurrency_semaphore", None)
            if semaphore is None:
                limit = max(1, int(getattr(provider, "max_concurrency", 1)))
                semaphore = threading.BoundedSemaphore(limit)
                setattr(provider, "_sprite_concurrency_semaphore", semaphore)

    acquired = False
    try:
        while not acquired:
            if check_cancelled is not None:
                check_cancelled()
            acquired = semaphore.acquire(timeout=0.05)
        if check_cancelled is not None:
            check_cancelled()
        yield
    finally:
        if acquired:
            semaphore.release()


class ImageProvider(Protocol):
    """The image operations required by the sprite workflow."""

    max_concurrency: int

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
