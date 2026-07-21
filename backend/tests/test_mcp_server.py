"""Protocol-contract tests for the local FastMCP adapter."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image

from app.mcp_server import APP_VERSION, create_mcp_server
from app.models import (
    Frame,
    FrameErrorCode,
    FrameStatus,
    ImageProviderName,
    Project,
    Style,
)
from app.services.provider_selection import ProviderRegistry
from app.services.sprite_runtime import SpriteRuntime
from app.storage.project_store import ProjectStore


TOOL_NAMES = {
    "get_capabilities",
    "list_projects",
    "get_project",
    "enhance_prompt",
    "generate_sprite",
    "animate",
    "regenerate_frame",
    "export_sheet",
}

INPUT_FIELDS = {
    "get_capabilities": set(),
    "list_projects": set(),
    "get_project": {"project_id"},
    "enhance_prompt": {"prompt", "style", "view_mode", "direction"},
    "generate_sprite": {
        "prompt",
        "style",
        "view_mode",
        "direction",
        "enhanced_prompt",
        "provider",
    },
    "animate": {"project_id", "action", "direction", "frames", "fps"},
    "regenerate_frame": {"project_id", "index"},
    "export_sheet": {"project_id", "format", "padding", "cols"},
}

OUTPUT_FIELDS = {
    "get_capabilities": {
        "app_version",
        "providers",
        "presets",
        "camera_directions",
        "limits",
    },
    "list_projects": {"projects"},
    "get_project": {
        "project",
        "sprite_path",
        "sprite_resource_uri",
        "health",
        "resume_available",
    },
    "enhance_prompt": {
        "outcome",
        "provider",
        "original_prompt",
        "enhanced_prompt",
    },
    "generate_sprite": {
        "outcome",
        "project",
        "sprite_path",
        "sprite_resource_uri",
    },
    "animate": {"outcome", "project", "frame_paths", "frame_resource_uris"},
    "regenerate_frame": {
        "outcome",
        "project",
        "frame",
        "frame_path",
        "frame_resource_uri",
    },
    "export_sheet": {
        "outcome",
        "project_id",
        "revision",
        "provider",
        "sheet_path",
        "sheet_resource_uri",
        "atlas_path",
        "atlas_resource_uri",
    },
}

ANNOTATIONS = {
    "get_capabilities": (True, False, True, False),
    "list_projects": (True, False, True, False),
    "get_project": (True, False, True, False),
    "enhance_prompt": (True, False, False, True),
    "generate_sprite": (False, False, False, True),
    "animate": (False, True, False, True),
    "regenerate_frame": (False, True, False, True),
    "export_sheet": (False, True, True, False),
}


class FakeProvider:
    def __init__(self, *, fail: Exception | None = None):
        self.fail = fail
        self.generate_calls = 0
        self.edit_calls = 0
        self.enhance_calls = 0
        self.max_concurrency = 1

    @staticmethod
    def _image() -> Image.Image:
        image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
        image.paste(Image.new("RGBA", (8, 8), "red"), (8, 8))
        return image

    def enhance_prompt(self, prompt, style, view_mode, direction):
        self.enhance_calls += 1
        if self.fail:
            raise self.fail
        return f"enhanced {prompt}"

    def generate(self, prompt, style, reference=None, *, view_mode, direction):
        self.generate_calls += 1
        if self.fail:
            raise self.fail
        return self._image()

    def edit(self, base, prompt, *, pose_reference=None):
        self.edit_calls += 1
        if self.fail:
            raise self.fail
        return self._image()


def _runtime(
    tmp_path,
    *,
    gemini=None,
    azure=None,
    operation_timeout_seconds=600.0,
    creative_operation_max_concurrency=2,
) -> SpriteRuntime:
    return SpriteRuntime(
        store=ProjectStore(tmp_path),
        providers=ProviderRegistry(gemini=gemini, azure=azure),
        remover=lambda image: image,
        operation_timeout_seconds=operation_timeout_seconds,
        creative_operation_max_concurrency=creative_operation_max_concurrency,
    )


def _schema_fields(schema: dict) -> set[str]:
    return set(schema.get("properties", {}))


async def test_exact_tool_inventory_annotations_and_schema_contract(tmp_path):
    server = create_mcp_server(runtime=_runtime(tmp_path))

    async with create_connected_server_and_client_session(server) as session:
        listed = await session.list_tools()
        tools = {tool.name: tool for tool in listed.tools}

        assert set(tools) == TOOL_NAMES
        assert {
            name: _schema_fields(tool.inputSchema) for name, tool in tools.items()
        } == INPUT_FIELDS
        assert {
            name: _schema_fields(tool.outputSchema) for name, tool in tools.items()
        } == OUTPUT_FIELDS

        for name, expected in ANNOTATIONS.items():
            annotations = tools[name].annotations
            assert annotations is not None
            assert annotations.title
            assert (
                annotations.readOnlyHint,
                annotations.destructiveHint,
                annotations.idempotentHint,
                annotations.openWorldHint,
            ) == expected

        for tool in tools.values():
            assert tool.description
            assert "billing" in tool.description.lower()
            assert "overwrite" in tool.description.lower()

        generate = tools["generate_sprite"].inputSchema
        assert generate["properties"]["prompt"]["maxLength"] == 2000
        assert generate["properties"]["prompt"]["minLength"] == 1
        assert generate["properties"]["prompt"]["description"]
        assert generate["properties"]["provider"]["description"]
        provider_ref = generate["properties"]["provider"]["$ref"].split("/")[-1]
        assert generate["$defs"][provider_ref]["enum"] == [
            "auto",
            "azure",
            "gemini",
        ]

        animate = tools["animate"].inputSchema["properties"]
        assert animate["frames"]["anyOf"][0] == {
            "maximum": 8,
            "minimum": 2,
            "type": "integer",
        }
        assert animate["fps"]["minimum"] == 1
        assert animate["fps"]["maximum"] == 60
        assert animate["action"]["description"]

        export = tools["export_sheet"].inputSchema["properties"]
        assert export["padding"]["minimum"] == 0
        assert export["padding"]["maximum"] == 256
        assert export["cols"]["anyOf"][0]["maximum"] == 64

        project_ref = tools["get_project"].outputSchema["properties"]["project"][
            "$ref"
        ].split("/")[-1]
        project_schema = tools["get_project"].outputSchema["$defs"][project_ref]
        frame_ref = project_schema["properties"]["frames"]["items"]["$ref"].split(
            "/"
        )[-1]
        frame_schema = tools["get_project"].outputSchema["$defs"][frame_ref]
        assert "url" not in frame_schema["properties"]
        assert {
            "index",
            "status",
            "error_code",
            "error_message",
            "path",
            "resource_uri",
        } == set(frame_schema["properties"])
        assert {"revision", "provider", "manifest_resource_uri"} <= set(
            project_schema["properties"]
        )


async def test_capabilities_are_complete_and_unknown_arguments_are_sdk_limited(
    tmp_path,
):
    server = create_mcp_server(runtime=_runtime(tmp_path))

    async with create_connected_server_and_client_session(server) as session:
        # FastMCP 1.28.1's generated argument models ignore unknown top-level
        # keys. Its public decorator has no strict-extra switch, so this behavior
        # is documented rather than changed through private SDK internals.
        result = await session.call_tool(
            "get_capabilities", {"unknown_top_level_argument": True}
        )

    assert result.isError is False
    capabilities = result.structuredContent
    assert capabilities["app_version"] == APP_VERSION
    assert [provider["id"] for provider in capabilities["providers"]] == [
        "auto",
        "azure",
        "gemini",
        "hyperagent",
    ]
    assert [preset["action"] for preset in capabilities["presets"]] == [
        "idle",
        "walk",
        "run",
        "attack",
        "jump",
    ]
    assert capabilities["camera_directions"] == [
        {"view_mode": "side_scroller", "directions": ["left", "right"]},
        {
            "view_mode": "top_down_2_5d",
            "directions": [
                "left",
                "right",
                "up",
                "down",
                "up_left",
                "up_right",
                "down_left",
                "down_right",
            ],
        },
    ]
    assert capabilities["limits"] == {
        "max_prompt_characters": 2000,
        "max_upload_bytes": 10 * 1024 * 1024,
        "max_image_dimension_pixels": 8192,
        "max_image_pixels": 16 * 1024 * 1024,
        "max_export_padding_pixels": 256,
        "max_export_columns": 64,
        "max_sheet_dimension_pixels": 8192,
        "max_sheet_pixels": 32 * 1024 * 1024,
        "max_sheet_bytes": 64 * 1024 * 1024,
        "max_frame_error_message_characters": 200,
    }


async def test_default_lifespan_starts_storage_only_without_cloud_clients(
    monkeypatch, tmp_path
):
    env_file = tmp_path / "config" / "sprite.env"
    env_file.parent.mkdir()
    env_file.write_text("PROJECTS_DIR=relative-projects\n", encoding="utf-8")
    monkeypatch.setenv("SPRITE_ENV_FILE", str(env_file.resolve()))
    for key in (
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "PROJECTS_DIR",
    ):
        monkeypatch.delenv(key, raising=False)

    import app.config as config
    import app.deps as deps
    import app.mcp_server as mcp_server

    config.get_settings.cache_clear()
    settings = config.get_settings()
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_server, "get_settings", lambda: settings)
    deps._default_store.cache_clear()
    deps._default_gemini.cache_clear()
    deps._default_azure.cache_clear()
    monkeypatch.setattr(
        deps,
        "build_default_client",
        lambda: pytest.fail("Gemini client must not be constructed"),
    )
    monkeypatch.setattr(
        deps,
        "AzureImageProvider",
        lambda **kwargs: pytest.fail("Azure client must not be constructed"),
    )
    try:
        server = create_mcp_server()
        async with create_connected_server_and_client_session(server) as session:
            tools = await session.list_tools()
            projects = await session.call_tool("list_projects", {})
        assert {tool.name for tool in tools.tools} == TOOL_NAMES
        assert projects.structuredContent == {"projects": []}
        assert (env_file.parent / "relative-projects").is_dir()
    finally:
        config.get_settings.cache_clear()
        deps._default_store.cache_clear()
        deps._default_gemini.cache_clear()
        deps._default_azure.cache_clear()


async def test_creative_workflow_honors_explicit_and_stored_azure_provider(tmp_path):
    gemini = FakeProvider()
    azure = FakeProvider()
    server = create_mcp_server(runtime=_runtime(tmp_path, gemini=gemini, azure=azure))

    async with create_connected_server_and_client_session(server) as session:
        generated = await session.call_tool(
            "generate_sprite",
            {"prompt": "a knight", "style": "pixel", "provider": "azure"},
        )
        pid = generated.structuredContent["project"]["id"]
        assert generated.structuredContent["project"]["provider"] == "azure"
        assert generated.structuredContent["outcome"] == "complete"

        animated = await session.call_tool(
            "animate",
            {"project_id": pid, "action": "idle", "frames": 2},
        )
        repaired = await session.call_tool(
            "regenerate_frame", {"project_id": pid, "index": 1}
        )

    assert animated.isError is False
    assert repaired.isError is False
    assert animated.structuredContent["project"]["provider"] == "azure"
    assert repaired.structuredContent["project"]["provider"] == "azure"
    assert azure.generate_calls == 1
    assert azure.edit_calls == 3
    assert gemini.generate_calls == 0
    assert gemini.edit_calls == 0


async def test_stored_provider_never_silently_falls_back(tmp_path):
    azure = FakeProvider()
    runtime = _runtime(tmp_path, azure=azure)
    pid = runtime.store.create()
    runtime.store.save_image(pid, "sprite", FakeProvider._image())
    runtime.store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a mage",
            style=Style.PIXEL,
            image_provider=ImageProviderName.GEMINI,
            frames=[Frame(index=0)],
        ),
    )
    server = create_mcp_server(runtime=runtime)

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "animate", {"project_id": pid, "action": "idle", "frames": 2}
        )

    assert result.isError is True
    assert "Gemini is not configured" in result.content[0].text
    assert azure.edit_calls == 0


async def test_project_dto_strips_stale_urls_and_exposes_paths_uris_and_errors(
    tmp_path,
):
    runtime = _runtime(tmp_path)
    pid = runtime.store.create()
    runtime.store.save_image(pid, "sprite", FakeProvider._image())
    runtime.store.save_image(pid, "frame_0", FakeProvider._image())
    project = Project(
        id=pid,
        prompt="a knight",
        style=Style.PIXEL,
        image_provider=ImageProviderName.AZURE,
        action="idle",
        fps=8,
        frames=[
            Frame(index=0, url="https://stale.invalid/frame.png"),
            Frame(
                index=1,
                url="https://stale.invalid/failed.png",
                status=FrameStatus.FAILED,
                error_code=FrameErrorCode.SAFETY,
                error_message="Image provider blocked this frame for safety.",
            ),
        ],
    )
    runtime.store.write_manifest(pid, project)
    server = create_mcp_server(runtime=runtime)

    async with create_connected_server_and_client_session(server) as session:
        detail = await session.call_tool("get_project", {"project_id": pid})

    payload = detail.structuredContent
    assert payload["project"]["revision"] == 1
    assert payload["project"]["provider"] == "azure"
    assert payload["project"]["manifest_resource_uri"] == (
        f"sprite://projects/{pid}/manifest"
    )
    assert "url" not in json.dumps(payload["project"])
    assert Path(payload["project"]["frames"][0]["path"]).is_absolute()
    assert payload["project"]["frames"][0]["resource_uri"].endswith(
        "/assets/frame_0.png"
    )
    assert payload["project"]["frames"][1] == {
        "index": 1,
        "status": "failed",
        "error_code": "safety",
        "error_message": "Image provider blocked this frame for safety.",
        "path": None,
        "resource_uri": None,
    }


async def test_project_manifest_and_asset_resources_reject_traversal(tmp_path):
    runtime = _runtime(tmp_path)
    pid = runtime.store.create()
    runtime.store.save_image(pid, "sprite", FakeProvider._image())
    runtime.store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a knight",
            style=Style.PIXEL,
            frames=[Frame(index=0)],
        ),
    )
    server = create_mcp_server(runtime=runtime)

    async with create_connected_server_and_client_session(server) as session:
        templates = await session.list_resource_templates()
        assert {item.uriTemplate for item in templates.resourceTemplates} == {
            "sprite://projects/{project_id}/manifest",
            "sprite://projects/{project_id}/assets/{filename}",
        }

        manifest = await session.read_resource(f"sprite://projects/{pid}/manifest")
        manifest_data = json.loads(manifest.contents[0].text)
        assert manifest_data["project"]["id"] == pid
        assert "url" not in json.dumps(manifest_data)

        asset = await session.read_resource(
            f"sprite://projects/{pid}/assets/sprite.png"
        )
        assert asset.contents[0].blob

        with pytest.raises(Exception, match="resource|Resource|unsafe|Unknown"):
            await session.read_resource(
                f"sprite://projects/{pid}/assets/%2E%2E%2Fproject.json"
            )
        with pytest.raises(Exception, match="resource|Resource|unsafe|Unknown"):
            await session.read_resource(
                "sprite://projects/%2E%2E/manifest"
            )


async def test_unexpected_errors_are_logged_with_request_id_and_sanitized(
    tmp_path, capsys
):
    provider = FakeProvider(fail=RuntimeError("top-secret-provider-detail"))
    server = create_mcp_server(runtime=_runtime(tmp_path, gemini=provider))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "generate_sprite",
            {"prompt": "a knight", "style": "pixel", "provider": "gemini"},
        )

    client_text = result.content[0].text
    assert result.isError is True
    assert "top-secret-provider-detail" not in client_text
    match = re.search(r"request ID: ([0-9a-f]{32})", client_text)
    assert match
    stderr = capsys.readouterr().err
    assert match.group(1) in stderr
    assert "top-secret-provider-detail" in stderr


async def test_ping_remains_responsive_during_slow_creative_tool(tmp_path):
    started = threading.Event()
    release = threading.Event()

    class SlowProvider(FakeProvider):
        def generate(self, *args, **kwargs):
            started.set()
            assert release.wait(timeout=2)
            return self._image()

    server = create_mcp_server(runtime=_runtime(tmp_path, gemini=SlowProvider()))

    async with create_connected_server_and_client_session(server) as session:
        timer = threading.Timer(0.5, release.set)
        timer.start()
        started_at = time.monotonic()
        call = asyncio.create_task(
            session.call_tool(
                "generate_sprite",
                {"prompt": "a knight", "style": "pixel", "provider": "gemini"},
            )
        )
        try:
            while not started.is_set():
                await asyncio.sleep(0.005)
            await asyncio.wait_for(session.send_ping(), timeout=0.2)
            assert time.monotonic() - started_at < 0.25
        finally:
            release.set()
            timer.cancel()
        result = await call

    assert result.isError is False


async def test_creative_tool_reports_monotonic_progress(tmp_path):
    progress = []
    provider = FakeProvider()
    server = create_mcp_server(runtime=_runtime(tmp_path, gemini=provider))

    async def record(current, total, message):
        progress.append((current, total, message))

    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool(
            "generate_sprite",
            {"prompt": "a knight", "style": "pixel", "provider": "gemini"},
            progress_callback=record,
        )

    assert result.isError is False
    assert len(progress) >= 3
    assert [item[0] for item in progress] == sorted(item[0] for item in progress)
    assert all(item[1] == 1.0 for item in progress)
    assert progress[-1][0] == 1.0
    assert all(item[2] for item in progress)


async def test_whole_operation_timeout_is_actionable_and_never_commits(tmp_path):
    class SlowProvider(FakeProvider):
        def generate(self, *args, **kwargs):
            time.sleep(0.15)
            return self._image()

    runtime = _runtime(
        tmp_path,
        gemini=SlowProvider(),
        operation_timeout_seconds=0.02,
    )
    server = create_mcp_server(runtime=runtime)

    async with create_connected_server_and_client_session(server) as session:
        started_at = time.monotonic()
        result = await session.call_tool(
            "generate_sprite",
            {"prompt": "a knight", "style": "pixel", "provider": "gemini"},
        )
        elapsed = time.monotonic() - started_at

    assert result.isError is True
    assert elapsed < 0.1
    assert "timed out" in result.content[0].text.lower()
    assert "no project changes were committed" in result.content[0].text.lower()
    await asyncio.sleep(0.15)
    assert list(runtime.store.root.iterdir()) == []


async def test_process_creative_limit_spans_concurrent_tool_requests(tmp_path):
    class ConcurrentProvider(FakeProvider):
        max_concurrency = 8

        def __init__(self):
            super().__init__()
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def generate(self, *args, **kwargs):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.04)
            with self.lock:
                self.active -= 1
            return self._image()

    provider = ConcurrentProvider()
    server = create_mcp_server(
        runtime=_runtime(
            tmp_path,
            gemini=provider,
            creative_operation_max_concurrency=1,
        )
    )

    async with create_connected_server_and_client_session(server) as session:
        first, second = await asyncio.gather(
            session.call_tool(
                "generate_sprite",
                {"prompt": "knight one", "style": "pixel", "provider": "gemini"},
            ),
            session.call_tool(
                "generate_sprite",
                {"prompt": "knight two", "style": "pixel", "provider": "gemini"},
            ),
        )

    assert first.isError is False
    assert second.isError is False
    assert provider.peak == 1


def test_stdio_console_entrypoint_smoke_from_foreign_cwd():
    repo_root = Path(__file__).resolve().parents[2]
    smoke = repo_root / "scripts" / "smoke_mcp.py"
    result = subprocess.run(
        [sys.executable, str(smoke)],
        cwd=Path(os.environ.get("TEMP", repo_root)),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.strip() == (
        "MCP smoke passed: " + ", ".join(sorted(TOOL_NAMES))
    )
