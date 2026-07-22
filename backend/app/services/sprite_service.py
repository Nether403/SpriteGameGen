"""Framework-neutral application workflows for sprite projects.

HTTP and MCP adapters translate these typed results and errors into their own
transport conventions. This module intentionally imports neither framework.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from io import BytesIO
import hashlib
import json
import threading
import uuid
import zipfile
from collections.abc import Callable

from PIL import Image
from pydantic import BaseModel

from app.models import (
    Direction,
    AnimationClip,
    ActionSnapshot,
    AnimateRequest,
    EnhancePromptRequest,
    EnhancePromptResult,
    Frame,
    FrameStatus,
    ImageProviderName,
    ExportOptions,
    LoopMode,
    PaletteMode,
    Project,
    ProjectHealth,
    FrameErrorCode,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_SHEET_BYTES,
    MAX_SHEET_PIXELS,
    MAX_PROMPT_LENGTH,
    PromptSource,
    Style,
    ViewMode,
    RenderSettings,
)
from app.pipeline import atlas, background, frame_render, packer, pixelate, trim
from app.pipeline.background import BackgroundRemovalError
from app.pipeline.pixelate import PixelateError
from app.pipeline.trim import DegenerateBBoxError, EmptyImageError
from app.character_bundle import build_character_bundle, CharacterBundleError
from app.services import pose_reference, prompt_builder
from app.services.image_provider import (
    ImageProvider,
    ImageProviderError,
    ImageProviderTimeoutError,
    ImageSafetyBlockedError,
    PromptEnhancer,
    ProviderCapability,
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
    clip_count: int = 0
    active_clip_id: str | None = None


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
    seed: int | None = None


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
    clip_id: str


class FrameMutationResult(BaseModel):
    project_id: str
    frame: Frame
    filename: str | None
    project: Project


class ExportSheetResult(BaseModel):
    project_id: str
    sheet_filename: str
    atlas_filename: str
    frames_filename: str


class ClipMutationResult(BaseModel):
    project_id: str
    clip: AnimationClip | None
    project: Project


class CharacterBundleResult(BaseModel):
    project_id: str
    bundle_filename: str


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
        required = {ProviderCapability.GENERATE}
        if request.reference is not None:
            required.add(ProviderCapability.IDENTITY_REFERENCE)
        if request.seed is not None:
            required.add(ProviderCapability.SEED)
        self._require_provider_capabilities(required)
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
                kwargs = {
                    "reference": request.reference,
                    "view_mode": request.view_mode,
                    "direction": request.direction,
                }
                if request.seed is not None:
                    kwargs["seed"] = request.seed
                if getattr(self.image_provider, "supports_cancel_check", False):
                    kwargs["cancel_check"] = operation.check_cancelled
                raw_image = self._validate_provider_image(
                    self.image_provider.generate(effective_prompt, request.style, **kwargs)
                )
        except ImageSafetyBlockedError as exc:
            raise SafetyServiceError(str(exc)) from exc
        except ImageProviderError as exc:
            raise UpstreamServiceError(str(exc)) from exc

        operation.check_cancelled()
        operation.report(0.55, "Provider image received")
        try:
            cut = background.remove(raw_image, remover=self.remover)
            source = trim.autocrop(cut, padding=0)
            sprite = self._render_source(source, RenderSettings(), request.style)
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
            schema_version=2,
        )
        try:
            operation.report(0.95, "Committing sprite project")
            operation.check_cancelled()
            self.store.commit_project(
                project_id,
                project,
                expected_revision=0,
                images={"source_sprite": source, "sprite": sprite},
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
        required = {
            ProviderCapability.EDIT,
            ProviderCapability.IDENTITY_REFERENCE,
        }
        if request.action == "walk":
            required.add(ProviderCapability.POSE_REFERENCE)
        if request.seed is not None:
            required.add(ProviderCapability.SEED)
        self._require_provider_capabilities(required)
        operation.check_cancelled()
        operation.report(0.03, "Preparing animation")
        try:
            preset = prompt_builder.get_preset(request.action)
        except KeyError as exc:
            if not request.custom_motion:
                raise ValidationServiceError(
                    f"unknown action: {request.action!r}"
                ) from exc
            requested_frames = request.frames or 4
            preset = {
                "action": request.action,
                "pose": request.custom_motion,
                "min_frames": 2,
                "max_frames": 8,
                "default_frames": requested_frames,
                "phases": [],
            }
        project = self._read_project(request.project_id)
        original_revision = project.revision
        clip_id = request.clip_id or project.active_clip_id or uuid.uuid4().hex[:16]
        old_clip = project.clips.get(clip_id)
        old_frame_names = {
            filename.removesuffix(".png")
            for frame in (old_clip.frames if old_clip else [])
            for filename in (frame.source_filename, frame.rendered_filename)
            if filename and filename.endswith(".png")
        }
        from app.models import validate_direction

        try:
            validate_direction(project.view_mode, request.direction)
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        try:
            try:
                base = self.store.load_image(request.project_id, "source_sprite")
            except FileNotFoundError:
                base = self.store.load_image(request.project_id, "sprite")
        except FileNotFoundError as exc:
            raise ProjectNotFoundError("project has no base sprite") from exc

        total = self._resolve_frame_count(preset, request.frames)
        def generate_frame(index: int) -> Image.Image:
            frame_prompt = self._request_frame_prompt(
                request, preset, index, total, project.view_mode
            )
            return self._edit_frame(
                base,
                frame_prompt,
                request.action,
                index,
                total,
                project.view_mode,
                request.direction,
                guide_specs=preset.get("guides", []),
                seed=(request.seed + index if request.seed is not None else None),
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
                except ImageProviderTimeoutError:
                    raise
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
                    except ImageProviderTimeoutError:
                        raise
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
        source_by_index: dict[int, Image.Image] = {}
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
                    source_by_index[index] = image
                except (PixelateError, ValueError) as exc:
                    mark_failed(index, exc)

        shared_palette: list[str] | None = None
        if (
            project.style is Style.PIXEL
            and project.render_settings.palette_mode is PaletteMode.SHARED_AUTO
            and source_by_index
        ):
            shared_palette = pixelate.build_shared_palette(
                [source_by_index[index] for index in sorted(source_by_index)],
                project.render_settings.color_limit,
            )

        operation.check_cancelled()
        operation.report(0.9, "Animation frame processing complete")
        frames: list[Frame] = []
        filenames: list[str | None] = []
        images_to_save: dict[str, Image.Image] = {}
        for index in range(total):
            if index in source_by_index and index not in failed:
                source_name = f"source_clip_{clip_id}_{index:04d}"
                rendered_name = f"clip_{clip_id}_{index:04d}"
                images_to_save[source_name] = source_by_index[index]
                try:
                    images_to_save[rendered_name] = self._render_source(
                        source_by_index[index],
                        project.render_settings,
                        project.style,
                        palette=shared_palette,
                    )
                    frames.append(
                        Frame(
                            index=index,
                            source_filename=f"{source_name}.png",
                            rendered_filename=f"{rendered_name}.png",
                            duration_ms=max(1, round(1000 / request.fps)),
                            seed=(request.seed + index if request.seed is not None else None),
                            status=FrameStatus.OK,
                        )
                    )
                    filenames.append(f"{rendered_name}.png")
                except PixelateError as exc:
                    error_code, error_message = self._frame_failure(exc)
                    frames.append(
                        Frame(
                            index=index,
                            source_filename=f"{source_name}.png",
                            duration_ms=max(1, round(1000 / request.fps)),
                            seed=(request.seed + index if request.seed is not None else None),
                            status=FrameStatus.FAILED,
                            error_code=error_code,
                            error_message=error_message,
                        )
                    )
                    filenames.append(None)
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

        snapshot = self._action_snapshot(request.action, preset, request)
        digest = hashlib.sha256(
            snapshot.model_dump_json(exclude_none=True).encode("utf-8")
        ).hexdigest()
        now = datetime.now(timezone.utc)
        project.clips[clip_id] = AnimationClip(
            id=clip_id,
            name=request.clip_name or (old_clip.name if old_clip else request.action.title()),
            action=request.action,
            action_ref=(
                f"custom:{request.action}"
                if request.custom_motion
                else str(preset.get("_reference", f"builtin:{request.action}"))
            ),
            action_version=str(preset.get("_version", "1")),
            action_digest=(digest if request.custom_motion else str(preset.get("_digest", digest))),
            action_snapshot=snapshot,
            direction=request.direction,
            fps=request.fps,
            loop_mode=request.loop_mode,
            loop_start=0,
            loop_end=len(frames) - 1 if frames else None,
            enabled=old_clip.enabled if old_clip else True,
            horizontal_flip=old_clip.horizontal_flip if old_clip else False,
            frames=frames,
            image_provider=self.provider_name,
            created_at=old_clip.created_at if old_clip else now,
            updated_at=now,
        )
        project.active_clip_id = clip_id
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
            direction=request.direction,
            frames=frames,
            frame_filenames=filenames,
            project=project,
            clip_id=clip_id,
        )

    def regenerate_frame(
        self,
        project_id: str,
        index: int,
        *,
        clip_id: str | None = None,
        control: OperationControl | None = None,
    ) -> FrameMutationResult:
        operation = control or OperationControl()
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        operation.check_cancelled()
        operation.report(0.05, "Preparing frame regeneration")
        project = self._read_project(project_id)
        original_revision = project.revision
        clip = self._get_clip(project, clip_id)
        if clip is None:
            raise ValidationServiceError("project has not been animated")
        total = len(clip.frames)
        if not 0 <= index < total:
            raise ValidationServiceError(f"frame index {index} out of range")
        try:
            try:
                base = self.store.load_image(project_id, "source_sprite")
            except FileNotFoundError:
                base = self.store.load_image(project_id, "sprite")
        except FileNotFoundError as exc:
            raise ProjectNotFoundError("project has no base sprite") from exc

        target_size: tuple[int, int] | None = None
        for frame in clip.frames:
            if frame.index != index and frame.status is FrameStatus.OK:
                if frame.source_filename:
                    target_size = self.store.load_image(
                        project_id, frame.source_filename.removesuffix(".png")
                    ).size
                    break
                if frame.rendered_filename:
                    target_size = self.store.load_image(
                        project_id, frame.rendered_filename.removesuffix(".png")
                    ).size
                break
        if target_size is None:
            target_size = trim.autocrop(base, padding=0).size

        frame_prompt = self._clip_frame_prompt(
            clip, index, total, project.view_mode
        )
        error_code: FrameErrorCode | None = None
        error_message: str | None = None
        try:
            edited = self._edit_frame(
                base,
                frame_prompt,
                clip.action,
                index,
                total,
                project.view_mode,
                clip.direction,
                guide_specs=(clip.action_snapshot.guides if clip.action_snapshot else []),
                control=operation,
            )
            operation.check_cancelled()
            cut = background.remove(edited, remover=self.remover)
            source = self._fit_to_size(cut, target_size)
            previous = clip.frames[index]
            sprite = self._render_adjusted_source(
                source,
                project,
                clip,
                previous,
            )
            status = FrameStatus.OK
        except ImageProviderTimeoutError:
            raise
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
            source_name = f"source_clip_{clip.id}_{index:04d}"
            name = f"clip_{clip.id}_{index:04d}"
            images_to_save[source_name] = source
            images_to_save[name] = sprite
            filename = f"{name}.png"
        else:
            previous = clip.frames[index]
            if (
                previous.rendered_filename
                and previous.rendered_filename != previous.source_filename
            ):
                delete_images.add(previous.rendered_filename.removesuffix(".png"))
        previous = clip.frames[index]
        frame = Frame(
            index=index,
            url=None,
            source_filename=(
                f"source_clip_{clip.id}_{index:04d}.png"
                if status is FrameStatus.OK
                else previous.source_filename
            ),
            rendered_filename=filename,
            enabled=previous.enabled,
            nudge_x=previous.nudge_x,
            nudge_y=previous.nudge_y,
            duration_ms=previous.duration_ms,
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
        clip.frames[index] = frame
        clip.updated_at = datetime.now(timezone.utc)
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
        guide_specs: list[dict] | None = None,
        seed: int | None = None,
        control: OperationControl | None = None,
    ) -> Image.Image:
        """Edit one frame, adding a structural guide where the model needs it."""
        guide = None
        guides = guide_specs or []
        if guides and view_mode is ViewMode.SIDE_SCROLLER:
            selected = guides[min(len(guides) - 1, (index * len(guides)) // total)]
            guide = pose_reference.declarative_pose_reference(
                [tuple(point) for point in selected.get("points", [])], direction
            )
        elif action == "walk" and view_mode is ViewMode.SIDE_SCROLLER:
            guide = pose_reference.walk_pose_reference(index, total, direction)
        if guide is not None:
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
            kwargs = {"pose_reference": guide}
            if seed is not None:
                kwargs["seed"] = seed
            if getattr(self.image_provider, "supports_cancel_check", False):
                kwargs["cancel_check"] = operation.check_cancelled
            image = self.image_provider.edit(base, frame_prompt, **kwargs)
        operation.check_cancelled()
        return self._validate_provider_image(image)

    def delete_frame(
        self, project_id: str, index: int, *, clip_id: str | None = None
    ) -> AnimationResult:
        """Compatibility operation: curate a frame without deleting its source."""

        project = self._read_project(project_id)
        original_revision = project.revision
        clip = self._get_clip(project, clip_id)
        if clip is None:
            raise ValidationServiceError("project has not been animated")
        if not 0 <= index < len(clip.frames):
            raise ValidationServiceError(f"frame index {index} out of range")
        clip.frames[index].enabled = False
        clip.updated_at = datetime.now(timezone.utc)
        self._commit_project(
            project_id,
            project,
            expected_revision=original_revision,
        )
        return AnimationResult(
            project_id=project_id,
            action=clip.action,
            fps=clip.fps,
            view_mode=project.view_mode,
            direction=clip.direction,
            frames=clip.frames,
            frame_filenames=[
                frame.rendered_filename if frame.status is FrameStatus.OK else None
                for frame in clip.frames
            ],
            project=project,
            clip_id=clip.id,
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
        clip = self._get_clip(project, options.clip_id)
        selected_frames = clip.frames if clip else []
        failed_count = sum(
            frame.enabled and frame.status is FrameStatus.FAILED
            for frame in selected_frames
        )
        if failed_count:
            plural = "frame" if failed_count == 1 else "frames"
            raise ProjectUnavailableError(
                f"Project has {failed_count} failed {plural}; "
                "regenerate or disable them before export."
            )
        ok_frames = [
            frame
            for frame in selected_frames
            if frame.enabled and frame.status is FrameStatus.OK
        ]
        if clip is None:
            ok_frames = [
                Frame(
                    index=0,
                    source_filename=project.source_sprite_filename,
                    rendered_filename=project.sprite_filename,
                )
            ]
        if not ok_frames:
            raise ValidationServiceError("project has no usable frames")
        images = []
        ordered_frames = sorted(ok_frames, key=lambda item: item.index)
        for position, frame in enumerate(ordered_frames, start=1):
            operation.check_cancelled()
            name = (frame.rendered_filename or project.sprite_filename).removesuffix(".png")
            images.append(self.store.load_image(project_id, name))
            operation.report(
                0.1 + 0.4 * (position / len(ordered_frames)),
                f"Loaded export frame {position}/{len(ordered_frames)}",
            )
        try:
            sheet, layout = packer.pack(
                images,
                cols=options.cols,
                padding=options.padding,
                indices=[frame.index for frame in ordered_frames],
            )
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        prefix = f"clip_{clip.id}" if clip and options.clip_id else "sprite"
        sheet_name = f"{prefix}_sheet"
        atlas_text = atlas.write_atlas(
            layout,
            sheet.size,
            fmt=options.format.value,
            sheet_filename=f"{sheet_name}.png",
        )
        operation.check_cancelled()
        operation.report(0.9, "Sprite sheet packed")
        atlas_filename = f"{prefix}.{options.format.value}"
        frames_filename = f"{prefix}_frames.zip"
        frame_zip = self._frames_zip(project_id, ordered_frames)
        try:
            operation.report(0.95, "Committing export assets")
            operation.check_cancelled()
            self.store.commit_assets(
                project_id,
                expected_revision=original_revision,
                images={sheet_name: sheet},
                texts={atlas_filename: atlas_text},
                blobs={frames_filename: frame_zip},
            )
        except (ProjectConflictError, ProjectBusyError) as exc:
            raise ProjectConflictServiceError(str(exc)) from exc
        operation.report(1.0, "Sprite-sheet export complete")
        return ExportSheetResult(
            project_id=project_id,
            sheet_filename=f"{sheet_name}.png",
            atlas_filename=atlas_filename,
            frames_filename=frames_filename,
        )

    def set_render_settings(
        self, project_id: str, settings: RenderSettings
    ) -> Project:
        """Rerender every retained source without making a provider call."""

        project = self._read_project(project_id)
        revision = project.revision
        aggregate_pixels = 0
        candidate_files = [project.source_sprite_filename]
        candidate_files.extend(
            frame.source_filename or frame.rendered_filename
            for clip in project.clips.values()
            for frame in clip.frames
            if frame.source_filename or frame.rendered_filename
        )
        for filename in candidate_files:
            try:
                path = self.store.asset_path(project_id, filename)
            except FileNotFoundError:
                if filename == project.source_sprite_filename:
                    path = self.store.asset_path(project_id, project.sprite_filename)
                else:
                    raise
            with Image.open(path) as probe:
                width = settings.target_width or probe.width
                height = settings.target_height or probe.height
            aggregate_pixels += (
                width * settings.output_scale * height * settings.output_scale
            )
            if aggregate_pixels > MAX_SHEET_PIXELS * 2:
                raise ValidationServiceError(
                    "render settings exceed the aggregate project render limit"
                )
        images: dict[str, Image.Image] = {}
        try:
            base_source = self.store.load_image(project_id, "source_sprite")
        except FileNotFoundError:
            base_source = self.store.load_image(project_id, "sprite")
            images["source_sprite"] = base_source
        project.render_settings = settings
        images["sprite"] = self._render_source(base_source, settings, project.style)

        for clip in project.clips.values():
            sources: dict[int, Image.Image] = {}
            for frame in clip.frames:
                if not frame.source_filename and not frame.rendered_filename:
                    continue
                filename = frame.source_filename or frame.rendered_filename
                assert filename is not None
                source = self.store.load_image(
                    project_id, filename.removesuffix(".png")
                )
                sources[frame.index] = source
            shared = None
            if (
                project.style is Style.PIXEL
                and settings.palette_mode is PaletteMode.SHARED_AUTO
                and sources
            ):
                shared = pixelate.build_shared_palette(
                    [sources[index] for index in sorted(sources)], settings.color_limit
                )
            for frame in clip.frames:
                source = sources.get(frame.index)
                if source is None:
                    continue
                source_name = f"source_clip_{clip.id}_{frame.index:04d}"
                render_name = f"clip_{clip.id}_{frame.index:04d}"
                images[source_name] = source
                images[render_name] = self._render_adjusted_source(
                    source, project, clip, frame, palette=shared
                )
                frame.source_filename = f"{source_name}.png"
                frame.rendered_filename = f"{render_name}.png"
        self._commit_project(
            project_id, project, expected_revision=revision, images=images
        )
        return project

    def export_character_bundle(
        self,
        project_id: str,
        *,
        scope: str = "active",
        clip_id: str | None = None,
        engine_profile: str | None = None,
    ) -> CharacterBundleResult:
        project = self._read_project(project_id)
        try:
            payload = build_character_bundle(
                self.store,
                project,
                scope=scope,
                clip_id=clip_id,
                engine_profile=engine_profile,
            )
        except CharacterBundleError as exc:
            raise ProjectUnavailableError(str(exc)) from exc
        suffix = engine_profile or "generic"
        filename = f"character_bundle_{suffix}.zip"
        self.store.commit_assets(
            project_id,
            expected_revision=project.revision,
            blobs={filename: payload},
        )
        return CharacterBundleResult(
            project_id=project_id, bundle_filename=filename
        )

    def set_frame_adjustment(
        self,
        project_id: str,
        index: int,
        *,
        clip_id: str | None = None,
        enabled: bool | None = None,
        nudge_x: int | None = None,
        nudge_y: int | None = None,
        horizontal_flip: bool | None = None,
        reset: bool = False,
    ) -> FrameMutationResult:
        """Apply deterministic curation from the retained frame source."""

        project = self._read_project(project_id)
        revision = project.revision
        clip = self._require_clip(project, clip_id)
        if not 0 <= index < len(clip.frames):
            raise ValidationServiceError(f"frame index {index} out of range")
        frame = clip.frames[index]
        if reset:
            frame.nudge_x = 0
            frame.nudge_y = 0
            frame.enabled = True
            clip.horizontal_flip = False
        if enabled is not None:
            frame.enabled = enabled
        if nudge_x is not None:
            frame.nudge_x = nudge_x
        if nudge_y is not None:
            frame.nudge_y = nudge_y
        if horizontal_flip is not None:
            clip.horizontal_flip = horizontal_flip

        images: dict[str, Image.Image] = {}
        filename = frame.rendered_filename
        if frame.source_filename:
            source = self.store.load_image(
                project_id, frame.source_filename.removesuffix(".png")
            )
            rendered_name = f"clip_{clip.id}_{index:04d}"
            images[rendered_name] = self._render_adjusted_source(
                source, project, clip, frame
            )
            frame.rendered_filename = f"{rendered_name}.png"
            filename = frame.rendered_filename
        clip.updated_at = datetime.now(timezone.utc)
        self._commit_project(
            project_id, project, expected_revision=revision, images=images
        )
        return FrameMutationResult(
            project_id=project_id,
            frame=frame,
            filename=filename,
            project=project,
        )

    def select_clip(self, project_id: str, clip_id: str) -> ClipMutationResult:
        project = self._read_project(project_id)
        revision = project.revision
        clip = self._require_clip(project, clip_id)
        project.active_clip_id = clip.id
        self._commit_project(project_id, project, expected_revision=revision)
        return ClipMutationResult(project_id=project_id, clip=clip, project=project)

    def update_clip(
        self,
        project_id: str,
        clip_id: str,
        *,
        name: str | None = None,
        fps: int | None = None,
        loop_mode: LoopMode | None = None,
        loop_start: int | None = None,
        loop_end: int | None = None,
        enabled: bool | None = None,
    ) -> ClipMutationResult:
        project = self._read_project(project_id)
        revision = project.revision
        clip = self._require_clip(project, clip_id)
        updates = {
            "name": name,
            "fps": fps,
            "loop_mode": loop_mode,
            "loop_start": loop_start,
            "loop_end": loop_end,
            "enabled": enabled,
        }
        payload = clip.model_dump()
        payload.update({key: value for key, value in updates.items() if value is not None})
        payload["updated_at"] = datetime.now(timezone.utc)
        updated = AnimationClip.model_validate(payload)
        project.clips[clip_id] = updated
        self._commit_project(project_id, project, expected_revision=revision)
        return ClipMutationResult(project_id=project_id, clip=updated, project=project)

    def delete_clip(self, project_id: str, clip_id: str) -> ClipMutationResult:
        project = self._read_project(project_id)
        revision = project.revision
        clip = self._require_clip(project, clip_id)
        delete_files = {
            filename
            for frame in clip.frames
            for filename in (frame.source_filename, frame.rendered_filename)
            if filename
        }
        del project.clips[clip_id]
        if project.active_clip_id == clip_id:
            project.active_clip_id = next(iter(project.clips), None)
        self._commit_project(
            project_id,
            project,
            expected_revision=revision,
            delete_files=delete_files,
        )
        return ClipMutationResult(project_id=project_id, clip=None, project=project)

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
        delete_files: set[str] | None = None,
    ) -> None:
        try:
            self.store.commit_project(
                project_id,
                project,
                expected_revision=expected_revision,
                images=images,
                delete_images=delete_images,
                delete_files=delete_files,
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
    def _get_clip(project: Project, clip_id: str | None) -> AnimationClip | None:
        selected = clip_id or project.active_clip_id
        if selected is None:
            return None
        clip = project.clips.get(selected)
        if clip is None:
            raise ValidationServiceError(f"unknown clip: {selected!r}")
        return clip

    @classmethod
    def _require_clip(cls, project: Project, clip_id: str | None) -> AnimationClip:
        clip = cls._get_clip(project, clip_id)
        if clip is None:
            raise ValidationServiceError("project has no animation clips")
        return clip

    @staticmethod
    def _action_snapshot(
        action: str, preset: dict, request: AnimateRequest
    ) -> ActionSnapshot:
        motion = request.custom_motion or str(preset.get("pose") or action)
        phases = [str(value) for value in preset.get("phases", [])]
        return ActionSnapshot(
            id=action,
            motion=motion,
            min_frames=int(preset["min_frames"]),
            max_frames=int(preset["max_frames"]),
            default_frames=int(preset["default_frames"]),
            fps=request.fps,
            loop_mode=request.loop_mode,
            phases=phases,
            first_pose=request.first_pose,
            last_pose=request.last_pose,
            change_directive=preset.get("change_directive"),
            guides=preset.get("guides", []),
        )

    @staticmethod
    def _request_frame_prompt(
        request: AnimateRequest,
        preset: dict,
        index: int,
        total: int,
        view_mode: ViewMode,
    ) -> str:
        if not request.custom_motion:
            return prompt_builder.frame_prompt(
                request.action, index, total, view_mode, request.direction
            )
        pose = request.custom_motion
        if index == 0 and request.first_pose:
            pose = request.first_pose
        elif index == total - 1 and request.last_pose:
            pose = request.last_pose
        return (
            f"Animate the character performing {request.custom_motion}. "
            f"Frame {index + 1} of {total}: {pose}. "
            f"Keep identity, proportions, camera, and transparent background unchanged."
        )

    @staticmethod
    def _clip_frame_prompt(
        clip: AnimationClip, index: int, total: int, view_mode: ViewMode
    ) -> str:
        snapshot = clip.action_snapshot
        if snapshot is None:
            try:
                return prompt_builder.frame_prompt(
                    clip.action, index, total, view_mode, clip.direction
                )
            except KeyError as exc:
                raise ValidationServiceError("clip has no saved action snapshot") from exc
        pose = snapshot.motion
        if snapshot.phases:
            phase_index = min(
                len(snapshot.phases) - 1,
                (index * len(snapshot.phases)) // max(1, total),
            )
            pose = snapshot.phases[phase_index]
        if index == 0 and snapshot.first_pose:
            pose = snapshot.first_pose
        elif index == total - 1 and snapshot.last_pose:
            pose = snapshot.last_pose
        return (
            f"Animate the character performing {snapshot.motion}. "
            f"Frame {index + 1} of {total}: {pose}. "
            f"{snapshot.change_directive or ''} "
            "Keep identity, proportions, camera, and transparent background unchanged. "
            + prompt_builder.camera_direction_prompt(view_mode, clip.direction)
        )

    @staticmethod
    def _render_source(
        source: Image.Image,
        settings: RenderSettings,
        style: Style,
        *,
        palette: list[str] | None = None,
    ) -> Image.Image:
        target = (
            (settings.target_width, settings.target_height)
            if settings.target_width and settings.target_height
            else None
        )
        logical_width, logical_height = target or source.size
        final_width = logical_width * settings.output_scale
        final_height = logical_height * settings.output_scale
        if (
            final_width > MAX_IMAGE_DIMENSION
            or final_height > MAX_IMAGE_DIMENSION
            or final_width * final_height > MAX_IMAGE_PIXELS
        ):
            raise PixelateError("rendered image exceeds resource limits")
        if style is Style.PIXEL:
            selected_palette = palette
            if settings.palette_mode is PaletteMode.PRESET:
                selected_palette = list(
                    pixelate.PRESET_PALETTES[settings.preset_palette or ""]
                )
            elif settings.palette_mode is PaletteMode.CUSTOM:
                selected_palette = settings.custom_palette
            if (
                target is None
                and settings.output_scale == 1
                and settings.color_limit == 32
                and selected_palette is None
            ):
                return pixelate.quantize(source)
            return pixelate.quantize(
                source,
                colors=settings.color_limit,
                target_size=target,
                output_scale=settings.output_scale,
                palette=selected_palette,
            )
        image = source.convert("RGBA")
        if target:
            image = image.resize(target, Image.Resampling.LANCZOS)
        if settings.output_scale > 1:
            image = image.resize(
                (
                    image.width * settings.output_scale,
                    image.height * settings.output_scale,
                ),
                Image.Resampling.NEAREST,
            )
        return image

    @classmethod
    def _render_adjusted_source(
        cls,
        source: Image.Image,
        project: Project,
        clip: AnimationClip,
        frame: Frame,
        *,
        palette: list[str] | None = None,
    ) -> Image.Image:
        composed = frame_render.compose(
            source,
            source.size,
            horizontal_flip=clip.horizontal_flip,
            nudge_x=frame.nudge_x,
            nudge_y=frame.nudge_y,
        )
        return cls._render_source(
            composed, project.render_settings, project.style, palette=palette
        )

    def _frames_zip(self, project_id: str, frames: list[Frame]) -> bytes:
        output = BytesIO()
        with zipfile.ZipFile(
            output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for frame in frames:
                if not frame.rendered_filename:
                    continue
                payload = self.store.asset_path(
                    project_id, frame.rendered_filename
                ).read_bytes()
                info = zipfile.ZipInfo(f"{frame.index:04d}.png", (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, payload, compresslevel=9)
        data = output.getvalue()
        if len(data) > MAX_SHEET_BYTES:
            raise ValidationServiceError("frame archive exceeds the export byte limit")
        return data

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

    def _require_provider_capabilities(
        self, required: set[ProviderCapability]
    ) -> None:
        capabilities = getattr(
            self.image_provider, "capabilities", frozenset(ProviderCapability)
        )
        missing = required - set(capabilities)
        if missing:
            names = ", ".join(sorted(value.value for value in missing))
            raise ValidationServiceError(
                f"selected provider lacks required capabilities: {names}"
            )

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
            sprite_filename=project.sprite_filename,
            frame_filenames=[
                None
                if frame.status is FrameStatus.FAILED
                else frame.rendered_filename
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
            clip_count=len(project.clips) if project is not None else 0,
            active_clip_id=project.active_clip_id if project is not None else None,
        )
