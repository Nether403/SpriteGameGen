"""Local stdio MCP adapter over framework-neutral sprite services."""
from __future__ import annotations

import sys
import traceback
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from typing import Annotated, Literal, TypeVar

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError

from app import deps
from app.config import get_settings
from app.models import (
    AnimateRequest,
    Direction,
    EnhancePromptRequest,
    ExportFormat,
    ExportOptions,
    FrameErrorCode,
    FrameStatus,
    ImageProviderName,
    MAX_EXPORT_COLS,
    MAX_EXPORT_PADDING,
    MAX_FRAME_ERROR_MESSAGE_LENGTH,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PROMPT_LENGTH,
    MAX_SHEET_BYTES,
    MAX_SHEET_DIMENSION,
    MAX_SHEET_PIXELS,
    Project,
    ProjectHealth,
    LoopMode,
    PaletteMode,
    RenderSettings,
    PromptSource,
    Style,
    ViewMode,
    directions_for,
)
from app.services import prompt_builder
from app.services.provider_selection import ProviderRequirements, ProviderUnavailableError
from app.services.image_provider import ProviderCapability
from app.recipes import RecipeV1, capture_project_recipe, validate_recipe_semantics
from app.services.sprite_runtime import SpriteRuntime
from app.services.sprite_service import (
    AnimationResult,
    GenerateSpriteInput,
    OperationControl,
    OperationProgress,
    OperationTimeoutError,
    SpriteServiceError,
)
from app.storage.project_store import ProjectBusyError, ProjectConflictError


try:
    APP_VERSION = version("sprite-game-asset-tool")
except PackageNotFoundError:  # pragma: no cover - editable installs cover tests/runtime
    APP_VERSION = "unknown"


class MCPProviderChoice(str, Enum):
    AUTO = "auto"
    AZURE = "azure"
    GEMINI = "gemini"
    COMFYUI = "comfyui"


class MCPOperationOutcome(str, Enum):
    COMPLETE = "complete"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class MCPFrame(BaseModel):
    index: int = Field(ge=0, description="Zero-based frame index.")
    status: FrameStatus = Field(description="Persisted frame generation status.")
    error_code: FrameErrorCode | None = Field(
        default=None, description="Stable failure category when status is failed."
    )
    error_message: str | None = Field(
        default=None,
        max_length=MAX_FRAME_ERROR_MESSAGE_LENGTH,
        description="Safe persisted frame failure message.",
    )
    path: str | None = Field(
        default=None, description="Absolute local asset path for a usable frame."
    )
    resource_uri: str | None = Field(
        default=None, description="MCP resource URI for a usable frame."
    )
    enabled: bool = True
    nudge_x: int = 0
    nudge_y: int = 0
    duration_ms: int | None = None
    seed: int | None = None


class MCPProject(BaseModel):
    id: str
    prompt: str
    enhanced_prompt: str | None
    prompt_source: PromptSource
    provider: ImageProviderName
    style: Style
    view_mode: ViewMode
    direction: Direction
    schema_version: int
    revision: int
    created_at: str
    updated_at: str
    frames: list[MCPFrame]
    action: str | None
    fps: int | None
    manifest_resource_uri: str
    active_clip_id: str | None = None
    clip_count: int = 0


class MCPProjectSummary(BaseModel):
    id: str
    prompt_preview: str | None
    provider: ImageProviderName | None
    revision: int | None
    style: Style | None
    view_mode: ViewMode | None
    direction: Direction | None
    thumbnail_path: str | None
    thumbnail_resource_uri: str | None
    manifest_resource_uri: str
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
    project: MCPProject
    sprite_path: str
    sprite_resource_uri: str
    health: ProjectHealth
    resume_available: bool


class MCPEnhanceResult(BaseModel):
    outcome: Literal[MCPOperationOutcome.COMPLETE] = MCPOperationOutcome.COMPLETE
    provider: Literal[ImageProviderName.GEMINI] = ImageProviderName.GEMINI
    original_prompt: str
    enhanced_prompt: str


class MCPGenerateResult(BaseModel):
    outcome: Literal[MCPOperationOutcome.COMPLETE] = MCPOperationOutcome.COMPLETE
    project: MCPProject
    sprite_path: str
    sprite_resource_uri: str


