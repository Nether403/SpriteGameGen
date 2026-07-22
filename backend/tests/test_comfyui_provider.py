from io import BytesIO
import json

import httpx
from PIL import Image
import pytest

from app.models import Style
from app.services.comfyui_provider import ComfyUIProvider, validate_loopback_url


def _descriptor(tmp_path):
    (tmp_path / "workflow.json").write_text(
        json.dumps(
            {
                "1": {"inputs": {"text": ""}},
                "2": {"inputs": {"image": ""}},
                "9": {"inputs": {}},
            }
        ), encoding="utf-8"
    )
    path = tmp_path / "workflow.sprite.json"
    path.write_text(
        json.dumps(
            {
                "format": "sprite-comfyui-workflow",
                "format_version": 1,
                "workflow_file": "workflow.json",
                "prompt": {"node_id": "1", "input_name": "text"},
                "identity_image": {"node_id": "2", "input_name": "image"},
                "output_node_id": "9",
            }
        ), encoding="utf-8"
    )
    return path


@pytest.mark.parametrize(
    "url",
    ["http://example.com:8188", "http://127.0.0.1", "http://127.0.0.1:8188/path", "http://user@localhost:8188"],
)
def test_url_rejects_non_loopback_or_ambiguous_boundaries(url):
    with pytest.raises(ValueError):
        validate_loopback_url(url)


def test_provider_uploads_submits_polls_and_decodes(tmp_path):
    output = BytesIO()
    Image.new("RGBA", (2, 2), "red").save(output, format="PNG")
    paths = []

    def handler(request: httpx.Request):
        paths.append(request.url.path)
        if request.url.path == "/upload/image":
            return httpx.Response(200, json={"name": "identity.png"})
        if request.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "owned"})
        if request.url.path == "/history/owned":
            return httpx.Response(200, json={"owned": {"outputs": {"9": {"images": [{"filename": "out.png"}]}}}})
        if request.url.path == "/view":
            return httpx.Response(200, content=output.getvalue())
        raise AssertionError(request.url)

    client = httpx.Client(
        base_url="http://127.0.0.1:8188",
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        trust_env=False,
    )
    provider = ComfyUIProvider(
        base_url="http://127.0.0.1:8188",
        descriptor_path=str(_descriptor(tmp_path)),
        client=client,
        sleep=lambda _: None,
    )

    image = provider.generate("knight", Style.PIXEL, reference=Image.new("RGBA", (1, 1)))

    assert image.size == (2, 2)
    assert paths == ["/upload/image", "/prompt", "/history/owned", "/view"]
    assert "/interrupt" not in paths


def test_cancellation_deletes_only_owned_queued_prompt(tmp_path):
    requests = []
    client = httpx.Client(
        base_url="http://127.0.0.1:8188",
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={})
        ),
    )
    provider = ComfyUIProvider(
        base_url="http://127.0.0.1:8188",
        descriptor_path=str(_descriptor(tmp_path)),
        client=client,
    )
    provider._owned_prompts.add("ours")

    assert provider.cancel_queued("other") is False
    assert provider.cancel_queued("ours") is True
    assert [request.url.path for request in requests] == ["/queue"]
    assert b"ours" in requests[0].content
    assert provider._draining is True
    with pytest.raises(Exception, match="unconfirmed running job"):
        provider.generate("blocked", Style.PIXEL)
