"""In-process protocol tests for the local FastMCP adapter."""
from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image

from app.mcp_server import create_mcp_server
from app.models import Frame, Project, Style
from app.services.sprite_service import SpriteService
from app.storage.project_store import ProjectStore


def _service(tmp_path) -> tuple[SpriteService, str]:
    store = ProjectStore(tmp_path)
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (8, 8), "red"))
    store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a knight",
            style=Style.PIXEL,
            frames=[Frame(index=0, url=None)],
        ),
    )
    return SpriteService(store=store), pid


async def test_mcp_lists_and_reads_projects_with_local_paths(tmp_path):
    service, pid = _service(tmp_path)
    server = create_mcp_server(service=service)

    async with create_connected_server_and_client_session(server) as session:
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} >= {"list_projects", "get_project"}

        listed = await session.call_tool("list_projects", {})
        assert listed.isError is False
        assert listed.structuredContent["projects"][0]["id"] == pid
        assert listed.structuredContent["projects"][0]["thumbnail_path"].endswith(
            "sprite.png"
        )

        detail = await session.call_tool("get_project", {"project_id": pid})
        assert detail.isError is False
        assert detail.structuredContent["project"]["id"] == pid
        assert detail.structuredContent["sprite_path"].endswith("sprite.png")

        missing = await session.call_tool(
            "get_project", {"project_id": "missing"}
        )
        assert missing.isError is True
        assert "project not found" in missing.content[0].text


async def test_mcp_creative_workflow_uses_service_and_returns_local_paths(tmp_path):
    class Gemini:
        def _image(self):
            image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            image.paste(Image.new("RGBA", (8, 8), "red"), (8, 8))
            return image

        def enhance_prompt(self, prompt, style, view_mode, direction):
            return "a detailed silver knight"

        def generate(self, prompt, style, reference=None, *, view_mode, direction):
            return self._image()

        def edit(self, base, prompt):
            return self._image()

    service = SpriteService(
        store=ProjectStore(tmp_path), gemini=Gemini(), remover=lambda image: image
    )
    server = create_mcp_server(service=service)

    async with create_connected_server_and_client_session(server) as session:
        tools = await session.list_tools()
        assert {tool.name for tool in tools.tools} >= {
            "enhance_prompt",
            "generate_sprite",
            "animate",
            "regenerate_frame",
            "export_sheet",
        }

        preview = await session.call_tool(
            "enhance_prompt", {"prompt": "a knight", "style": "pixel"}
        )
        assert preview.structuredContent["enhanced_prompt"].startswith("a detailed")

        generated = await session.call_tool(
            "generate_sprite",
            {
                "prompt": "a knight",
                "enhanced_prompt": preview.structuredContent["enhanced_prompt"],
                "style": "hires",
                "view_mode": "top_down_2_5d",
                "direction": "down_right",
            },
        )
        pid = generated.structuredContent["project"]["id"]
        assert generated.structuredContent["sprite_path"].endswith("sprite.png")

        animated = await session.call_tool(
            "animate",
            {
                "project_id": pid,
                "action": "walk",
                "frames": 4,
                "direction": "up_left",
            },
        )
        assert len(animated.structuredContent["frame_paths"]) == 4

        repaired = await session.call_tool(
            "regenerate_frame", {"project_id": pid, "index": 1}
        )
        assert repaired.structuredContent["frame_path"].endswith("frame_1.png")

        exported = await session.call_tool(
            "export_sheet", {"project_id": pid, "format": "json"}
        )
        assert exported.structuredContent["sheet_path"].endswith(
            "sprite_sheet.png"
        )
        assert exported.structuredContent["atlas_path"].endswith("sprite.json")
