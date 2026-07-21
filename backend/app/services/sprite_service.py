"""Framework-neutral application workflows for sprite projects.

HTTP and MCP adapters translate these typed results and errors into their own
transport conventions. This module intentionally imports neither framework.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

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
)
from app.storage.project_store import ProjectRecord, ProjectStore


class SpriteServiceError(RuntimeError):
    """Base class for expected application-level failures."""


class ProjectNotFoundError(SpriteServiceError):
    pass


class ProjectUnavailableError(SpriteServiceError):
    pass


class ValidationServiceError(SpriteServiceError):
    pass


class SafetyServiceError(SpriteServiceError):
    pass


class UpstreamServiceError(SpriteServiceError):
    pass


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

    def enhance_prompt(self, request: EnhancePromptRequest) -> EnhancePromptResult:
        if self.prompt_enhancer is None:
            raise UpstreamServiceError("Prompt enhancer is not configured")
        try:
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
        return EnhancePromptResult(
            original_prompt=request.prompt,
            enhanced_prompt=enhanced,
        )

    def generate_sprite(self, request: GenerateSpriteInput) -> GenerateSpriteResult:
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        if not request.prompt.strip():
            raise ValidationServiceError("prompt must not be empty")
        from app.models import validate_direction

        try:
            validate_direction(request.view_mode, request.direction)
        except ValueError as exc:
            raise ValidationServiceError(str(exc)) from exc
        accepted_prompt = (
            request.enhanced_prompt.strip() if request.enhanced_prompt else None
        )
        effective_prompt = accepted_prompt or request.prompt.strip()
        try:
            raw_image = self.image_provider.generate(
                effective_prompt,
                request.style,
                reference=request.reference,
                view_mode=request.view_mode,
                direction=request.direction,
            )
        except ImageSafetyBlockedError as exc:
            raise SafetyServiceError(str(exc)) from exc
        except ImageProviderError as exc:
            raise UpstreamServiceError(str(exc)) from exc

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

        project_id = self.store.create()
        self.store.save_image(project_id, "sprite", sprite)
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
        self.store.write_manifest(project_id, project)
        return GenerateSpriteResult(
            project_id=project_id,
            sprite_filename="sprite.png",
            project=project,
        )

    def animate(self, request: AnimateRequest) -> AnimationResult:
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        try:
            preset = prompt_builder.get_preset(request.action)
        except KeyError as exc:
            raise ValidationServiceError(
                f"unknown action: {request.action!r}"
            ) from exc
        project = self._read_project(request.project_id)
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
            )

        cut_by_index: dict[int, Image.Image] = {}
        failed: set[int] = set()

        def process_result(index: int, edited: Image.Image) -> None:
            try:
                cut_by_index[index] = background.remove(
                    edited, remover=self.remover
                )
            except BackgroundRemovalError:
                failed.add(index)

        max_workers = max(1, int(getattr(self.image_provider, "max_concurrency", 1)))
        if max_workers == 1:
            for index in range(total):
                try:
                    process_result(index, generate_frame(index))
                except (ImageProviderError, ImageSafetyBlockedError):
                    failed.add(index)
        else:
            # Only network-bound provider calls run concurrently. Background
            # removal and deterministic post-processing remain serial because
            # their native inference sessions are not guaranteed thread-safe.
            with ThreadPoolExecutor(max_workers=min(max_workers, total)) as executor:
                future_by_index = {
                    executor.submit(generate_frame, index): index
                    for index in range(total)
                }
                for future in as_completed(future_by_index):
                    index = future_by_index[future]
                    try:
                        process_result(index, future.result())
                    except (ImageProviderError, ImageSafetyBlockedError):
                        failed.add(index)

        ok_indices = sorted(cut_by_index)
        aligned_by_index: dict[int, Image.Image] = {}
        if ok_indices:
            ordered = [cut_by_index[index] for index in ok_indices]
            try:
                box = trim.shared_bbox(ordered)
                aligned = trim.align_to_bbox(ordered, box, padding=0)
            except (EmptyImageError, DegenerateBBoxError):
                failed.update(ok_indices)
                aligned = []
            for index, image in zip(ok_indices, aligned):
                try:
                    if project.style is Style.PIXEL:
                        image = pixelate.quantize(image)
                    aligned_by_index[index] = image
                except PixelateError:
                    failed.add(index)

        frames: list[Frame] = []
        filenames: list[str | None] = []
        for index in range(total):
            if index in aligned_by_index and index not in failed:
                name = f"frame_{index}"
                self.store.save_image(
                    request.project_id, name, aligned_by_index[index]
                )
                frames.append(Frame(index=index, url=None, status=FrameStatus.OK))
                filenames.append(f"{name}.png")
            else:
                frames.append(
                    Frame(index=index, url=None, status=FrameStatus.FAILED)
                )
                filenames.append(None)

        project.frames = frames
        project.action = request.action
        project.fps = request.fps
        project.direction = request.direction
        project.image_provider = self.provider_name
        self.store.write_manifest(request.project_id, project)
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

    def regenerate_frame(self, project_id: str, index: int) -> FrameMutationResult:
        if self.image_provider is None:
            raise UpstreamServiceError("Image provider is not configured")
        project = self._read_project(project_id)
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
        try:
            edited = self._edit_frame(
                base,
                frame_prompt,
                project.action,
                index,
                total,
                project.view_mode,
                project.direction,
            )
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
        ):
            status = FrameStatus.FAILED

        filename = None
        if status is FrameStatus.OK:
            name = f"frame_{index}"
            self.store.save_image(project_id, name, sprite)
            filename = f"{name}.png"
        frame = Frame(index=index, url=None, status=status)
        project.frames[index] = frame
        project.image_provider = self.provider_name
        self.store.write_manifest(project_id, project)
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
    ) -> Image.Image:
        """Edit one frame, adding a structural guide where the model needs it."""
        guide = None
        if action == "walk" and view_mode is ViewMode.SIDE_SCROLLER:
            guide = pose_reference.walk_pose_reference(index, total, direction)
            frame_prompt += (
                " The first input image is the character identity and art-style "
                "reference. The second input image is a pose-only skeleton: copy "
                "its torso, hip, knee, ankle, foot, and arm positions, but never "
                "copy its stick-figure style or colors."
            )
        return self.image_provider.edit(base, frame_prompt, pose_reference=guide)

    def delete_frame(self, project_id: str, index: int) -> AnimationResult:
        project = self._read_project(project_id)
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
        for frame in project.frames:
            self.store.delete_image(project_id, f"frame_{frame.index}")

        frames: list[Frame] = []
        filenames: list[str | None] = []
        for new_index, old_frame in enumerate(survivors):
            if new_index in loaded:
                name = f"frame_{new_index}"
                self.store.save_image(project_id, name, loaded[new_index])
                frames.append(
                    Frame(index=new_index, url=None, status=FrameStatus.OK)
                )
                filenames.append(f"{name}.png")
            else:
                frames.append(
                    Frame(index=new_index, url=None, status=FrameStatus.FAILED)
                )
                filenames.append(None)
        project.frames = frames
        self.store.write_manifest(project_id, project)
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
        self, project_id: str, options: ExportOptions
    ) -> ExportSheetResult:
        project = self._read_project(project_id)
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
        for frame in sorted(ok_frames, key=lambda item: item.index):
            name = (
                "sprite"
                if len(project.frames) == 1
                else f"frame_{frame.index}"
            )
            images.append(self.store.load_image(project_id, name))
        sheet, layout = packer.pack(
            images, cols=options.cols, padding=options.padding
        )
        atlas_text = atlas.write_atlas(
            layout, sheet.size, fmt=options.format.value
        )
        self.store.save_image(project_id, "sprite_sheet", sheet)
        atlas_filename = f"sprite.{options.format.value}"
        self.store.write_text(project_id, atlas_filename, atlas_text)
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

    @staticmethod
    def _resolve_frame_count(preset: dict, requested: int | None) -> int:
        if requested is None:
            return preset["default_frames"]
        return max(preset["min_frames"], min(preset["max_frames"], requested))

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
