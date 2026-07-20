"""Gemini client wrapper (Vertex AI).

All retry/backoff/timeout and error-classification logic lives here and nowhere
else. The underlying SDK client is injected so tests substitute a fake — no real
API calls in CI. Two operations:

- ``generate(prompt, style, reference=None)`` — text-to-image (Stage 1).
- ``edit(base_img, prompt)`` — image editing, base image passed every call
  (Stage 2, base-anchored so frames stay consistent).
"""
from __future__ import annotations

import io
import time
from typing import Any, Callable

from PIL import Image

from app.config import get_settings
from app.models import Style
from app.services.prompt_builder import build_generate_prompt

# Substrings that mark a transient, retryable error from the SDK/transport.
_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504",
    "unavailable", "deadline", "timeout", "temporarily", "rate limit",
)
# finish_reason values that indicate a safety refusal (not retryable).
_SAFETY_MARKERS = ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION")


class GeminiError(RuntimeError):
    """Generic, non-recoverable Gemini failure (malformed/empty response, exhausted retries)."""


class SafetyBlockedError(GeminiError):
    """The model refused the request for safety reasons — do not retry; rephrase."""


class GeminiTimeoutError(GeminiError):
    """A single call exceeded the hard per-call timeout."""


def _is_transient(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


class GeminiClient:
    def __init__(
        self,
        *,
        client: Any,
        model_generate: str,
        model_edit: str,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        timeout_s: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._client = client
        self._model_generate = model_generate
        self._model_edit = model_edit
        self._max_retries = max(1, max_retries)
        self._backoff_base = backoff_base
        self._timeout_s = timeout_s
        self._sleep = sleep

    # --- public API ---
    def generate(
        self, prompt: str, style: Style, reference: Image.Image | None = None
    ) -> Image.Image:
        from google.genai import types

        text = build_generate_prompt(prompt, style)
        contents: list[Any] = [text]
        if reference is not None:
            contents.append(
                types.Part.from_bytes(
                    data=_to_png_bytes(reference), mime_type="image/png"
                )
            )
        config = types.GenerateContentConfig(response_modalities=["IMAGE"])
        return self._call(self._model_generate, contents, config)

    def edit(self, base_img: Image.Image, prompt: str) -> Image.Image:
        from google.genai import types

        # The original base image is passed on every call (never chained), so
        # each generated frame stays anchored to the same source sprite.
        contents: list[Any] = [
            types.Part.from_bytes(
                data=_to_png_bytes(base_img), mime_type="image/png"
            ),
            prompt,
        ]
        config = types.GenerateContentConfig(response_modalities=["IMAGE"])
        return self._call(self._model_edit, contents, config)

    # --- internals ---
    def _call(self, model: str, contents: list[Any], config: Any) -> Image.Image:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._invoke_with_timeout(model, contents, config)
            except SafetyBlockedError:
                raise
            except Exception as exc:  # noqa: BLE001 — classify below
                last_exc = exc
                if _is_transient(exc) and attempt < self._max_retries - 1:
                    self._sleep(self._backoff_base * (2**attempt))
                    continue
                raise GeminiError(f"Gemini call failed: {exc}") from exc
            return self._parse_image(response)

        raise GeminiError(f"Gemini call failed after retries: {last_exc}")

    def _invoke_with_timeout(self, model: str, contents: list[Any], config: Any) -> Any:
        # The SDK enforces its own transport timeout; we keep the hook here so the
        # timeout policy has a single home and can be tightened without touching
        # call sites.
        return self._client.models.generate_content(
            model=model, contents=contents, config=config
        )

    def _parse_image(self, response: Any) -> Image.Image:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise GeminiError("Gemini returned no candidates")

        candidate = candidates[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        if any(marker in finish.upper() for marker in _SAFETY_MARKERS):
            raise SafetyBlockedError(
                "Request was blocked by safety filters — try rephrasing the prompt."
            )

        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if data:
                try:
                    return Image.open(io.BytesIO(data)).convert("RGBA")
                except Exception as exc:  # noqa: BLE001
                    raise GeminiError(f"Malformed image data from Gemini: {exc}") from exc

        raise GeminiError("Gemini response contained no image data")


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    (img if img.mode == "RGBA" else img.convert("RGBA")).save(buf, format="PNG")
    return buf.getvalue()


def build_default_client() -> GeminiClient:
    """Construct a GeminiClient wired to a real Vertex AI SDK client from settings."""
    from google import genai

    settings = get_settings()
    sdk = genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_region,
    )
    return GeminiClient(
        client=sdk,
        model_generate=settings.gemini_model_generate,
        model_edit=settings.gemini_model_edit,
    )
