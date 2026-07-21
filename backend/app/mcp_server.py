"""Local stdio MCP adapter over the framework-neutral SpriteService."""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from app.config import get_settings
from app.models import (
    Direction,
    AnimateRequest,
    EnhancePromptRequest,
    EnhancePromptResult,
    ExportFormat,
    ExportOptions,
    Frame,
    Project,
    ProjectHealth,
    Style,
    ViewMode,
)
from app.services.gemini_client import build_default_client
from app.services.sprite_service import (
    AnimationResult,
    GenerateSpriteInput,
    SpriteService,
    SpriteServiceError,
)
from app.storage.project_store import ProjectStore


class MCPProjectSummary(BaseModel):
    id: str
    prompt_preview: str | None
    style: Style | None
    view_mode: ViewMode | None
    direction: Direction | None
    thumbnail_path: str | None
    action: str | None
    fps: int | None
    frame_count: int
    ok_count: int
    failed_count: int
    health: ProjectHealth
    resume_available: bool
    created_at: str
    updated_at: str


class MCPProjectList(BaseModel):
    projects: list[MCPProjectSummary]


class MCPProjectDetail(BaseModel):
    project: Project
    sprite_path: str
    frame_paths: list[str | None]
    health: ProjectHealth
    resume_available: bool


class MCPGenerateResult(BaseModel):
    project: Project
    sprite_path: str


class MCPAnimationResult(BaseModel):
    project: Project
    frame_paths: list[str | None]


class MCPFrameResult(BaseModel):
    project: Project
    frame: Frame
    frame_path: str | None


class MCPExportResult(BaseModel):
    project_id: str
    sheet_path: str
    atlas_path: str


@dataclass(frozen=True)
class AppContext:
    service: SpriteService


def _default_service() -> SpriteService:
    settings = get_settings()
    return SpriteService(
        store=ProjectStore(settings.projects_dir),
        gemini=build_default_client(),
    )


def _asset_path(service: SpriteService, project_id: str, filename: str) -> str:
    return str(service.store.asset_path(project_id, filename).resolve())


def _service(ctx: Context) -> SpriteService:
    return ctx.request_context.lifespan_context.service


def _frame_paths(
    active: SpriteService, result: AnimationResult
) -> list[str | None]:
    return [
        _asset_path(active, result.project_id, filename) if filename else None
        for filename in result.frame_filenames
    ]


