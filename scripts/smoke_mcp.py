"""Exercise the installed sprite-mcp stdio entrypoint without cloud credentials."""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED_TOOLS = {
    "get_capabilities",
    "list_projects",
    "get_project",
    "enhance_prompt",
    "generate_sprite",
    "animate",
    "regenerate_frame",
    "export_sheet",
    "set_render_settings",
    "set_frame_adjustment",
    "update_clip",
    "delete_clip",
    "export_character_bundle",
    "validate_recipe",
    "get_project_recipe",
}


def _console_entrypoint() -> str:
    executable = "sprite-mcp.exe" if os.name == "nt" else "sprite-mcp"
    beside_python = Path(sys.executable).resolve().parent / executable
    if beside_python.is_file():
        return str(beside_python)
    discovered = shutil.which("sprite-mcp")
    if discovered:
        return discovered
    raise RuntimeError("Installed sprite-mcp console entrypoint was not found")


async def run() -> set[str]:
    with TemporaryDirectory(prefix="sprite-mcp-smoke-") as temporary:
        root = Path(temporary).resolve()
        projects_dir = root / "projects"
        foreign_cwd = root / "foreign-cwd"
        foreign_cwd.mkdir()
        env_file = root / "sprite.env"
        env_file.write_text(f"PROJECTS_DIR={projects_dir}\n", encoding="utf-8")

        child_env = dict(os.environ)
        for key in (
            "GOOGLE_APPLICATION_CREDENTIALS",
            "GOOGLE_CLOUD_PROJECT",
            "GOOGLE_CLOUD_REGION",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
        ):
            child_env.pop(key, None)
        child_env.update(
            {
                "SPRITE_ENV_FILE": str(env_file),
                "PROJECTS_DIR": str(projects_dir),
            }
        )

        params = StdioServerParameters(
            command=_console_entrypoint(),
            env=child_env,
            cwd=foreign_cwd,
        )
        with TemporaryFile(mode="w+", encoding="utf-8") as child_stderr:
            async with stdio_client(params, errlog=child_stderr) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    tools = {tool.name for tool in result.tools}
                    if tools != EXPECTED_TOOLS:
                        raise AssertionError(
                            f"Unexpected MCP tools: expected {sorted(EXPECTED_TOOLS)}, "
                            f"received {sorted(tools)}"
                        )
                    capabilities = await session.call_tool("get_capabilities", {})
                    if capabilities.isError:
                        raise AssertionError("get_capabilities failed during smoke test")
                    if not capabilities.structuredContent.get("app_version"):
                        raise AssertionError("get_capabilities did not report app_version")
            # The SDK emits request diagnostics on child stderr. Keep them
            # captured so the smoke script itself prints only its parent result.
        return tools


if __name__ == "__main__":
    discovered_tools = asyncio.run(run())
    print("MCP smoke passed: " + ", ".join(sorted(discovered_tools)))