class MCPAnimationResult(BaseModel):
    outcome: MCPOperationOutcome
    project: MCPProject
    frame_paths: list[str | None]
    frame_resource_uris: list[str | None]


class MCPFrameResult(BaseModel):
    outcome: MCPOperationOutcome
    project: MCPProject
    frame: MCPFrame
    frame_path: str | None
    frame_resource_uri: str | None


class MCPExportResult(BaseModel):
    outcome: Literal[MCPOperationOutcome.COMPLETE] = MCPOperationOutcome.COMPLETE
    project_id: str
    revision: int
    provider: ImageProviderName
    sheet_path: str
    sheet_resource_uri: str
    atlas_path: str
    atlas_resource_uri: str
    frames_path: str | None = None
    frames_resource_uri: str | None = None


class MCPBundleResult(BaseModel):
    outcome: Literal[MCPOperationOutcome.COMPLETE] = MCPOperationOutcome.COMPLETE
    project_id: str
    bundle_path: str
    bundle_resource_uri: str


class MCPRecipeResult(BaseModel):
    valid: bool = True
    recipe: dict
    digest: str


class MCPProviderCapability(BaseModel):
    id: ImageProviderName
    label: str
    available: bool
    experimental: bool
    description: str
    unavailable_reason: str | None
    capabilities: list[ProviderCapability] = []


class MCPPreset(BaseModel):
    action: str
    min_frames: int
    max_frames: int
    default_frames: int


class MCPCameraDirections(BaseModel):
    view_mode: ViewMode
    directions: list[Direction]


class MCPLimits(BaseModel):
    max_prompt_characters: int
    max_upload_bytes: int
    max_image_dimension_pixels: int
    max_image_pixels: int
    max_export_padding_pixels: int
    max_export_columns: int
    max_sheet_dimension_pixels: int
    max_sheet_pixels: int
    max_sheet_bytes: int
    max_frame_error_message_characters: int


class MCPCapabilities(BaseModel):
    app_version: str
    providers: list[MCPProviderCapability]
    presets: list[MCPPreset]
    camera_directions: list[MCPCameraDirections]
    limits: MCPLimits


@dataclass(frozen=True)
class AppContext:
    runtime: SpriteRuntime


ProjectId = Annotated[
    str,
    Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Local sprite project identifier.",
    ),
]
Prompt = Annotated[
    str,
    Field(
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="Sprite description sent to the configured image provider.",
    ),
]

_T = TypeVar("_T")
_EXPECTED_ERRORS = (
    SpriteServiceError,
    ProviderUnavailableError,
    ProjectBusyError,
    ProjectConflictError,
    ValidationError,
    ValueError,
    FileNotFoundError,
)


def _default_runtime() -> SpriteRuntime:
    settings = get_settings()
    return SpriteRuntime(
        store=deps.get_store(),
        providers=deps.build_provider_registry(),
        max_upload_bytes=settings.max_upload_bytes,
        operation_timeout_seconds=settings.creative_operation_timeout_seconds,
        creative_operation_max_concurrency=(
            settings.creative_operation_max_concurrency
        ),
    )


def _runtime(ctx: Context) -> SpriteRuntime:
    return ctx.request_context.lifespan_context.runtime


def _resource_uri(project_id: str, filename: str) -> str:
    return f"sprite://projects/{project_id}/assets/{filename}"


def _manifest_uri(project_id: str) -> str:
    return f"sprite://projects/{project_id}/manifest"


def _asset_path(runtime: SpriteRuntime, project_id: str, filename: str) -> str:
    return str(runtime.store.asset_path(project_id, filename).resolve())


def _frame_filenames(project: Project) -> list[str | None]:
    return [
        None
        if frame.status is FrameStatus.FAILED
        else frame.rendered_filename
        for frame in project.frames
    ]