def create_mcp_server(*, service: SpriteService | None = None) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
        yield AppContext(service=service or _default_service())

    server = FastMCP(
        "Sprite Game Asset Tool",
        instructions=(
            "Generate, animate, resume, and export local sprite projects. "
            "All returned asset paths are local filesystem paths."
        ),
        lifespan=lifespan,
    )

    @server.tool()
    def list_projects(ctx: Context) -> MCPProjectList:
        """List local sprite projects, including resume health and frame counts."""

        active = _service(ctx)
        projects = []
        for item in active.list_projects():
            thumbnail_path = None
            if item.thumbnail_filename:
                thumbnail_path = _asset_path(
                    active, item.id, item.thumbnail_filename
                )
            projects.append(
                MCPProjectSummary(
                    id=item.id,
                    prompt_preview=item.prompt_preview,
                    style=item.style,
                    view_mode=item.view_mode,
                    direction=item.direction,
                    thumbnail_path=thumbnail_path,
                    action=item.action,
                    fps=item.fps,
                    frame_count=item.frame_count,
                    ok_count=item.ok_count,
                    failed_count=item.failed_count,
                    health=item.health,
                    resume_available=item.resume_available,
                    created_at=item.created_at.isoformat(),
                    updated_at=item.updated_at.isoformat(),
                )
            )
        return MCPProjectList(projects=projects)

    @server.tool()
    def get_project(project_id: str, ctx: Context) -> MCPProjectDetail:
        """Get complete resumable project state and absolute local asset paths."""

        active = _service(ctx)
        try:
            result = active.get_project(project_id)
        except SpriteServiceError as exc:
            raise ToolError(str(exc)) from exc
        return MCPProjectDetail(
            project=result.project,
            sprite_path=_asset_path(
                active, project_id, result.sprite_filename
            ),
            frame_paths=[
                _asset_path(active, project_id, filename) if filename else None
                for filename in result.frame_filenames
            ],
            health=result.health,
            resume_available=result.resume_available,
        )

    @server.tool()
    def enhance_prompt(
        prompt: str,
        style: Style,
        ctx: Context,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
    ) -> EnhancePromptResult:
        """Preview a richer sprite-friendly prompt without creating a project."""

        try:
            return _service(ctx).enhance_prompt(
                EnhancePromptRequest(
                    prompt=prompt,
                    style=style,
                    view_mode=view_mode,
                    direction=direction,
                )
            )
        except (SpriteServiceError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    def generate_sprite(
        prompt: str,
        style: Style,
        ctx: Context,
        view_mode: ViewMode = ViewMode.SIDE_SCROLLER,
        direction: Direction = Direction.LEFT,
        enhanced_prompt: str | None = None,
    ) -> MCPGenerateResult:
        """Generate and persist a base sprite; reference images are not supported."""

        active = _service(ctx)
        try:
            result = active.generate_sprite(
                GenerateSpriteInput(
                    prompt=prompt,
                    style=style,
                    view_mode=view_mode,
                    direction=direction,
                    enhanced_prompt=enhanced_prompt,
                )
            )
        except SpriteServiceError as exc:
            raise ToolError(str(exc)) from exc
        return MCPGenerateResult(
            project=result.project,
            sprite_path=_asset_path(
                active, result.project_id, result.sprite_filename
            ),
        )

    @server.tool()
    def animate(
        project_id: str,
        action: str,
        ctx: Context,
        direction: Direction = Direction.LEFT,
        frames: int | None = None,
        fps: int = 8,
    ) -> MCPAnimationResult:
        """Generate a base-anchored animation with partial-failure frame status."""

        active = _service(ctx)
        try:
            result = active.animate(
                AnimateRequest(
                    project_id=project_id,
                    action=action,
                    direction=direction,
                    frames=frames,
                    fps=fps,
                )
            )
        except (SpriteServiceError, ValueError) as exc:
            raise ToolError(str(exc)) from exc
        return MCPAnimationResult(
            project=result.project,
            frame_paths=_frame_paths(active, result),
        )

    @server.tool()
    def regenerate_frame(
        project_id: str, index: int, ctx: Context
    ) -> MCPFrameResult:
        """Regenerate one animation frame using the project's stored context."""

        active = _service(ctx)
        try:
            result = active.regenerate_frame(project_id, index)
        except SpriteServiceError as exc:
            raise ToolError(str(exc)) from exc
        return MCPFrameResult(
            project=result.project,
            frame=result.frame,
            frame_path=(
                _asset_path(active, project_id, result.filename)
                if result.filename
                else None
            ),
        )

    @server.tool()
    def export_sheet(
        project_id: str,
        ctx: Context,
        format: ExportFormat = ExportFormat.JSON,
        padding: int = 0,
        cols: int | None = None,
    ) -> MCPExportResult:
        """Pack usable frames into a sprite sheet and JSON or XML atlas."""

        active = _service(ctx)
        try:
            result = active.export_sheet(
                project_id,
                ExportOptions(format=format, padding=padding, cols=cols),
            )
        except (SpriteServiceError, ValueError) as exc:
            raise ToolError(str(exc)) from exc
        return MCPExportResult(
            project_id=project_id,
            sheet_path=_asset_path(active, project_id, result.sheet_filename),
            atlas_path=_asset_path(active, project_id, result.atlas_filename),
        )

    return server


mcp = create_mcp_server()


def main() -> None:
    """Start the local MCP server over stdio."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
