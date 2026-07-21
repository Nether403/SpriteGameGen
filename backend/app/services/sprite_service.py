"""Framework-neutral application workflows for sprite projects.

HTTP and MCP adapters translate these typed results and errors into their own
transport conventions. This module intentionally imports neither framework.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import threading
from collections.abc import Callable

from PIL import Image
from pydantic import BaseModel

from app.models import (
    Direction,
    AnimateRequest,
    EnhancePromptRequest,
    EnhancePromptResult,
    Frame,
    FrameStatus,
    ImageProviderName,
    ExportOptions,
    Project,
    ProjectHealth,
    FrameErrorCode,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PROMPT_LENGTH,
    PromptSource,
    Style,
    ViewMode,
)
from app.pipeline import atlas, background, packer, pixelate, trim
from app.pipeline.background import BackgroundRemovalError
from app.pipeline.pixelate import PixelateError
from app.pipeline.trim import DegenerateBBoxError, EmptyImageError
from app.services import pose_reference, prompt_builder
from app.services.image_provider import (
    ImageProvider,
    ImageProviderError,
    ImageSafetyBlockedError,
    PromptEnhancer,
    provider_concurrency_slot,
)
from app.storage.project_store import (
    ProjectBusyError,
    ProjectConflictError,
    ProjectRecord,
    ProjectStore,
)


class SpriteServiceError(RuntimeError):
    """Base class for expected application-level failures."""


class ProjectNotFoundError(SpriteServiceError):
    pass


class ProjectUnavailableError(SpriteServiceError):
    pass


class ProjectConflictServiceError(SpriteServiceError):
    pass


class ValidationServiceError(SpriteServiceError):
    pass


class SafetyServiceError(SpriteServiceError):
    pass


class UpstreamServiceError(SpriteServiceError):
    pass


class OperationCancelledError(SpriteServiceError):
    """A cooperative cancellation stopped work before its persistence boundary."""


class OperationTimeoutError(SpriteServiceError):
    """A whole creative operation exceeded its configured deadline."""


@dataclass(frozen=True)
class OperationProgress:
    progress: float
    total: float
    message: str


class OperationControl:
    """Thread-safe cancellation and monotonic progress for synchronous workflows."""

    def __init__(
        self,
        *,
        cancelled: threading.Event | None = None,
        on_progress: Callable[[OperationProgress], None] | None = None,
    ) -> None:
        self._cancelled = cancelled or threading.Event()
        self._on_progress = on_progress
        self._progress = 0.0
        self._progress_lock = threading.Lock()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def cancel(self) -> None:
        self._cancelled.set()

    def check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise OperationCancelledError(
                "Operation cancelled; no project changes were committed."
            )

    def report(self, progress: float, message: str) -> None:
        value = min(1.0, max(0.0, float(progress)))
        with self._progress_lock:
            value = max(value, self._progress)
            self._progress = value
        if self._on_progress is not None:
            self._on_progress(
                OperationProgress(progress=value, total=1.0, message=message)
            )


class ProjectSummaryData(BaseModel):
    id: str
    prompt_preview: str | None = None
    style: Style | None = None
    view_mode: ViewMode | None = None
    direction: Direction | None = None
    thumbnail_filename: str | None = None
    action: str | None = None
    fps: int | None = None
    frame_count: int = 0
    ok_count: int = 0
    failed_count: int = 0
    created_at: datetime
    updated_at: datetime
    health: ProjectHealth
    resume_available: bool = False


class ProjectDetailData(BaseModel):
    project: Project
    sprite_filename: str
    frame_filenames: list[str | None]
    health: ProjectHealth = ProjectHealth.READY
    resume_available: bool = True


@dataclass(frozen=True)
class GenerateSpriteInput:
    prompt: str
    style: Style
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER
    direction: Direction = Direction.LEFT
    enhanced_prompt: str | None = None
    reference: Image.Image | None = None


class GenerateSpriteResult(BaseModel):
    project_id: str
    sprite_filename: str
    project: Project


class AnimationResult(BaseModel):
    project_id: str
    action: str
    fps: int
    view_mode: ViewMode
    direction: Direction
    frames: list[Frame]
    frame_filenames: list[str | None]
    project: Project


class FrameMutationResult(BaseModel):
    project_id: str
    frame: Frame
    filename: str | None
    project: Project


class ExportSheetResult(BaseModel):
    project_id: str
    sheet_filename: str
    atlas_filename: str


_FRAME_ERROR_MESSAGES: dict[FrameErrorCode, str] = {
    FrameErrorCode.PROVIDER: "Image provider failed to generate this frame.",
    FrameErrorCode.SAFETY: "Image provider blocked this frame for safety.",
    FrameErrorCode.BACKGROUND: "Background removal failed for this frame.",
    FrameErrorCode.EMPTY: "Frame contained no visible pixels after background removal.",
    FrameErrorCode.PIXELATE: "Pixel-art conversion failed for this frame.",
}


class SpriteService:
    def __init__(
        self,
        *,
        store: ProjectStore,
        image_provider: ImageProvider | None = None,
        prompt_enhancer: PromptEnhancer | None = None,
        provider_name: ImageProviderName = ImageProviderName.GEMINI,
        gemini=None,
        remover=None,
    ):
        self.store = store
        # ``gemini`` remains as a compatibility alias for existing adapters and
        # tests while callers migrate to the provider-neutral dependencies.
        self.image_provider = image_provider or gemini
        self.prompt_enhancer = prompt_enhancer or gemini
        self.provider_name = provider_name
        self.remover = remover

    def enhance_prompt(
        self,
        request: EnhancePromptRequest,
        *,
        control: OperationControl | None = None,
    ) -> EnhancePromptResult:
        operation = control or OperationControl()
        if self.prompt_enhancer is None:
            raise UpstreamServiceError("Prompt enhancer is not configured")
        operation.check_cancelled()
        operation.report(0.1, "Preparing prompt enhancement")
        try:
            with provider_concurrency_slot(
                self.prompt_enhancer,
                check_cancelled=operation.check_cancelled,
            ):
                enhanced = self.prompt_enhancer.enhance_prompt(
                    request.prompt,
                    request.style,
                    request.view_mode,
                    request.direction,
                )
        except ImageSafetyBlockedError as exc:
            raise SafetyServiceError(str(exc)) from exc
        except ImageProviderError as exc:
            raise UpstreamServiceError(str(exc)) from exc
        operation.check_cancelled()
        operation.report(0.9, "Prompt enhancement received")
        if len(enhanced) > MAX_PROMPT_LENGTH:
            raise UpstreamServiceError(
                "Prompt enhancer returned text above the maximum length"
            )
        operation.report(1.0, "Prompt enhancement complete")
        return EnhancePromptResult(
            original_prompt=request.prompt,
            enhanced_prompt=enhanced,
        )

    def generate_sprite(
        self,
        request: GenerateSpriteInput,
        *,
        control: OperationControl | None = None,
    ) -> GenerateSpriteResult:
        operation = control or OperationControl()
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        if not request.prompt.strip():
            raise ValidationServiceError("prompt must not be empty")
        if len(request.prompt) > MAX_PROMPT_LENGTH:
            raise ValidationServiceError(
                f"prompt must be at most {MAX_PROMPT_LENGTH} characters"
            )
        if (
            request.enhanced_prompt is not None
            and len(request.enhanced_prompt) > MAX_PROMPT_LENGTH
        ):
            raise ValidationServiceError(
                f"enhanced prompt must be at most {MAX_PROMPT_LENGTH} characters"
            )
        from app.models import validate_direction

        try:
            validate_direction(request.view_mode, request.direction)
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        accepted_prompt = (
            request.enhanced_prompt.strip() if request.enhanced_prompt else None
        )
        effective_prompt = accepted_prompt or request.prompt.strip()
        operation.check_cancelled()
        operation.report(0.05, "Preparing sprite generation")
        try:
            with provider_concurrency_slot(
                self.image_provider,
                check_cancelled=operation.check_cancelled,
            ):
                raw_image = self._validate_provider_image(
                    self.image_provider.generate(
                        effective_prompt,
                        request.style,
                        reference=request.reference,
                        view_mode=request.view_mode,
                        direction=request.direction,
                    )
                )
        except ImageSafetyBlockedError as exc:
            raise SafetyServiceError(str(exc)) from exc
        except ImageProviderError as exc:
            raise UpstreamServiceError(str(exc)) from exc

        operation.check_cancelled()
        operation.report(0.55, "Provider image received")
        try:
            cut = background.remove(raw_image, remover=self.remover)
            sprite = trim.autocrop(cut, padding=0)
            if request.style is Style.PIXEL:
                sprite = pixelate.quantize(sprite)
        except BackgroundRemovalError as exc:
            raise UpstreamServiceError(str(exc)) from exc
        except EmptyImageError as exc:
            raise UpstreamServiceError(
                "generated image was empty after background removal"
            ) from exc
        except PixelateError as exc:
            raise UpstreamServiceError(str(exc)) from exc

        operation.check_cancelled()
        operation.report(0.9, "Sprite processing complete")
        project_id = self.store.create()
        project = Project(
            id=project_id,
            prompt=request.prompt.strip(),
            enhanced_prompt=accepted_prompt,
            prompt_source=(
                PromptSource.ENHANCED if accepted_prompt else PromptSource.RAW
            ),
            image_provider=self.provider_name,
            style=request.style,
            view_mode=request.view_mode,
            direction=request.direction,
            frames=[Frame(index=0, url=None)],
        )
        try:
            operation.report(0.95, "Committing sprite project")
            operation.check_cancelled()
            self.store.commit_project(
                project_id,
                project,
                expected_revision=0,
                images={"sprite": sprite},
            )
        except Exception:
            self.store.delete_project(project_id)
            raise
        operation.report(1.0, "Sprite project complete")
        return GenerateSpriteResult(
            project_id=project_id,
            sprite_filename="sprite.png",
            project=project,
        )

    def animate(
        self,
        request: AnimateRequest,
        *,
        control: OperationControl | None = None,
    ) -> AnimationResult:
        operation = control or OperationControl()
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        operation.check_cancelled()
        operation.report(0.03, "Preparing animation")
        try:
            preset = prompt_builder.get_preset(request.action)
        except KeyError as exc:
            raise ValidationServiceError(
                f"unknown action: {request.action!r}"
            ) from exc
        project = self._read_project(request.project_id)
        original_revision = project.revision
        old_frame_names = {f"frame_{frame.index}" for frame in project.frames}
        from app.models import validate_direction

        try:
            validate_direction(project.view_mode, request.direction)
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        try:
            base = self.store.load_image(request.project_id, "sprite")
        except FileNotFoundError as exc:
            raise ProjectNotFoundError("project has no base sprite") from exc

        total = self._resolve_frame_count(preset, request.frames)
        def generate_frame(index: int) -> Image.Image:
            frame_prompt = prompt_builder.frame_prompt(
                request.action,
                index,
                total,
                project.view_mode,
                request.direction,
            )
            return self._edit_frame(
                base,
                frame_prompt,
                request.action,
                index,
                total,
                project.view_mode,
                request.direction,
                control=operation,
            )

        cut_by_index: dict[int, Image.Image] = {}
        failed: dict[int, tuple[FrameErrorCode, str]] = {}

        def mark_failed(index: int, exc: Exception) -> None:
            failed[index] = self._frame_failure(exc)

        def process_result(index: int, edited: Image.Image) -> None:
            try:
                cut = background.remove(edited, remover=self.remover)
                trim.content_bbox(cut)
                cut_by_index[index] = cut
            except (BackgroundRemovalError, EmptyImageError) as exc:
                mark_failed(index, exc)

        max_workers = max(1, int(getattr(self.image_provider, "max_concurrency", 1)))
        if max_workers == 1:
            for index in range(total):
                operation.check_cancelled()
                try:
                    process_result(index, generate_frame(index))
                except ImageSafetyBlockedError as exc:
                    mark_failed(index, exc)
                except ImageProviderError as exc:
                    mark_failed(index, exc)
                operation.check_cancelled()
                operation.report(
                    0.1 + 0.55 * ((index + 1) / total),
                    f"Generated animation frame {index + 1}/{total}",
                )
        else:
            # Only network-bound provider calls run concurrently. Background
            # removal and deterministic post-processing remain serial because
            # their native inference sessions are not guaranteed thread-safe.
            with ThreadPoolExecutor(max_workers=min(max_workers, total)) as executor:
                future_by_index = {
                    executor.submit(generate_frame, index): index
                    for index in range(total)
                }
                completed = 0
                for future in as_completed(future_by_index):
                    operation.check_cancelled()
                    index = future_by_index[future]
                    try:
                        process_result(index, future.result())
                    except ImageSafetyBlockedError as exc:
                        mark_failed(index, exc)
                    except ImageProviderError as exc:
                        mark_failed(index, exc)
                    completed += 1
                    operation.check_cancelled()
                    operation.report(
                        0.1 + 0.55 * (completed / total),
                        f"Generated animation frame {completed}/{total}",
                    )

        operation.check_cancelled()
        operation.report(0.7, "Processing animation frames")
        ok_indices = sorted(cut_by_index)
        aligned_by_index: dict[int, Image.Image] = {}
        if ok_indices:
            ordered = [cut_by_index[index] for index in ok_indices]
            try:
                box = trim.shared_bbox(ordered)
                aligned = trim.align_to_bbox(ordered, box, padding=0)
            except (EmptyImageError, DegenerateBBoxError) as exc:
                for index in ok_indices:
                    mark_failed(index, exc)
                aligned = []
            for index, image in zip(ok_indices, aligned):
                try:
                    if project.style is Style.PIXEL:
                        image = pixelate.quantize(image)
                    aligned_by_index[index] = image
                except PixelateError as exc:
                    mark_failed(index, exc)

        operation.check_cancelled()
        operation.report(0.9, "Animation frame processing complete")
        frames: list[Frame] = []
        filenames: list[str | None] = []
        images_to_save: dict[str, Image.Image] = {}
        for index in range(total):
            if index in aligned_by_index and index not in failed:
                name = f"frame_{index}"
                images_to_save[name] = aligned_by_index[index]
                frames.append(Frame(index=index, url=None, status=FrameStatus.OK))
                filenames.append(f"{name}.png")
            else:
                error_code, error_message = failed.get(
                    index,
                    (
                        FrameErrorCode.PROVIDER,
                        _FRAME_ERROR_MESSAGES[FrameErrorCode.PROVIDER],
                    ),
                )
                frames.append(
                    Frame(
                        index=index,
                        url=None,
                        status=FrameStatus.FAILED,
                        error_code=error_code,
                        error_message=error_message,
                    )
                )
                filenames.append(None)

        project.frames = frames
        project.action = request.action
        project.fps = request.fps
        project.direction = request.direction
        project.image_provider = self.provider_name
        operation.report(0.95, "Committing animation")
        operation.check_cancelled()
        self._commit_project(
            request.project_id,
            project,
            expected_revision=original_revision,
            images=images_to_save,
            delete_images=old_frame_names - set(images_to_save),
        )
        operation.report(1.0, "Animation complete")
        return AnimationResult(
            project_id=request.project_id,
            action=request.action,
            fps=request.fps,
            view_mode=project.view_mode,
            direction=project.direction,
            frames=frames,
            frame_filenames=filenames,
            project=project,
        )

    def regenerate_frame(
        self,
        project_id: str,
        index: int,
        *,
        control: OperationControl | None = None,
    ) -> FrameMutationResult:
        operation = control or OperationControl()
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        operation.check_cancelled()
        operation.report(0.05, "Preparing frame regeneration")
        project = self._read_project(project_id)
        original_revision = project.revision
        if project.action is None:
            raise ValidationServiceError("project has not been animated")
        total = len(project.frames)
        if not 0 <= index < total:
            raise ValidationServiceError(f"frame index {index} out of range")
        try:
            base = self.store.load_image(project_id, "sprite")
        except FileNotFoundError as exc:
            raise ProjectNotFoundError("project has no base sprite") from exc

        target_size: tuple[int, int] | None = None
        for frame in project.frames:
            if frame.index != index and frame.status is FrameStatus.OK:
                target_size = self.store.load_image(
                    project_id, f"frame_{frame.index}"
                ).size
                break
        if target_size is None:
            target_size = trim.autocrop(base, padding=0).size

        frame_prompt = prompt_builder.frame_prompt(
            project.action,
            index,
            total,
            project.view_mode,
            project.direction,
        )
        error_code: FrameErrorCode | None = None
        error_message: str | None = None
        try:
            edited = self._edit_frame(
                base,
                frame_prompt,
                project.action,
                index,
                total,
                project.view_mode,
                project.direction,
                control=operation,
            )
            operation.check_cancelled()
            cut = background.remove(edited, remover=self.remover)
            sprite = self._fit_to_size(cut, target_size)
            if project.style is Style.PIXEL:
                sprite = pixelate.quantize(sprite)
            status = FrameStatus.OK
        except (
            ImageProviderError,
            ImageSafetyBlockedError,
            BackgroundRemovalError,
            PixelateError,
            EmptyImageError,
            DegenerateBBoxError,
        ) as exc:
            status = FrameStatus.FAILED
            error_code, error_message = self._frame_failure(exc)

        operation.check_cancelled()
        operation.report(0.85, "Frame processing complete")
        filename = None
        images_to_save: dict[str, Image.Image] = {}
        delete_images: set[str] = set()
        if status is FrameStatus.OK:
            name = f"frame_{index}"
            images_to_save[name] = sprite
            filename = f"{name}.png"
        else:
            delete_images.add(f"frame_{index}")
        frame = Frame(
            index=index,
            url=None,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
        project.frames[index] = frame
        project.image_provider = self.provider_name
        operation.check_cancelled()
        operation.report(0.95, "Committing regenerated frame")
        operation.check_cancelled()
        self._commit_project(
            project_id,
            project,
            expected_revision=original_revision,
            images=images_to_save,
            delete_images=delete_images,
        )
        operation.report(1.0, "Frame regeneration complete")
        return FrameMutationResult(
            project_id=project_id,
            frame=frame,
            filename=filename,
            project=project,
        )

    def _edit_frame(
        self,
        base: Image.Image,
        frame_prompt: str,
        action: str,
        index: int,
        total: int,
        view_mode: ViewMode,
        direction: Direction,
        *,
        control: OperationControl | None = None,
    ) -> Image.Image:
        """Edit one frame, adding a structural guide where the model needs it."""
        guide = None
        if action == "walk" and view_mode is ViewMode.SIDE_SCROLLER:
            guide = pose_reference.walk_pose_reference(index, total, direction)
            frame_prompt += (
                " The first input image is the character identity and art-style "
                "reference. The second input image is a pose-only skeleton: copy "
                "its torso, hip, knee, ankle, foot, and arm positions, but never "
                "copy its stick-figure style, colors, background, or any guide lines."
            )
        operation = control or OperationControl()
        operation.check_cancelled()
        with provider_concurrency_slot(
            self.image_provider,
            check_cancelled=operation.check_cancelled,
        ):
            image = self.image_provider.edit(
                base, frame_prompt, pose_reference=guide
            )
        operation.check_cancelled()
        return self._validate_provider_image(image)

    def delete_frame(self, project_id: str, index: int) -> AnimationResult:
        project = self._read_project(project_id)
        original_revision = project.revision
        if project.action is None or project.fps is None:
            raise ValidationServiceError("project has not been animated")
        if not 0 <= index < len(project.frames):
            raise ValidationServiceError(f"frame index {index} out of range")

        survivors = [frame for frame in project.frames if frame.index != index]
        loaded: dict[int, Image.Image] = {}
        for new_index, frame in enumerate(survivors):
            if frame.status is FrameStatus.OK:
                loaded[new_index] = self.store.load_image(
                    project_id, f"frame_{frame.index}"
                )
        frames: list[Frame] = []
        filenames: list[str | None] = []
        images_to_save: dict[str, Image.Image] = {}
        for new_index, old_frame in enumerate(survivors):
            if new_index in loaded:
                name = f"frame_{new_index}"
                images_to_save[name] = loaded[new_index]
                frames.append(
                    Frame(index=new_index, url=None, status=FrameStatus.OK)
                )
                filenames.append(f"{name}.png")
            else:
                frames.append(
                    Frame(
                        index=new_index,
                        url=None,
                        status=FrameStatus.FAILED,
                        error_code=old_frame.error_code,
                        error_message=old_frame.error_message,
                    )
                )
                filenames.append(None)
        project.frames = frames
        old_frame_names = {f"frame_{frame.index}" for frame in [*survivors, project.frames]}
        # Include the deleted frame and any old high index that disappeared after reindexing.
        old_frame_names.update(f"frame_{old_index}" for old_index in range(len(survivors) + 1))
        self._commit_project(
            project_id,
            project,
            expected_revision=original_revision,
            images=images_to_save,
            delete_images=old_frame_names - set(images_to_save),
        )
        return AnimationResult(
            project_id=project_id,
            action=project.action,
            fps=project.fps,
            view_mode=project.view_mode,
            direction=project.direction,
            frames=frames,
            frame_filenames=filenames,
            project=project,
        )

    def export_sheet(
        self,
        project_id: str,
        options: ExportOptions,
        *,
        control: OperationControl | None = None,
    ) -> ExportSheetResult:
        operation = control or OperationControl()
        operation.check_cancelled()
        operation.report(0.05, "Preparing sprite-sheet export")
        project = self._read_project(project_id)
        original_revision = project.revision
        failed_count = sum(
            frame.status is FrameStatus.FAILED for frame in project.frames
        )
        if failed_count:
            plural = "frame" if failed_count == 1 else "frames"
            raise ProjectUnavailableError(
                f"Project has {failed_count} failed {plural}; "
                "regenerate or delete them before export."
            )
        ok_frames = [
            frame for frame in project.frames if frame.status is FrameStatus.OK
        ]
        if not ok_frames:
            raise ValidationServiceError("project has no usable frames")
        images = []
        ordered_frames = sorted(ok_frames, key=lambda item: item.index)
        for position, frame in enumerate(ordered_frames, start=1):
            operation.check_cancelled()
            name = (
                "sprite"
                if project.action is None
                else f"frame_{frame.index}"
            )
            images.append(self.store.load_image(project_id, name))
            operation.report(
                0.1 + 0.4 * (position / len(ordered_frames)),
                f"Loaded export frame {position}/{len(ordered_frames)}",
            )
        try:
            sheet, layout = packer.pack(
                images, cols=options.cols, padding=options.padding
            )
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        atlas_text = atlas.write_atlas(
            layout, sheet.size, fmt=options.format.value
        )
        operation.check_cancelled()
        operation.report(0.9, "Sprite sheet packed")
        atlas_filename = f"sprite.{options.format.value}"
        try:
            operation.report(0.95, "Committing export assets")
            operation.check_cancelled()
            self.store.commit_assets(
                project_id,
                expected_revision=original_revision,
                images={"sprite_sheet": sheet},
                texts={atlas_filename: atlas_text},
            )
        except (ProjectConflictError, ProjectBusyError) as exc:
            raise ProjectConflictServiceError(str(exc)) from exc
        operation.report(1.0, "Sprite-sheet export complete")
        return ExportSheetResult(
            project_id=project_id,
            sheet_filename="sprite_sheet.png",
            atlas_filename=atlas_filename,
        )

    def _read_project(self, project_id: str) -> Project:
        try:
            return self.store.read_manifest(project_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ProjectNotFoundError("project not found") from exc

    def _commit_project(
        self,
        project_id: str,
        project: Project,
        *,
        expected_revision: int,
        images: dict[str, Image.Image] | None = None,
        delete_images: set[str] | None = None,
    ) -> None:
        try:
            self.store.commit_project(
                project_id,
                project,
                expected_revision=expected_revision,
                images=images,
                delete_images=delete_images,
            )
        except (ProjectConflictError, ProjectBusyError) as exc:
            raise ProjectConflictServiceError(str(exc)) from exc

    @staticmethod
    def _resolve_frame_count(preset: dict, requested: int | None) -> int:
        if requested is None:
            return preset["default_frames"]
        if not preset["min_frames"] <= requested <= preset["max_frames"]:
            raise ValidationServiceError(
                f"frames for {preset['action']!r} must be between "
                f"{preset['min_frames']} and {preset['max_frames']}"
            )
        return requested

    @staticmethod
    def _validate_provider_image(image: Image.Image) -> Image.Image:
        try:
            width, height = image.size
        except (AttributeError, TypeError, ValueError) as exc:
            raise ImageProviderError("image provider returned an invalid image") from exc
        if (
            width < 1
            or height < 1
            or width > MAX_IMAGE_DIMENSION
            or height > MAX_IMAGE_DIMENSION
            or width * height > MAX_IMAGE_PIXELS
        ):
            raise ImageProviderError(
                "image provider returned image exceeds the decoded image limit"
            )
        try:
            image.load()
        except (OSError, SyntaxError, ValueError) as exc:
            raise ImageProviderError("image provider returned an invalid image") from exc
        return image

    @staticmethod
    def _frame_failure(exc: Exception) -> tuple[FrameErrorCode, str]:
        if isinstance(exc, ImageSafetyBlockedError):
            code = FrameErrorCode.SAFETY
        elif isinstance(exc, ImageProviderError):
            code = FrameErrorCode.PROVIDER
        elif isinstance(exc, BackgroundRemovalError):
            code = FrameErrorCode.BACKGROUND
        elif isinstance(exc, (EmptyImageError, DegenerateBBoxError)):
            code = FrameErrorCode.EMPTY
        elif isinstance(exc, PixelateError):
            code = FrameErrorCode.PIXELATE
        else:
            code = FrameErrorCode.PROVIDER
        return code, _FRAME_ERROR_MESSAGES[code]

    @staticmethod
    def _fit_to_size(image: Image.Image, size: tuple[int, int]) -> Image.Image:
        cropped = trim.autocrop(image, padding=0)
        width, height = cropped.size
        target_width, target_height = size
        if width > target_width or height > target_height:
            scale = min(target_width / width, target_height / height)
            cropped = cropped.resize(
                (max(1, int(width * scale)), max(1, int(height * scale))),
                Image.LANCZOS,
            )
            width, height = cropped.size
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.paste(
            cropped,
            ((target_width - width) // 2, (target_height - height) // 2),
        )
        return canvas

    def list_projects(self) -> list[ProjectSummaryData]:
        return [self._project_summary(record) for record in self.store.list_project_records()]

    def get_project(self, project_id: str) -> ProjectDetailData:
        try:
            record = self.store.get_project_record(project_id)
        except (FileNotFoundError, ValueError) as exc:
            raise ProjectNotFoundError("project not found") from exc
        if record.project is None or record.health is not ProjectHealth.READY:
            raise ProjectUnavailableError(
                f"project is {record.health.value} and cannot be resumed"
            )
        project = record.project
        return ProjectDetailData(
            project=project,
            sprite_filename="sprite.png",
            frame_filenames=[
                None
                if frame.status is FrameStatus.FAILED
                else (
                    "sprite.png"
                    if project.action is None
                    else f"frame_{frame.index}.png"
                )
                for frame in project.frames
            ],
            health=record.health,
            resume_available=True,
        )

    @staticmethod
    def _project_summary(record: ProjectRecord) -> ProjectSummaryData:
        project = record.project
        frames = project.frames if project is not None else []
        return ProjectSummaryData(
            id=record.id,
            prompt_preview=project.prompt[:120] if project is not None else None,
            style=project.style if project is not None else None,
            view_mode=project.view_mode if project is not None else None,
            direction=project.direction if project is not None else None,
            thumbnail_filename="sprite.png" if record.has_sprite else None,
            action=project.action if project is not None else None,
            fps=project.fps if project is not None else None,
            frame_count=len(frames),
            ok_count=sum(frame.status is FrameStatus.OK for frame in frames),
            failed_count=sum(frame.status is FrameStatus.FAILED for frame in frames),
            created_at=project.created_at if project is not None else record.updated_at,
            updated_at=record.updated_at,
            health=record.health,
            resume_available=record.health is ProjectHealth.READY,
        )
