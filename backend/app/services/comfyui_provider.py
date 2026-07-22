"""Loopback-only synchronous ComfyUI image provider."""
from __future__ import annotations

from io import BytesIO
import ipaddress
import time
import uuid
from urllib.parse import urlsplit

import httpx
from PIL import Image, UnidentifiedImageError

from app.models import Direction, Style, ViewMode
from app.services.comfyui_workflow import WorkflowCompiler
from app.services.image_provider import (
    ImageProviderError,
    ImageProviderTimeoutError,
    ProviderCapability,
)
from app.services.prompt_builder import build_generate_prompt


class ComfyUIProvider:
    max_concurrency = 1
    supports_cancel_check = True

    def __init__(
        self,
        *,
        base_url: str,
        descriptor_path: str,
        timeout_s: float = 180.0,
        poll_interval_s: float = 0.25,
        max_image_bytes: int = 32 * 1024 * 1024,
        max_image_pixels: int = 16 * 1024 * 1024,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ):
        self.base_url = validate_loopback_url(base_url)
        self.compiler = WorkflowCompiler(descriptor_path)
        self.capabilities = frozenset(
            ProviderCapability(value) for value in self.compiler.capabilities
        )
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s
        self.max_image_bytes = max_image_bytes
        self.max_image_pixels = max_image_pixels
        self._client = client or httpx.Client(
            base_url=self.base_url,
            timeout=min(timeout_s, 30),
            trust_env=False,
            follow_redirects=False,
        )
        self._sleep = sleep
        self._owned_prompts: set[str] = set()
        self._draining = False

    def generate(
        self,
        prompt: str,
        style: Style,
        reference: Image.Image | None = None,
        *,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
        seed: int | None = None,
        cancel_check=None,
    ) -> Image.Image:
        if self._draining:
            raise ImageProviderError("ComfyUI has an unconfirmed running job")
        identity = self._upload(reference, "identity") if reference else None
        workflow = self.compiler.compile(
            prompt=build_generate_prompt(prompt, style, view_mode, direction),
            identity_image=identity,
            seed=seed,
        )
        return self._execute(workflow, cancel_check=cancel_check)

    def edit(
        self,
        base_img: Image.Image,
        prompt: str,
        *,
        pose_reference: Image.Image | None = None,
        seed: int | None = None,
        cancel_check=None,
    ) -> Image.Image:
        if self._draining:
            raise ImageProviderError("ComfyUI has an unconfirmed running job")
        if ProviderCapability.EDIT not in self.capabilities:
            raise ImageProviderError("ComfyUI workflow does not support identity edits")
        identity = self._upload(base_img, "identity")
        pose = self._upload(pose_reference, "pose") if pose_reference else None
        workflow = self.compiler.compile(
            prompt=prompt, identity_image=identity, pose_image=pose, seed=seed
        )
        return self._execute(workflow, cancel_check=cancel_check)

    def cancel_queued(self, prompt_id: str) -> bool:
        if prompt_id not in self._owned_prompts:
            return False
        self._draining = True
        response = self._request("POST", "/queue", json={"delete": [prompt_id]})
        self._owned_prompts.discard(prompt_id)
        return response.status_code < 300

    def _upload(self, image: Image.Image | None, role: str) -> str:
        assert image is not None
        output = BytesIO()
        image.convert("RGBA").save(output, format="PNG")
        filename = f"spritegamegen-{role}-{uuid.uuid4().hex}.png"
        response = self._request(
            "POST",
            "/upload/image",
            files={"image": (filename, output.getvalue(), "image/png")},
            data={"overwrite": "false"},
        )
        data = response.json()
        name = data.get("name")
        if not isinstance(name, str):
            raise ImageProviderError("ComfyUI upload returned no image name")
        return name

    def _execute(self, workflow: dict, *, cancel_check=None) -> Image.Image:
        response = self._request("POST", "/prompt", json={"prompt": workflow})
        prompt_id = response.json().get("prompt_id")
        if not isinstance(prompt_id, str):
            raise ImageProviderError("ComfyUI submit returned no prompt ID")
        self._owned_prompts.add(prompt_id)
        deadline = time.monotonic() + self.timeout_s
        while time.monotonic() < deadline:
            if cancel_check is not None:
                try:
                    cancel_check()
                except Exception:
                    self._draining = True
                    try:
                        self.cancel_queued(prompt_id)
                    except ImageProviderError:
                        self._draining = True
                    raise
            try:
                history = self._request("GET", f"/history/{prompt_id}").json()
            except ImageProviderTimeoutError:
                self._draining = True
                raise
            except ImageProviderError:
                self._draining = True
                raise
            record = history.get(prompt_id)
            if record:
                self._owned_prompts.discard(prompt_id)
                output = record.get("outputs", {}).get(
                    self.compiler.descriptor.output_node_id, {}
                )
                images = output.get("images", [])
                if not images:
                    raise ImageProviderError("ComfyUI workflow produced no image")
                image = images[0]
                result = self._request(
                    "GET",
                    "/view",
                    params={
                        "filename": image.get("filename", ""),
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    },
                )
                return self._decode(result.content)
            self._sleep(self.poll_interval_s)
        # A running job cannot be interrupted safely. Keep ownership recorded so
        # callers do not reuse this provider slot until an operator resolves it.
        self._draining = True
        raise ImageProviderTimeoutError("ComfyUI workflow timed out while still running")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise ImageProviderTimeoutError("ComfyUI request timed out") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ImageProviderError("ComfyUI request failed") from exc

    def _decode(self, payload: bytes) -> Image.Image:
        if len(payload) > self.max_image_bytes:
            raise ImageProviderError("ComfyUI image exceeds the byte limit")
        try:
            with Image.open(BytesIO(payload)) as image:
                image.load()
                if image.width * image.height > self.max_image_pixels:
                    raise ImageProviderError("ComfyUI image exceeds the pixel limit")
                return image.convert("RGBA")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageProviderError("ComfyUI returned an invalid image") from exc


def validate_loopback_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or not parsed.port:
        raise ValueError("ComfyUI URL must use HTTP(S) loopback with an explicit port")
    host = parsed.hostname.lower()
    try:
        loopback = ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = host == "localhost"
    if (
        not loopback
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("ComfyUI URL must be loopback-only without credentials or query")
    return f"{parsed.scheme}://{parsed.netloc.rstrip('/')}"
