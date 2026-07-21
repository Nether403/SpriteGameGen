"""Framework-neutral SpriteService behavior."""
import threading
import time

from PIL import Image
import pytest

from app.models import (
    Direction,
    AnimateRequest,
    EnhancePromptRequest,
    Frame,
    FrameStatus,
    ExportOptions,
    Project,
    ProjectHealth,
    Style,
    ViewMode,
)
from app.services.sprite_service import (
    GenerateSpriteInput,
    ProjectNotFoundError,
    ProjectUnavailableError,
    SpriteService,
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
        "frame_0.png",
        "frame_1.png",
        "frame_2.png",
        "frame_3.png",
    ]
    assert len(gemini.pose_references) == 4
    assert all(reference is not None for reference in gemini.pose_references)

    exported = service.export_sheet(pid, ExportOptions(format="json"))
    assert exported.sheet_filename == "sprite_sheet.png"
    assert exported.atlas_filename == "sprite.json"
    assert store.asset_path(pid, exported.sheet_filename).is_file()


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
