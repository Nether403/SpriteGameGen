"""Azure OpenAI GPT Image adapter.

The adapter uses Azure's OpenAI-compatible ``/openai/v1/images`` REST surface
directly. Keeping multipart construction and Azure-specific retries here leaves
the sprite workflow provider-neutral.
"""
from __future__ import annotations

import base64
import binascii
import io
import time
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from PIL import Image, UnidentifiedImageError

from app.models import Direction, Style, ViewMode
from app.services.image_provider import (
    ImageProviderError,
    ImageProviderTimeoutError,
    ImageSafetyBlockedError,
)
from app.services.prompt_builder import build_generate_prompt


_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_SAFETY_MARKERS = (
    "content_filter",
    "contentfilter",
    "responsibleaipolicyviolation",
    "safety",
    "blocked by a content filter",
)


class AzureImageError(ImageProviderError):
    """Azure returned an unusable response or exhausted its retry policy."""


class AzureImageTimeoutError(AzureImageError, ImageProviderTimeoutError):
    """An Azure image request exceeded its configured timeout."""


class AzureImageProvider:
    """Generate and edit images through an Azure GPT Image deployment."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment: str,
        quality: str = "low",
        size: str = "1024x1024",
        input_fidelity: str = "high",
        timeout_s: float = 180.0,
        max_retries: int = 2,
        backoff_base: float = 1.0,
        max_concurrency: int = 3,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not endpoint.strip() or not api_key.strip() or not deployment.strip():
            raise ValueError("Azure endpoint, API key, and deployment are required")
        self._base_url = _normalize_base_url(endpoint)
        self._api_key = api_key
        self._deployment = deployment
        self._quality = quality
        self._size = size
        self._input_fidelity = input_fidelity
        self._timeout_s = timeout_s
        self._max_retries = max(1, max_retries)
        self._backoff_base = backoff_base
        self.max_concurrency = max(1, max_concurrency)
        self._client = client or httpx.Client()
        self._sleep = sleep

    def generate(
        self,
        prompt: str,
        style: Style,
        reference: Image.Image | None = None,
        *,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> Image.Image:
        full_prompt = build_generate_prompt(prompt, style, view_mode, direction)
        if reference is not None:
            # Reference-conditioned generation is an edit operation in the GPT
            # Image API, so identity/style guidance remains an actual image input.
            return self.edit(reference, full_prompt)
        response = self._request(
            "generations",
            json={
                "model": self._deployment,
                "prompt": full_prompt,
                "n": 1,
                "size": self._size,
                "quality": self._quality,
                "output_format": "png",
            },
        )
        return self._parse_image(response)

    def edit(
        self,
        base_img: Image.Image,
        prompt: str,
        *,
        pose_reference: Image.Image | None = None,
    ) -> Image.Image:
        files = [
            ("image[]", ("identity.png", _to_png_bytes(base_img), "image/png")),
        ]
        if pose_reference is not None:
            files.append(
                ("image[]", ("pose.png", _to_png_bytes(pose_reference), "image/png"))
            )
        response = self._request(
            "edits",
            data={
                "model": self._deployment,
                "prompt": prompt,
                "n": "1",
                "size": self._size,
                "quality": self._quality,
                "output_format": "png",
                "input_fidelity": self._input_fidelity,
            },
            files=files,
        )
        return self._parse_image(response)

    def _request(self, operation: str, **kwargs) -> httpx.Response:
        url = f"{self._base_url}/images/{operation}?api-version=preview"
        headers = {"api-key": self._api_key, "User-Agent": "sprite-game-asset-tool/0.1"}
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._client.post(
                    url,
                    headers=headers,
                    timeout=self._timeout_s,
                    **kwargs,
                )
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    self._sleep(self._backoff_base * (2**attempt))
                    continue
                raise AzureImageTimeoutError(
                    f"Azure image call timed out after {self._timeout_s:g}s"
                ) from exc
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries - 1:
                    self._sleep(self._backoff_base * (2**attempt))
                    continue
                raise AzureImageError(f"Azure image transport failed: {exc}") from exc

            if response.is_success:
                return response

            message, code = _azure_error(response)
            searchable = f"{code} {message}".lower().replace("_", "")
            if any(marker.replace("_", "") in searchable for marker in _SAFETY_MARKERS):
                raise ImageSafetyBlockedError(
                    "Request was blocked by Azure safety filters; try rephrasing the prompt."
                )
            if response.status_code in _RETRYABLE_STATUS_CODES:
                last_error = AzureImageError(
                    f"Azure image call returned {response.status_code}: {message}"
                )
                if attempt < self._max_retries - 1:
                    self._sleep(_retry_delay(response, self._backoff_base, attempt))
                    continue
            raise AzureImageError(
                f"Azure image call returned {response.status_code}: {message}"
            )

        raise AzureImageError(f"Azure image call failed after retries: {last_error}")

    @staticmethod
    def _parse_image(response: httpx.Response) -> Image.Image:
        try:
            payload = response.json()
            encoded = payload["data"][0]["b64_json"]
            raw = base64.b64decode(encoded, validate=True)
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
            raise AzureImageError("Azure response contained no image data") from None
        except UnidentifiedImageError as exc:
            raise AzureImageError("Azure returned malformed image data") from exc


def _normalize_base_url(endpoint: str) -> str:
    """Accept a resource URL, v1 base URL, or full image operation URL."""
    value = endpoint.strip().rstrip("/")
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    for suffix in ("/images/generations", "/images/edits", "/images"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if not path.endswith("/openai/v1"):
        path = f"{path}/openai/v1" if path else "/openai/v1"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _to_png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    (image if image.mode == "RGBA" else image.convert("RGBA")).save(
        output, format="PNG"
    )
    return output.getvalue()


def _azure_error(response: httpx.Response) -> tuple[str, str]:
    try:
        error = response.json().get("error", {})
        if isinstance(error, str):
            return error, ""
        return str(error.get("message") or response.text), str(error.get("code") or "")
    except (ValueError, AttributeError):
        return response.text or "unknown Azure error", ""


def _retry_delay(response: httpx.Response, base: float, attempt: int) -> float:
    retry_after = response.headers.get("retry-after")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    retry_after_ms = response.headers.get("retry-after-ms")
    if retry_after_ms:
        try:
            return max(0.0, float(retry_after_ms) / 1000)
        except ValueError:
            pass
    return base * (2**attempt)
