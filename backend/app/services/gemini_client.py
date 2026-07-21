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
from app.models import Direction, Style, ViewMode
from app.services.image_provider import (
    ImageProviderError,
    ImageProviderTimeoutError,
    ImageSafetyBlockedError,
)
from app.services.prompt_builder import build_generate_prompt

# Substrings that mark a transient, retryable error from the SDK/transport.
_TRANSIENT_MARKERS = (
    "429", "500", "502", "503", "504",
    "unavailable", "deadline", "timeout", "temporarily", "rate limit",
)
# finish_reason values that indicate a safety refusal (not retryable).
_SAFETY_MARKERS = ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "RECITATION")


class GeminiError(ImageProviderError):
    """Generic, non-recoverable Gemini failure (malformed/empty response, exhausted retries)."""


class SafetyBlockedError(GeminiError, ImageSafetyBlockedError):
    """The model refused the request for safety reasons — do not retry; rephrase."""


class GeminiTimeoutError(GeminiError, ImageProviderTimeoutError):
    """A single call exceeded the hard per-call timeout."""


def _is_transient(exc: Exception) -> bool:
    text = str(exc).lower()
    return _is_timeout(exc) or any(marker in text for marker in _TRANSIENT_MARKERS)


def _is_timeout(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return isinstance(exc, TimeoutError) or "timeout" in text or "deadline" in text


def _is_quota_exhausted(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "resource_exhausted" in text or "resource exhausted" in text


class GeminiClient:
    def __init__(
        self,
        *,
        client: Any,
        model_generate: str,
        model_edit: str,
        model_text: str,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        quota_backoff_s: float = 15.0,
        timeout_s: float = 120.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._client = client
        self._model_generate = model_generate
        self._model_edit = model_edit
        self._model_text = model_text
        self._max_retries = max(1, max_retries)
        self._backoff_base = backoff_base
        self._quota_backoff_s = quota_backoff_s
        self._timeout_s = timeout_s
        self._sleep = sleep

    # --- public API ---
    def generate(
        self,
        prompt: str,
        style: Style,
        reference: Image.Image | None = None,
        *,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> Image.Image:
        from google.genai import types

        text = build_generate_prompt(prompt, style, view_mode, direction)
        contents: list[Any] = [text]
        if reference is not None:
            contents.append(
                types.Part.from_bytes(
                    data=_to_png_bytes(reference), mime_type="image/png"
                )
            )
        config = self._content_config(types)
        response = self._request(self._model_generate, contents, config)
        return self._parse_image(response)

    def edit(
        self,
        base_img: Image.Image,
        prompt: str,
        *,
        pose_reference: Image.Image | None = None,
    ) -> Image.Image:
        from google.genai import types

        # The original base image is passed on every call (never chained), so
        # each generated frame stays anchored to the same source sprite.
        contents: list[Any] = [
            types.Part.from_bytes(
                data=_to_png_bytes(base_img), mime_type="image/png"
            ),
        ]
        if pose_reference is not None:
            contents.append(
                types.Part.from_bytes(
                    data=_to_png_bytes(pose_reference), mime_type="image/png"
                )
            )
        contents.append(prompt)
        config = self._content_config(types)
        response = self._request(self._model_edit, contents, config)
        return self._parse_image(response)

    def enhance_prompt(
        self,
        prompt: str,
        style: Style,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> str:
        """Expand a terse subject description for sprite generation.

        This is a preview-only text call. Callers decide whether its visible,
        editable result is later accepted for image generation.
        """

        from google.genai import types

        system_instruction = (
            "Rewrite the user's subject as one concise, sprite-friendly game-art "
            "description. Preserve the subject and intent. Add concrete visual "
            "details, silhouette, clothing/materials, and a readable color palette. "
            "Do not add scenery, camera instructions, explanations, headings, or "
            "Markdown. Return only the enhanced subject description."
        )
        contents = [
            f"Subject: {prompt.strip()}\n"
            f"Art style: {style.value}\n"
            f"View mode: {view_mode.value}\n"
            f"Direction: {direction.value}"
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            # Gemini 3.5 Flash counts hidden thought tokens against this cap.
            # Prompt rewriting needs almost no reasoning; MINIMAL prevents the
            # model from spending the budget before producing visible text.
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.MINIMAL
            ),
            max_output_tokens=512,
            response_mime_type="text/plain",
            http_options=types.HttpOptions(
                timeout=max(1, round(self._timeout_s * 1000))
            ),
        )
        response = self._request(self._model_text, contents, config)
        return self._parse_text(response)

    def _content_config(self, types: Any) -> Any:
        return types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            http_options=types.HttpOptions(timeout=max(1, round(self._timeout_s * 1000))),
        )

    # --- internals ---
    def _request(self, model: str, contents: list[Any], config: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._invoke_with_timeout(model, contents, config)
            except SafetyBlockedError:
                raise
            except Exception as exc:  # noqa: BLE001 — classify below
                last_exc = exc
                if _is_transient(exc) and attempt < self._max_retries - 1:
                    delay = self._backoff_base * (2**attempt)
                    if _is_quota_exhausted(exc):
                        # Vertex image quotas commonly need a meaningful cooldown;
                        # rapid exponential retries only repeat the same 429 and
                        # force users to regenerate frames manually.
                        delay = max(delay, self._quota_backoff_s)
                    self._sleep(delay)
                    continue
                if _is_timeout(exc) and attempt == self._max_retries - 1:
                    raise GeminiTimeoutError(
                        f"Gemini call timed out after {self._timeout_s:g}s"
                    ) from exc
                raise GeminiError(f"Gemini call failed: {exc}") from exc
            return response

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

    def _parse_text(self, response: Any) -> str:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            raise GeminiError("Gemini returned no candidates")

        candidate = candidates[0]
        finish = str(getattr(candidate, "finish_reason", "") or "")
        if any(marker in finish.upper() for marker in _SAFETY_MARKERS):
            raise SafetyBlockedError(
                "Request was blocked by safety filters — try rephrasing the prompt."
            )
        if "MAX_TOKENS" in finish.upper():
            raise GeminiError(
                "Gemini prompt enhancement was truncated; using the raw prompt instead."
            )

        result = str(getattr(response, "text", "") or "").strip()
        if not result:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            result = "\n".join(
                str(getattr(part, "text", "") or "").strip()
                for part in parts
                if getattr(part, "text", None)
            ).strip()
        if result.startswith("```") and result.endswith("```"):
            lines = result.splitlines()
            result = "\n".join(lines[1:-1]).strip()
        if not result:
            raise GeminiError("Gemini response contained no text")
        return result


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    (img if img.mode == "RGBA" else img.convert("RGBA")).save(buf, format="PNG")
    return buf.getvalue()


def build_default_client() -> GeminiClient:
    """Construct a GeminiClient wired to a real Vertex AI SDK client from settings.

    Credential resolution:
      * If ``GOOGLE_APPLICATION_CREDENTIALS`` is set, load that service-account
        JSON key explicitly (with the Vertex ``cloud-platform`` scope) and pass
        it to the client — this does not depend on the OS environment or a
        gcloud login.
      * Otherwise, let the SDK fall back to Application Default Credentials
        (e.g. ``gcloud auth application-default login``).
    """
    from google import genai

    settings = get_settings()
    credentials = None
    if settings.google_application_credentials:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(
            settings.google_application_credentials,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    sdk = genai.Client(
        vertexai=True,
        credentials=credentials,  # None => SDK uses ADC
        project=settings.google_cloud_project,
        location=settings.google_cloud_region,
    )
    return GeminiClient(
        client=sdk,
        model_generate=settings.gemini_model_generate,
        model_edit=settings.gemini_model_edit,
        model_text=settings.gemini_model_text,
        # Keep compatibility with lightweight settings fakes used by callers
        # that predate the timeout setting; production Settings always exposes it.
        timeout_s=getattr(settings, "gemini_timeout_seconds", 120.0),
        max_retries=getattr(settings, "gemini_max_retries", 5),
        backoff_base=getattr(settings, "gemini_backoff_seconds", 1.0),
        quota_backoff_s=getattr(settings, "gemini_quota_backoff_seconds", 15.0),
    )
