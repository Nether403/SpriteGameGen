"""Azure GPT Image provider transport and error behavior."""
from __future__ import annotations

import base64
import io

import httpx
from PIL import Image
import pytest

from app.models import Direction, Style, ViewMode
from app.services.azure_image_provider import (
    AzureImageError,
    AzureImageProvider,
)
from app.services.image_provider import ImageSafetyBlockedError


def _png_bytes(color: str = "red") -> bytes:
    output = io.BytesIO()
    Image.new("RGBA", (8, 8), color).save(output, format="PNG")
    return output.getvalue()


def _success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"data": [{"b64_json": base64.b64encode(_png_bytes()).decode()}]},
    )


def _provider(handler, **overrides) -> AzureImageProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    sleep = overrides.pop("sleep", lambda _: None)
    return AzureImageProvider(
        endpoint="https://sprites.openai.azure.com/openai/v1/images/generations",
        api_key="test-key",
        deployment="gpt-image-2-2",
        client=client,
        sleep=sleep,
        **overrides,
    )


def test_generate_uses_v1_endpoint_and_deployment_name():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["body"] = request.read()
        return _success_response()

    provider = _provider(handler)
    image = provider.generate(
        "a knight",
        Style.PIXEL,
        view_mode=ViewMode.SIDE_SCROLLER,
        direction=Direction.RIGHT,
    )

    request = seen["request"]
    assert str(request.url) == (
        "https://sprites.openai.azure.com/openai/v1/images/generations"
        "?api-version=preview"
    )
    assert request.headers["api-key"] == "test-key"
    assert b'"model":"gpt-image-2-2"' in seen["body"]
    assert image.mode == "RGBA"
    assert image.size == (8, 8)


def test_edit_sends_identity_and_pose_as_ordered_image_array_parts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["body"] = request.read()
        return _success_response()

    provider = _provider(handler)
    provider.edit(
        Image.new("RGBA", (8, 8), "red"),
        "copy the pose",
        pose_reference=Image.new("RGBA", (8, 8), "blue"),
    )

    request = seen["request"]
    body = seen["body"]
    assert str(request.url) == (
        "https://sprites.openai.azure.com/openai/v1/images/edits"
        "?api-version=preview"
    )
    assert request.headers["content-type"].startswith("multipart/form-data;")
    assert body.count(b'name="image[]"') == 2
    assert body.index(b'filename="identity.png"') < body.index(
        b'filename="pose.png"'
    )
    assert b'name="model"' in body and b"gpt-image-2-2" in body
    assert b'name="input_fidelity"' in body and b"high" in body


def test_rate_limit_is_retried_using_retry_after_header():
    attempts = 0
    sleeps = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(
                429,
                headers={"retry-after": "2"},
                json={"error": {"code": "RateLimitReached", "message": "slow down"}},
            )
        return _success_response()

    provider = _provider(
        handler,
        max_retries=2,
        sleep=sleeps.append,
    )
    provider.generate("a knight", Style.HIRES)

    assert attempts == 2
    assert sleeps == [2.0]


def test_content_filter_error_is_not_retried():
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "content_filter",
                    "message": "The prompt was blocked by a content filter.",
                }
            },
        )

    provider = _provider(handler, max_retries=3)

    with pytest.raises(ImageSafetyBlockedError, match="safety filters"):
        provider.generate("blocked", Style.HIRES)
    assert attempts == 1


def test_malformed_success_response_has_actionable_error():
    provider = _provider(lambda _: httpx.Response(200, json={"data": []}))

    with pytest.raises(AzureImageError, match="no image data"):
        provider.generate("a knight", Style.HIRES)


def test_declares_bounded_animation_concurrency():
    provider = _provider(lambda _: _success_response(), max_concurrency=3)
    assert provider.max_concurrency == 3
