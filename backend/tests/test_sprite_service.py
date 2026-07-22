"""Framework-neutral SpriteService behavior."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

from PIL import Image
import pytest

from app.models import (
    Direction,
    AnimateRequest,
    EnhancePromptRequest,
    Frame,
    FrameErrorCode,
    FrameStatus,
    ExportOptions,
    Project,
    ProjectHealth,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PROMPT_LENGTH,
    Style,
    ViewMode,
)
from app.services.sprite_service import (
    GenerateSpriteInput,
    OperationCancelledError,
    OperationControl,
    ProjectConflictServiceError,
    ProjectNotFoundError,
    ProjectUnavailableError,
    SpriteService,
    UpstreamServiceError,
    ValidationServiceError,
)
from app.storage.project_store import ProjectStore


def _project(store: ProjectStore, *, action: str | None = None) -> str:
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (8, 8), "red"))
    frames = [Frame(index=0, url="stale-web-url")]
    if action:
        store.save_image(pid, "frame_0", Image.new("RGBA", (8, 8), "red"))
        frames = [
            Frame(index=0, url="stale-web-url"),
            Frame(index=1, url=None, status=FrameStatus.FAILED),
        ]
    store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a knight",
            style=Style.PIXEL,
            frames=frames,
            action=action,
            fps=8 if action else None,
        ),
    )
    return pid


def test_project_queries_return_transport_neutral_asset_names(tmp_path):
    store = ProjectStore(tmp_path)
    pid = _project(store, action="walk")
    service = SpriteService(store=store)

    summary = service.list_projects()[0]
    assert summary.id == pid
    assert summary.thumbnail_filename == "sprite.png"
    assert summary.health is ProjectHealth.READY

    detail = service.get_project(pid)
    assert detail.project.id == pid
    assert detail.sprite_filename == "sprite.png"
    assert detail.frame_filenames == ["frame_0.png", None]
    assert "stale-web-url" not in detail.frame_filenames


def test_project_queries_raise_typed_errors(tmp_path):
    store = ProjectStore(tmp_path)
    service = SpriteService(store=store)

    with pytest.raises(ProjectNotFoundError):
        service.get_project("missing")

    incomplete = store.create()
    with pytest.raises(ProjectUnavailableError, match="incomplete"):
        service.get_project(incomplete)


def test_enhance_prompt_is_a_framework_neutral_preview(tmp_path):
    class Gemini:
        def enhance_prompt(self, prompt, style, view_mode, direction):
            assert (style, view_mode, direction) == (
                Style.PIXEL,
                ViewMode.TOP_DOWN_2_5D,
                Direction.UP_LEFT,
            )
            return "a silver-armored knight"

    service = SpriteService(store=ProjectStore(tmp_path), gemini=Gemini())
    result = service.enhance_prompt(
        EnhancePromptRequest(
            prompt="a knight",
            style=Style.PIXEL,
            view_mode=ViewMode.TOP_DOWN_2_5D,
            direction=Direction.UP_LEFT,
        )
    )

    assert result.original_prompt == "a knight"
    assert result.enhanced_prompt == "a silver-armored knight"
    assert list(tmp_path.iterdir()) == []


def test_enhance_prompt_rejects_overlong_provider_output(tmp_path):
    class Gemini:
        def enhance_prompt(self, *args):
            return "x" * (MAX_PROMPT_LENGTH + 1)

    with pytest.raises(UpstreamServiceError, match="maximum length"):
        SpriteService(store=ProjectStore(tmp_path), gemini=Gemini()).enhance_prompt(
            EnhancePromptRequest(prompt="a knight", style=Style.PIXEL)
        )


def test_generate_sprite_processes_and_persists_accepted_prompt(tmp_path):
    class Gemini:
        def __init__(self):
            self.prompt = None

        def generate(self, prompt, style, reference=None, *, view_mode, direction):
            self.prompt = prompt
            image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            image.paste(Image.new("RGBA", (8, 8), "red"), (8, 8))
            return image

    gemini = Gemini()
    store = ProjectStore(tmp_path)
    service = SpriteService(store=store, gemini=gemini, remover=lambda image: image)

    result = service.generate_sprite(
        GenerateSpriteInput(
            prompt="a knight",
            enhanced_prompt="a detailed silver knight",
            style=Style.HIRES,
            view_mode=ViewMode.TOP_DOWN_2_5D,
            direction=Direction.DOWN_RIGHT,
        )
    )

    assert gemini.prompt == "a detailed silver knight"
    assert result.sprite_filename == "sprite.png"
    assert result.project.prompt == "a knight"
    assert result.project.prompt_source.value == "enhanced"
    assert store.load_image(result.project_id, "sprite").size == (8, 8)


@pytest.mark.parametrize("field", ["prompt", "enhanced_prompt"])
def test_generate_sprite_bounds_raw_and_enhanced_prompts(tmp_path, field):
    values = {"prompt": "a knight", "style": Style.HIRES}
    values[field] = "x" * (MAX_PROMPT_LENGTH + 1)

    with pytest.raises(ValidationServiceError, match="at most"):
        SpriteService(store=ProjectStore(tmp_path), image_provider=object()).generate_sprite(
            GenerateSpriteInput(**values)
        )


def test_generate_sprite_rejects_provider_image_over_pixel_budget(tmp_path):
    class OversizedImage:
        size = (MAX_IMAGE_DIMENSION // 2 + 1, MAX_IMAGE_DIMENSION // 2 + 1)
        width, height = size

        def load(self):
            raise AssertionError("oversized provider image must not be decoded")

    class Provider:
        def generate(self, *args, **kwargs):
            return OversizedImage()

    assert OversizedImage.width <= MAX_IMAGE_DIMENSION
    assert OversizedImage.height <= MAX_IMAGE_DIMENSION
    assert OversizedImage.width * OversizedImage.height > MAX_IMAGE_PIXELS

    with pytest.raises(UpstreamServiceError, match="image exceeds"):
        SpriteService(
            store=ProjectStore(tmp_path), image_provider=Provider()
        ).generate_sprite(GenerateSpriteInput(prompt="a knight", style=Style.HIRES))


def test_animation_and_export_return_asset_names_not_urls(tmp_path):
    class Gemini:
        def __init__(self):
            self.pose_references = []

        def edit(self, base, prompt, *, pose_reference=None):
            self.pose_references.append(pose_reference)
            image = Image.new("RGBA", (24, 24), (0, 0, 0, 0))
            image.paste(Image.new("RGBA", (8, 8), "red"), (8, 8))
            return image

    store = ProjectStore(tmp_path)
    pid = _project(store)
    gemini = Gemini()
    service = SpriteService(store=store, gemini=gemini, remover=lambda image: image)

    animation = service.animate(
        AnimateRequest(
            project_id=pid,
            action="walk",
            frames=4,
            direction=Direction.RIGHT,
        )
    )
    assert len(animation.frames) == 4
    assert animation.frame_filenames == [
        frame.rendered_filename for frame in animation.frames
    ]
    assert len(gemini.pose_references) == 4
    assert all(reference is not None for reference in gemini.pose_references)

    exported = service.export_sheet(pid, ExportOptions(format="json"))
    assert exported.sheet_filename == "sprite_sheet.png"
    assert exported.atlas_filename == "sprite.json"
    assert store.asset_path(pid, exported.sheet_filename).is_file()


@pytest.mark.parametrize(
    ("action", "expected_color"),
    [(None, "red"), ("walk", "blue")],
)
def test_single_frame_export_uses_static_sprite_or_animated_frame(
    tmp_path, action, expected_color
):
    store = ProjectStore(tmp_path)
    pid = store.create()
    store.save_image(pid, "sprite", Image.new("RGBA", (2, 2), "red"))
    if action is not None:
        store.save_image(pid, "frame_0", Image.new("RGBA", (2, 2), "blue"))
    store.write_manifest(
        pid,
        Project(
            id=pid,
            prompt="a knight",
            style=Style.HIRES,
            frames=[Frame(index=0)],
            action=action,
            fps=8 if action else None,
        ),
    )

    SpriteService(store=store).export_sheet(pid, ExportOptions())

    assert store.load_image(pid, "sprite_sheet").getpixel((0, 0)) == Image.new(
        "RGBA", (1, 1), expected_color
    ).getpixel((0, 0))


def test_animation_honors_provider_bounded_concurrency(tmp_path):
    class ConcurrentProvider:
        max_concurrency = 3

        def __init__(self):
            self.active = 0
            self.peak = 0
            self.lock = threading.Lock()

        def edit(self, base, prompt, *, pose_reference=None):
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.03)
            with self.lock:
                self.active -= 1
            return Image.new("RGBA", (8, 8), "red")

    store = ProjectStore(tmp_path)
    pid = _project(store)
    provider = ConcurrentProvider()

    result = SpriteService(
        store=store,
        image_provider=provider,
        remover=lambda image: image,
    ).animate(
        AnimateRequest(project_id=pid, action="walk", frames=6)
    )

    assert provider.peak == 3
    assert all(frame.status is FrameStatus.OK for frame in result.frames)


def test_animation_rejects_commit_when_project_changes_during_provider_work(tmp_path):
    store = ProjectStore(tmp_path)
    pid = _project(store)

    class RacingProvider:
        max_concurrency = 1

        def __init__(self):
            self.changed = False

        def edit(self, base, prompt, *, pose_reference=None):
            if not self.changed:
                self.changed = True
                other_store = ProjectStore(tmp_path)
                changed = other_store.read_manifest(pid)
                original_revision = changed.revision
                changed.prompt = "updated elsewhere"
                other_store.write_manifest(
                    pid, changed, expected_revision=original_revision
                )
            return Image.new("RGBA", (8, 8), "red")

    with pytest.raises(ProjectConflictServiceError):
        SpriteService(
            store=store,
            image_provider=RacingProvider(),
            remover=lambda image: image,
        ).animate(AnimateRequest(project_id=pid, action="walk", frames=4))

    assert store.read_manifest(pid).prompt == "updated elsewhere"
    assert not list((tmp_path / pid).glob("frame_*.png"))


def test_generate_cancellation_after_provider_call_never_commits(tmp_path):
    provider_started = threading.Event()
    provider_release = threading.Event()

    class SlowProvider:
        max_concurrency = 1

        def generate(self, *args, **kwargs):
            provider_started.set()
            assert provider_release.wait(timeout=2)
            return Image.new("RGBA", (8, 8), "red")

    store = ProjectStore(tmp_path)
    control = OperationControl()
    service = SpriteService(
        store=store,
        image_provider=SlowProvider(),
        remover=lambda image: image,
    )
    errors = []

    def run() -> None:
        try:
            service.generate_sprite(
                GenerateSpriteInput(prompt="a knight", style=Style.HIRES),
                control=control,
            )
        except Exception as exc:  # captured for the calling test thread
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert provider_started.wait(timeout=1)
    control.cancel()
    provider_release.set()
    worker.join(timeout=2)

    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], OperationCancelledError)
    assert list(store.root.iterdir()) == []


def test_animation_cancellation_at_commit_boundary_preserves_revision(tmp_path):
    class Provider:
        max_concurrency = 1

        def edit(self, *args, **kwargs):
            return Image.new("RGBA", (8, 8), "red")

    store = ProjectStore(tmp_path)
    pid = _project(store)
    original = store.read_manifest(pid)
    control = None

    def cancel_before_commit(progress) -> None:
        if progress.message == "Committing animation":
            control.cancel()

    control = OperationControl(on_progress=cancel_before_commit)

    with pytest.raises(OperationCancelledError):
        SpriteService(
            store=store,
            image_provider=Provider(),
            remover=lambda image: image,
        ).animate(
            AnimateRequest(project_id=pid, action="walk", frames=4),
            control=control,
        )

    persisted = store.read_manifest(pid)
    assert persisted.revision == original.revision
    assert persisted.action is None
    assert not list((tmp_path / pid).glob("frame_*.png"))


def test_provider_concurrency_is_shared_across_independent_services(tmp_path):
    class SharedProvider:
        max_concurrency = 2

        def __init__(self):
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
            return Image.new("RGBA", (8, 8), "red")

    provider = SharedProvider()

    def generate(index: int) -> None:
        SpriteService(
            store=ProjectStore(tmp_path / str(index)),
            image_provider=provider,
            remover=lambda image: image,
        ).generate_sprite(
            GenerateSpriteInput(prompt=f"knight {index}", style=Style.HIRES)
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(generate, range(4)))

    assert provider.peak == 2