def _project_dto(
    runtime: SpriteRuntime,
    project: Project,
    filenames: list[str | None] | None = None,
) -> MCPProject:
    resolved_names = filenames if filenames is not None else _frame_filenames(project)
    frames = []
    for frame, filename in zip(project.frames, resolved_names):
        frames.append(
            MCPFrame(
                index=frame.index,
                status=frame.status,
                error_code=frame.error_code,
                error_message=frame.error_message,
                enabled=frame.enabled,
                nudge_x=frame.nudge_x,
                nudge_y=frame.nudge_y,
                duration_ms=frame.duration_ms,
                seed=frame.seed,
                path=(
                    _asset_path(runtime, project.id, filename) if filename else None
                ),
                resource_uri=(
                    _resource_uri(project.id, filename) if filename else None
                ),
            )
        )
    return MCPProject(
        id=project.id,
        prompt=project.prompt,
        enhanced_prompt=project.enhanced_prompt,
        prompt_source=project.prompt_source,
        provider=project.image_provider,
        style=project.style,
        view_mode=project.view_mode,
        direction=project.direction,
        schema_version=project.schema_version,
        revision=project.revision,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
        frames=frames,
        action=project.action,
        fps=project.fps,
        manifest_resource_uri=_manifest_uri(project.id),
        active_clip_id=project.active_clip_id,
        clip_count=len(project.clips),
    )


def _project_detail(runtime: SpriteRuntime, project_id: str) -> MCPProjectDetail:
    result = runtime.storage_service().get_project(project_id)
    return MCPProjectDetail(
        project=_project_dto(runtime, result.project, result.frame_filenames),
        sprite_path=_asset_path(runtime, project_id, result.sprite_filename),
        sprite_resource_uri=_resource_uri(project_id, result.sprite_filename),
        health=result.health,
        resume_available=result.resume_available,
    )


def _raise_tool_error(name: str, exc: Exception) -> None:
    if isinstance(exc, ToolError):
        raise exc
    if isinstance(exc, _EXPECTED_ERRORS):
        message = "project not found" if isinstance(exc, FileNotFoundError) else str(exc)
        raise ToolError(message) from exc
    request_id = uuid.uuid4().hex
    print(
        f"Unexpected MCP tool failure: tool={name} request_id={request_id}",
        file=sys.stderr,
    )
    traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
    raise ToolError(f"Unexpected server error (request ID: {request_id})") from None


def _safe_tool(name: str, operation: Callable[[], _T]) -> _T:
    try:
        return operation()
    except Exception as exc:  # noqa: BLE001 - shared transport sanitizer
        _raise_tool_error(name, exc)
        raise AssertionError("unreachable")


