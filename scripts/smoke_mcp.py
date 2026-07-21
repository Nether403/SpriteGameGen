"""List MCP tools in-process without credentials or Gemini calls."""
from __future__ import annotations

import asyncio
import os
import sys
from tempfile import TemporaryDirectory

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run() -> None:
    with TemporaryDirectory(prefix="sprite-mcp-smoke-") as project_dir:
        server_code = (
            "import os; "
            "from app.mcp_server import create_mcp_server; "
            "from app.services.sprite_service import SpriteService; "
            "from app.storage.project_store import ProjectStore; "
            "create_mcp_server(service=SpriteService("
            "store=ProjectStore(os.environ['SPRITE_MCP_SMOKE_DIR'])))"
            ".run(transport='stdio')"
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", server_code],
            env={**os.environ, "SPRITE_MCP_SMOKE_DIR": project_dir},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                print("MCP tools:", ", ".join(tool.name for tool in result.tools))


if __name__ == "__main__":
    asyncio.run(run())
