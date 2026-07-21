"""Gemini client wrapper: request shaping + retry/error classification (mocked SDK)."""
import io

import pytest
from PIL import Image

from app.models import Style
from app.services.gemini_client import (
    GeminiClient,
    GeminiError,
    SafetyBlockedError,
)


# --- Fakes emulating the google-genai SDK surface we depend on ---

def _png_bytes(color=(1, 2, 3, 255), size=(4, 4)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    return buf.getvalue()


class _InlineData:
    def __init__(self, data):
        self.data = data


class _Part:
    def __init__(self, data=None):
        self.inline_data = _InlineData(data) if data is not None else None


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Candidate:
    def __init__(self, parts, finish_reason=None):
        self.content = _Content(parts)
        self.finish_reason = finish_reason


class _Response:
    def __init__(self, parts, finish_reason=None):
        self.candidates = [_Candidate(parts, finish_reason)]


class FakeModels:
    """Records calls and returns queued responses/exceptions."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeSDK:
    def __init__(self, script):
        self.models = FakeModels(script)


def _make_client(script, **kwargs):
    sdk = FakeSDK(script)
    params = {
        "model_generate": "gen-model",
        "model_edit": "edit-model",
        "max_retries": 3,
        "backoff_base": 0.0,  # no real sleeping
        "sleep": lambda s: None,
    }
    params.update(kwargs)
    client = GeminiClient(client=sdk, **params)
    return client, sdk


# --- generate ---

def test_generate_uses_generate_model_and_image_modality():
    client, sdk = _make_client([_Response([_Part(_png_bytes())])])
    img = client.generate("a knight", Style.PIXEL)

    assert isinstance(img, Image.Image)
    assert img.mode == "RGBA"
    call = sdk.models.calls[0]
    assert call["model"] == "gen-model"
    # response_modalities requests an image
    assert list(call["config"].response_modalities) == ["IMAGE"]


def test_generate_without_reference_sends_text_only():
    client, sdk = _make_client([_Response([_Part(_png_bytes())])])
    client.generate("a knight", Style.PIXEL)
    contents = sdk.models.calls[0]["contents"]
    # no image Part present
    assert not any(hasattr(c, "inline_data") for c in _as_list(contents))


def test_generate_appends_reference_image_when_provided():
    ref = Image.new("RGBA", (5, 5), (9, 9, 9, 255))
    client, sdk = _make_client([_Response([_Part(_png_bytes())])])
    client.generate("a knight", Style.PIXEL, reference=ref)

    contents = _as_list(sdk.models.calls[0]["contents"])
    # a bytes-backed Part was appended alongside the text prompt
    assert any(_is_image_part(c) for c in contents)


# --- edit ---

def test_edit_uses_edit_model_and_passes_base_image():
    base = Image.new("RGBA", (6, 6), (5, 5, 5, 255))
    client, sdk = _make_client([_Response([_Part(_png_bytes())])])
    out = client.edit(base, "same character, walk frame 2")

    assert isinstance(out, Image.Image)
    call = sdk.models.calls[0]
    assert call["model"] == "edit-model"
    contents = _as_list(call["contents"])
    assert any(_is_image_part(c) for c in contents)


# --- error handling ---

def test_transient_error_is_retried_then_succeeds():
    client, sdk = _make_client(
        [RuntimeError("503 temporarily unavailable"),
         _Response([_Part(_png_bytes())])]
    )
    img = client.generate("a knight", Style.PIXEL)
    assert isinstance(img, Image.Image)
    assert len(sdk.models.calls) == 2  # retried once


def test_transient_error_exhausts_retries_raises_gemini_error():
    script = [RuntimeError("503 unavailable")] * 3
    client, sdk = _make_client(script, max_retries=3)
    with pytest.raises(GeminiError):
        client.generate("a knight", Style.PIXEL)
    assert len(sdk.models.calls) == 3


def test_safety_refusal_maps_to_safety_error_and_not_retried():
    resp = _Response([], finish_reason="SAFETY")
    client, sdk = _make_client([resp, resp, resp])
    with pytest.raises(SafetyBlockedError):
        client.generate("something", Style.PIXEL)
    assert len(sdk.models.calls) == 1  # not retried


def test_empty_response_maps_to_gemini_error():
    client, sdk = _make_client([_Response([_Part(None)])])
    with pytest.raises(GeminiError):
        client.generate("a knight", Style.PIXEL)


def test_no_candidates_maps_to_gemini_error():
    client, sdk = _make_client([_Response([])])
    with pytest.raises(GeminiError):
        client.generate("a knight", Style.PIXEL)


# --- helpers ---

def _as_list(contents):
    return contents if isinstance(contents, list) else [contents]


def _is_image_part(obj):
    # our wrapper builds image parts via types.Part.from_bytes; in tests the real
    # types is used, so detect a Part carrying inline image data.
    inline = getattr(obj, "inline_data", None)
    return inline is not None and getattr(inline, "mime_type", "").startswith("image/") \
        if inline is not None else False


# --- build_default_client credential selection ---

class _FakeSettings:
    def __init__(self, creds_path):
        self.google_application_credentials = creds_path
        self.google_cloud_project = "proj-x"
        self.google_cloud_region = "us-central1"
        self.gemini_model_generate = "gen-model"
        self.gemini_model_edit = "edit-model"


def _patch_sdk(monkeypatch):
    """Capture the kwargs passed to genai.Client without a real client."""
    from google import genai

    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(genai, "Client", fake_client)
    return captured


def test_build_default_client_loads_service_account_when_set(monkeypatch, tmp_path):
    import app.services.gemini_client as gc

    key_file = tmp_path / "sa.json"
    key_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(gc, "get_settings", lambda: _FakeSettings(str(key_file)))

    sentinel_creds = object()
    seen = {}
    from google.oauth2 import service_account

    def fake_from_file(path, scopes=None):
        seen["path"] = path
        seen["scopes"] = scopes
        return sentinel_creds

    monkeypatch.setattr(
        service_account.Credentials, "from_service_account_file", staticmethod(fake_from_file)
    )
    captured = _patch_sdk(monkeypatch)

    client = gc.build_default_client()

    assert seen["path"] == str(key_file)
    assert "https://www.googleapis.com/auth/cloud-platform" in seen["scopes"]
    # explicit credentials passed to the SDK (not None)
    assert captured["credentials"] is sentinel_creds
    assert captured["vertexai"] is True
    assert captured["project"] == "proj-x"
    assert client._model_generate == "gen-model"
    assert client._model_edit == "edit-model"


def test_build_default_client_uses_adc_when_credentials_unset(monkeypatch):
    import app.services.gemini_client as gc

    monkeypatch.setattr(gc, "get_settings", lambda: _FakeSettings(""))
    captured = _patch_sdk(monkeypatch)

    # Must NOT attempt to load a service-account file; credentials stays None so
    # the SDK falls back to Application Default Credentials (gcloud).
    from google.oauth2 import service_account

    def _boom(*a, **k):  # pragma: no cover - should never be called
        raise AssertionError("should not load a service-account file for ADC")

    monkeypatch.setattr(
        service_account.Credentials, "from_service_account_file", staticmethod(_boom)
    )

    gc.build_default_client()

    assert captured["credentials"] is None
    assert captured["vertexai"] is True
    assert captured["project"] == "proj-x"