async def _run_creative_tool(
    name: str,
    ctx: Context,
    operation: Callable[[OperationControl], _T],
) -> _T:
    active = _runtime(ctx)
    timed_out = False

    def report(update: OperationProgress) -> None:
        try:
            anyio.from_thread.run(
                ctx.report_progress,
                update.progress,
                update.total,
                update.message,
            )
        except BaseException:
            # Progress is best effort. Cancellation is carried separately by the
            # thread-safe control signal and checked before every persistence edge.
            pass

    control = OperationControl(on_progress=report)
    completed = anyio.Event()
    results: list[_T] = []
    errors: list[BaseException] = []

    async def run_worker() -> None:
        try:
            results.append(
                await anyio.to_thread.run_sync(
                    active.run_creative,
                    lambda: operation(control),
                    control,
                    abandon_on_cancel=True,
                )
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            completed.set()

    async def timeout_watch() -> None:
        nonlocal timed_out
        await anyio.sleep(active.operation_timeout_seconds)
        if not completed.is_set():
            control.cancel()
            timed_out = True
            tasks.cancel_scope.cancel()

    try:
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(run_worker)
            tasks.start_soon(timeout_watch)
            await completed.wait()
            tasks.cancel_scope.cancel()

        if timed_out:
            raise OperationTimeoutError(
                f"Operation timed out after {active.operation_timeout_seconds:g}s; "
                "no project changes were committed. Try fewer frames or increase "
                "CREATIVE_OPERATION_TIMEOUT_SECONDS."
            )
        if errors:
            raise errors[0]
        return results[0]
    except anyio.get_cancelled_exc_class():
        control.cancel()
        raise
    except Exception as exc:  # noqa: BLE001 - shared transport sanitizer
        _raise_tool_error(name, exc)
        raise AssertionError("unreachable")


def _annotations(
    title: str,
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


def create_mcp_server(*, runtime: SpriteRuntime | None = None) -> FastMCP:
    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
        yield AppContext(runtime=runtime or _default_runtime())

    server = FastMCP(
        "Sprite Game Asset Tool",
        instructions=(
            "Generate, animate, resume, and export local sprite projects. "
            "Asset paths are absolute local paths; sprite:// resources provide "
            "protocol access to manifests and files."
        ),
        lifespan=lifespan,
    )

    @server.tool(
        annotations=_annotations(
            "Get Sprite Capabilities",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        )
    )
    def get_capabilities(ctx: Context) -> MCPCapabilities:
        """Report the exact local contract. No billing occurs and this does not overwrite data."""

        def operation() -> MCPCapabilities:
            active = _runtime(ctx)
            return MCPCapabilities(
                app_version=APP_VERSION,
                providers=[
                    MCPProviderCapability.model_validate(option.model_dump())
                    for option in active.providers.options()
                ],
                presets=[
                    MCPPreset(
                        action=item["action"],
                        min_frames=item["min_frames"],
                        max_frames=item["max_frames"],
                        default_frames=item["default_frames"],
                    )
                    for item in prompt_builder.list_presets()
                ],
                camera_directions=[
                    MCPCameraDirections(
                        view_mode=view_mode,
                        directions=list(directions_for(view_mode)),
                    )
                    for view_mode in ViewMode
                ],
                limits=MCPLimits(
                    max_prompt_characters=MAX_PROMPT_LENGTH,
                    max_upload_bytes=active.max_upload_bytes,
                    max_image_dimension_pixels=MAX_IMAGE_DIMENSION,
                    max_image_pixels=MAX_IMAGE_PIXELS,
                    max_export_padding_pixels=MAX_EXPORT_PADDING,
                    max_export_columns=MAX_EXPORT_COLS,
                    max_sheet_dimension_pixels=MAX_SHEET_DIMENSION,
                    max_sheet_pixels=MAX_SHEET_PIXELS,
                    max_sheet_bytes=MAX_SHEET_BYTES,
                    max_frame_error_message_characters=MAX_FRAME_ERROR_MESSAGE_LENGTH,
                ),
            )

        return _safe_tool("get_capabilities", operation)

    @server.tool(
        annotations=_annotations(
            "List Sprite Projects",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        )
    )
    def list_projects(ctx: Context) -> MCPProjectList:
        """List local projects. No billing occurs and this does not overwrite data."""

        def operation() -> MCPProjectList:
            active = _runtime(ctx)
            projects = []
            for item in active.storage_service().list_projects():
                record = active.store.get_project_record(item.id)
                project = record.project
                thumbnail_path = (
                    _asset_path(active, item.id, item.thumbnail_filename)
                    if item.thumbnail_filename
                    else None
                )
                projects.append(
                    MCPProjectSummary(
                        id=item.id,
                        prompt_preview=item.prompt_preview,
                        provider=project.image_provider if project else None,
                        revision=project.revision if project else None,
                        style=item.style,
                        view_mode=item.view_mode,
                        direction=item.direction,
                        thumbnail_path=thumbnail_path,
                        thumbnail_resource_uri=(
                            _resource_uri(item.id, item.thumbnail_filename)
                            if item.thumbnail_filename
                            else None
                        ),
                        manifest_resource_uri=_manifest_uri(item.id),
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

        return _safe_tool("list_projects", operation)

    @server.tool(
        annotations=_annotations(
            "Get Sprite Project",
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        )
    )
    def get_project(project_id: ProjectId, ctx: Context) -> MCPProjectDetail:
        """Read project state and assets. No billing occurs and this does not overwrite data."""

        return _safe_tool(
            "get_project", lambda: _project_detail(_runtime(ctx), project_id)
        )

    @server.tool(
        annotations=_annotations(
            "Enhance Sprite Prompt",
            read_only=True,
            destructive=False,
            idempotent=False,
            open_world=True,
        )
    )
    async def enhance_prompt(
        prompt: Prompt,
        style: Annotated[Style, Field(description="Requested sprite art style.")],
        ctx: Context,
        view_mode: Annotated[
            ViewMode, Field(description="Game camera perspective.")
        ] = ViewMode.SIDE_SCROLLER,
        direction: Annotated[
            Direction, Field(description="Subject facing and movement direction.")
        ] = Direction.LEFT,
    ) -> MCPEnhanceResult:
        """Call Gemini text enhancement, which may incur billing; it does not overwrite files."""

        def operation(control: OperationControl) -> MCPEnhanceResult:
            result = _runtime(ctx).prompt_service().enhance_prompt(
                EnhancePromptRequest(
                    prompt=prompt,
                    style=style,
                    view_mode=view_mode,
                    direction=direction,
                ),
                control=control,
            )
            return MCPEnhanceResult(
                original_prompt=result.original_prompt,
                enhanced_prompt=result.enhanced_prompt,
            )

        return await _run_creative_tool("enhance_prompt", ctx, operation)

    @server.tool(
        annotations=_annotations(
            "Generate Base Sprite",
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=True,
        )
    )
    async def generate_sprite(
        prompt: Prompt,
        style: Annotated[Style, Field(description="Requested sprite art style.")],
        ctx: Context,
        view_mode: Annotated[
            ViewMode, Field(description="Game camera perspective.")
        ] = ViewMode.SIDE_SCROLLER,
        direction: Annotated[
            Direction, Field(description="Subject facing and movement direction.")
        ] = Direction.LEFT,
        enhanced_prompt: Annotated[
            str | None,
            Field(
                max_length=MAX_PROMPT_LENGTH,
                description="Previously reviewed enhanced prompt to use verbatim.",
            ),
        ] = None,
        provider: Annotated[
            MCPProviderChoice,
            Field(description="Image provider selection: auto, azure, or gemini."),
        ] = MCPProviderChoice.AUTO,
        seed: Annotated[int | None, Field(ge=0, le=2**63 - 1)] = None,
    ) -> MCPGenerateResult:
        """Generate an image with provider billing and create a project; it does not overwrite existing files."""

        def operation(control: OperationControl) -> MCPGenerateResult:
            active = _runtime(ctx)
            required = {ProviderCapability.GENERATE}
            if seed is not None:
                required.add(ProviderCapability.SEED)
            result = active.service_for_provider(
                ImageProviderName(provider.value),
                ProviderRequirements(frozenset(required)),
            ).generate_sprite(
                GenerateSpriteInput(
                    prompt=prompt,
                    style=style,
                    view_mode=view_mode,
                    direction=direction,
                    enhanced_prompt=enhanced_prompt,
                    seed=seed,
                ),
                control=control,
            )
            return MCPGenerateResult(
                project=_project_dto(
                    active, result.project, [result.sprite_filename]
                ),
                sprite_path=_asset_path(
                    active, result.project_id, result.sprite_filename
                ),
                sprite_resource_uri=_resource_uri(
                    result.project_id, result.sprite_filename
                ),
            )

        return await _run_creative_tool("generate_sprite", ctx, operation)

    @server.tool(
        annotations=_annotations(
            "Animate Sprite Project",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        )
    )
    async def animate(
        project_id: ProjectId,
        action: Annotated[
            str,
            Field(min_length=1, description="Action preset name from get_capabilities."),
        ],
        ctx: Context,
        direction: Annotated[
            Direction, Field(description="Animation facing and movement direction.")
        ] = Direction.LEFT,
        frames: Annotated[
            int | None,
            Field(
                ge=2,
                le=8,
                description="Frame count within the selected preset's bounds.",
            ),
        ] = None,
        fps: Annotated[
            int,
            Field(ge=1, le=60, description="Persisted preview playback rate."),
        ] = 8,
        clip_id: Annotated[
            str | None,
            Field(pattern=r"^[A-Za-z0-9_-]+$", description="Clip to replace; omitted targets the active clip."),
        ] = None,
        clip_name: Annotated[
            str | None, Field(min_length=1, max_length=100)
        ] = None,
        seed: Annotated[int | None, Field(ge=0, le=2**63 - 1)] = None,
    ) -> MCPAnimationResult:
        """Run image edits with provider billing and overwrite animation frames and metadata."""

        def operation(control: OperationControl) -> MCPAnimationResult:
            active = _runtime(ctx)
            result = active.service_for_project(project_id, clip_id).animate(
                AnimateRequest(
                    project_id=project_id,
                    action=action,
                    direction=direction,
                    frames=frames,
                    fps=fps,
                    clip_id=clip_id,
                    clip_name=clip_name,
                    seed=seed,
                ),
                control=control,
            )
            return MCPAnimationResult(
                outcome=(
                    MCPOperationOutcome.PARTIAL_FAILURE
                    if any(frame.status is FrameStatus.FAILED for frame in result.frames)
                    else MCPOperationOutcome.COMPLETE
                ),
                project=_project_dto(active, result.project, result.frame_filenames),
                frame_paths=_frame_paths(active, result),
                frame_resource_uris=[
                    _resource_uri(project_id, filename) if filename else None
                    for filename in result.frame_filenames
                ],
            )

        return await _run_creative_tool("animate", ctx, operation)

    @server.tool(
        annotations=_annotations(
            "Regenerate Animation Frame",
            read_only=False,
            destructive=True,
            idempotent=False,
            open_world=True,
        )
    )
    async def regenerate_frame(
        project_id: ProjectId,
        index: Annotated[
            int, Field(ge=0, description="Zero-based frame index to replace.")
        ],
        ctx: Context,
        clip_id: Annotated[
            str | None, Field(pattern=r"^[A-Za-z0-9_-]+$")
        ] = None,
    ) -> MCPFrameResult:
        """Run one image edit with provider billing and overwrite the selected persisted frame."""

        def operation(control: OperationControl) -> MCPFrameResult:
            active = _runtime(ctx)
            result = active.service_for_project(project_id, clip_id).regenerate_frame(
                project_id, index, clip_id=clip_id, control=control
            )
            project = _project_dto(active, result.project)
            filename = result.filename
            frame = MCPFrame(
                index=result.frame.index,
                status=result.frame.status,
                error_code=result.frame.error_code,
                error_message=result.frame.error_message,
                enabled=result.frame.enabled,
                nudge_x=result.frame.nudge_x,
                nudge_y=result.frame.nudge_y,
                duration_ms=result.frame.duration_ms,
                seed=result.frame.seed,
                path=_asset_path(active, project_id, filename) if filename else None,
                resource_uri=_resource_uri(project_id, filename) if filename else None,
            )
            return MCPFrameResult(
                outcome=(
                    MCPOperationOutcome.COMPLETE
                    if result.frame.status is FrameStatus.OK
                    else MCPOperationOutcome.FAILED
                ),
                project=project,
                frame=frame,
                frame_path=frame.path,
                frame_resource_uri=frame.resource_uri,
            )

        return await _run_creative_tool("regenerate_frame", ctx, operation)

    @server.tool(
        annotations=_annotations(
            "Export Sprite Sheet",
            read_only=False,
            destructive=True,
            idempotent=True,
            open_world=False,
        )
    )
    async def export_sheet(
        project_id: ProjectId,
        ctx: Context,
        format: Annotated[
            ExportFormat, Field(description="Atlas metadata format.")
        ] = ExportFormat.JSON,
        padding: Annotated[
            int,
            Field(
                ge=0,
                le=MAX_EXPORT_PADDING,
                description="Transparent pixels around each packed frame.",
            ),
        ] = 0,
        cols: Annotated[
            int | None,
            Field(
                ge=1,
                le=MAX_EXPORT_COLS,
                description="Optional fixed sheet column count.",
            ),
        ] = None,
        clip_id: Annotated[
            str | None, Field(pattern=r"^[A-Za-z0-9_-]+$")
        ] = None,
    ) -> MCPExportResult:
        """Pack locally with no provider billing; overwrite matching sheet and atlas outputs."""

        def operation(control: OperationControl) -> MCPExportResult:
            active = _runtime(ctx)
            result = active.storage_service().export_sheet(
                project_id,
                ExportOptions(format=format, padding=padding, cols=cols, clip_id=clip_id),
                control=control,
            )
            project = active.store.read_manifest(project_id)
            return MCPExportResult(
                project_id=project_id,
                revision=project.revision,
                provider=project.image_provider,
                sheet_path=_asset_path(active, project_id, result.sheet_filename),
                sheet_resource_uri=_resource_uri(
                    project_id, result.sheet_filename
                ),
                atlas_path=_asset_path(active, project_id, result.atlas_filename),
                atlas_resource_uri=_resource_uri(
                    project_id, result.atlas_filename
                ),
                frames_path=_asset_path(active, project_id, result.frames_filename),
                frames_resource_uri=_resource_uri(project_id, result.frames_filename),
            )

        return await _run_creative_tool("export_sheet", ctx, operation)

    @server.tool(
        annotations=_annotations(
            "Set Render Settings", read_only=False, destructive=True,
            idempotent=True, open_world=False,
        )
    )
    def set_render_settings(
        project_id: ProjectId,
        ctx: Context,
        target_width: Annotated[int | None, Field(ge=1, le=1024)] = None,
        target_height: Annotated[int | None, Field(ge=1, le=1024)] = None,
        output_scale: Annotated[int, Field(ge=1, le=16)] = 1,
        color_limit: Annotated[int, Field(ge=1, le=256)] = 32,
        palette_mode: PaletteMode = PaletteMode.AUTO,
        preset_palette: str | None = None,
        custom_palette: list[str] | None = None,
    ) -> MCPProject:
        """Rerender and overwrite outputs locally; no provider call or billing occurs."""

        def operation() -> MCPProject:
            active = _runtime(ctx)
            project = active.storage_service().set_render_settings(
                project_id,
                RenderSettings(
                    target_width=target_width,
                    target_height=target_height,
                    output_scale=output_scale,
                    color_limit=color_limit,
                    palette_mode=palette_mode,
                    preset_palette=preset_palette,
                    custom_palette=custom_palette or [],
                ),
            )
            return _project_dto(active, project)

        return _safe_tool("set_render_settings", operation)

    @server.tool(
        annotations=_annotations(
            "Set Frame Adjustment", read_only=False, destructive=True,
            idempotent=True, open_world=False,
        )
    )
    def set_frame_adjustment(
        project_id: ProjectId,
        index: Annotated[int, Field(ge=0)],
        ctx: Context,
        clip_id: Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]+$")] = None,
        enabled: bool | None = None,
        nudge_x: Annotated[int | None, Field(ge=-4096, le=4096)] = None,
        nudge_y: Annotated[int | None, Field(ge=-4096, le=4096)] = None,
        horizontal_flip: bool | None = None,
        reset: bool = False,
    ) -> MCPFrameResult:
        """Curate and overwrite one frame locally; no provider call or billing occurs."""

        def operation() -> MCPFrameResult:
            active = _runtime(ctx)
            result = active.storage_service().set_frame_adjustment(
                project_id,
                index,
                clip_id=clip_id,
                enabled=enabled,
                nudge_x=nudge_x,
                nudge_y=nudge_y,
                horizontal_flip=horizontal_flip,
                reset=reset,
            )
            project = _project_dto(active, result.project)
            filename = result.filename
            frame = MCPFrame(
                index=result.frame.index,
                status=result.frame.status,
                error_code=result.frame.error_code,
                error_message=result.frame.error_message,
                enabled=result.frame.enabled,
                nudge_x=result.frame.nudge_x,
                nudge_y=result.frame.nudge_y,
                duration_ms=result.frame.duration_ms,
                seed=result.frame.seed,
                path=_asset_path(active, project_id, filename) if filename else None,
                resource_uri=_resource_uri(project_id, filename) if filename else None,
            )
            return MCPFrameResult(
                outcome=MCPOperationOutcome.COMPLETE,
                project=project,
                frame=frame,
                frame_path=frame.path,
                frame_resource_uri=frame.resource_uri,
            )

        return _safe_tool("set_frame_adjustment", operation)

    @server.tool(
        annotations=_annotations(
            "Update Animation Clip", read_only=False, destructive=True,
            idempotent=True, open_world=False,
        )
    )
    def update_clip(
        project_id: ProjectId,
        clip_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")],
        ctx: Context,
        name: Annotated[str | None, Field(min_length=1, max_length=100)] = None,
        fps: Annotated[int | None, Field(ge=1, le=60)] = None,
        enabled: bool | None = None,
        loop_mode: LoopMode | None = None,
    ) -> MCPProject:
        """Overwrite clip metadata locally; no provider billing occurs."""
        def operation() -> MCPProject:
            active = _runtime(ctx)
            result = active.storage_service().update_clip(
                project_id, clip_id, name=name, fps=fps,
                enabled=enabled, loop_mode=loop_mode,
            )
            return _project_dto(active, result.project)

        return _safe_tool("update_clip", operation)

    @server.tool(
        annotations=_annotations(
            "Delete Animation Clip", read_only=False, destructive=True,
            idempotent=False, open_world=False,
        )
    )
    def delete_clip(
        project_id: ProjectId,
        clip_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")],
        ctx: Context,
    ) -> MCPProject:
        """Delete a clip and overwrite project state locally; no provider billing occurs."""
        def operation() -> MCPProject:
            active = _runtime(ctx)
            result = active.storage_service().delete_clip(project_id, clip_id)
            return _project_dto(active, result.project)

        return _safe_tool("delete_clip", operation)

    @server.tool(
        annotations=_annotations(
            "Export Character Bundle", read_only=False, destructive=True,
            idempotent=True, open_world=False,
        )
    )
    def export_character_bundle(
        project_id: ProjectId,
        ctx: Context,
        scope: Literal["active", "one", "all_enabled"] = "active",
        clip_id: Annotated[str | None, Field(pattern=r"^[A-Za-z0-9_-]+$")] = None,
        engine_profile: Literal["godot4_animatedsprite2d"] | None = None,
    ) -> MCPBundleResult:
        """Export and overwrite a local bundle; no provider billing occurs."""
        def operation() -> MCPBundleResult:
            active = _runtime(ctx)
            result = active.storage_service().export_character_bundle(
                project_id, scope=scope, clip_id=clip_id,
                engine_profile=engine_profile,
            )
            return MCPBundleResult(
                project_id=project_id,
                bundle_path=_asset_path(active, project_id, result.bundle_filename),
                bundle_resource_uri=_resource_uri(project_id, result.bundle_filename),
            )

        return _safe_tool("export_character_bundle", operation)

    @server.tool(
        annotations=_annotations(
            "Validate Sprite Recipe", read_only=True, destructive=False,
            idempotent=True, open_world=False,
        )
    )
    def validate_recipe(recipe_json: str, ctx: Context) -> MCPRecipeResult:
        """Validate a recipe with no billing and without overwrite operations."""

        def operation() -> MCPRecipeResult:
            recipe = RecipeV1.model_validate_json(recipe_json)
            validate_recipe_semantics(recipe)
            return MCPRecipeResult(
                recipe=recipe.model_dump(mode="json"), digest=recipe.digest()
            )

        return _safe_tool("validate_recipe", operation)

    @server.tool(
        annotations=_annotations(
            "Get Project Recipe", read_only=True, destructive=False,
            idempotent=True, open_world=False,
        )
    )
    def get_project_recipe(project_id: ProjectId, ctx: Context) -> MCPRecipeResult:
        """Capture a recipe with no billing and without overwrite operations."""

        def operation() -> MCPRecipeResult:
            recipe = capture_project_recipe(_runtime(ctx).store.read_manifest(project_id))
            return MCPRecipeResult(
                recipe=recipe.model_dump(mode="json"), digest=recipe.digest()
            )

        return _safe_tool("get_project_recipe", operation)

    @server.resource(
        "sprite://projects/{project_id}/manifest",
        name="project_manifest",
        title="Sprite Project Manifest",
        description="Sanitized project state with absolute paths and resource URIs.",
        mime_type="application/json",
    )
    def project_manifest(project_id: str, ctx: Context) -> str:
        try:
            return _project_detail(_runtime(ctx), project_id).model_dump_json()
        except (SpriteServiceError, ValueError, FileNotFoundError) as exc:
            raise ResourceError("project resource not found or invalid") from exc

    @server.resource(
        "sprite://projects/{project_id}/assets/{filename}",
        name="project_asset",
        title="Sprite Project Asset",
        description="Binary project asset contained by the canonical project store.",
        mime_type="application/octet-stream",
    )
    def project_asset(project_id: str, filename: str, ctx: Context) -> bytes:
        try:
            path = _runtime(ctx).store.asset_path(project_id, filename)
            return path.read_bytes()
        except (ValueError, FileNotFoundError, OSError) as exc:
            raise ResourceError("asset resource not found or invalid") from exc

    return server


def _frame_paths(
    runtime: SpriteRuntime, result: AnimationResult
) -> list[str | None]:
    return [
        _asset_path(runtime, result.project_id, filename) if filename else None
        for filename in result.frame_filenames
    ]


mcp = create_mcp_server()


def main() -> None:
    """Start the local MCP server over stdio without writing to stdout."""

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
