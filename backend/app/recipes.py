"""Credential-free recipe V1 capture, validation, and sequential execution."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.actions import ActionCatalog, load_action_catalog
from app.models import (
    AnimateRequest,
    Direction,
    ImageProviderName,
    LoopMode,
    Project,
    RenderSettings,
    Style,
    ViewMode,
    ExportOptions,
)
from app.config import get_settings
from app.services.image_provider import ProviderCapability
from app.services.provider_selection import ProviderRequirements
from app.services.sprite_service import GenerateSpriteInput

RECIPE_FORMAT = "sprite-recipe"
RECIPE_VERSION = 1


class RecipeClip(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    frames: int = Field(ge=2, le=8)
    fps: int = Field(ge=1, le=60)
    direction: Direction
    loop_mode: LoopMode = LoopMode.LOOP
    custom_motion: str | None = Field(default=None, min_length=1, max_length=2000)
    first_pose: str | None = Field(default=None, max_length=1000)
    last_pose: str | None = Field(default=None, max_length=1000)


class RecipeExport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["sheet", "character_bundle"]
    scope: Literal["active", "all_enabled"] = "active"
    engine_profile: Literal["godot4_animatedsprite2d"] | None = None


class RecipeV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["sprite-recipe"] = RECIPE_FORMAT
    format_version: Literal[1] = RECIPE_VERSION
    prompt: str = Field(min_length=1, max_length=2000)
    style: Style
    view_mode: ViewMode = ViewMode.SIDE_SCROLLER
    direction: Direction = Direction.LEFT
    provider: ImageProviderName = ImageProviderName.AUTO
    render_settings: RenderSettings = Field(default_factory=RenderSettings)
    clips: list[RecipeClip] = Field(default_factory=list, max_length=128)
    exports: list[RecipeExport] = Field(default_factory=list, max_length=16)

    def digest(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def capture_project_recipe(project: Project) -> RecipeV1:
    return RecipeV1(
        prompt=project.prompt,
        style=project.style,
        view_mode=project.view_mode,
        direction=project.direction,
        provider=project.image_provider,
        render_settings=project.render_settings,
        clips=[
            RecipeClip(
                action=clip.action,
                name=clip.name,
                frames=len(clip.frames),
                fps=clip.fps,
                direction=clip.direction,
                loop_mode=clip.loop_mode,
                custom_motion=(
                    clip.action_snapshot.motion
                    if clip.action_ref and clip.action_ref.startswith("custom:")
                    and clip.action_snapshot
                    else None
                ),
                first_pose=(clip.action_snapshot.first_pose if clip.action_snapshot else None),
                last_pose=(clip.action_snapshot.last_pose if clip.action_snapshot else None),
            )
            for clip in sorted(project.clips.values(), key=lambda item: item.id)
        ],
    )


def load_recipe(path: str | Path) -> RecipeV1:
    return RecipeV1.model_validate_json(Path(path).read_text(encoding="utf-8"))


def validate_recipe_semantics(
    recipe: RecipeV1, catalog: ActionCatalog | None = None
) -> None:
    catalog = catalog or load_action_catalog(get_settings().action_packs_dir or None)
    for clip in recipe.clips:
        if clip.custom_motion is None:
            try:
                action = catalog.get(clip.action)
            except KeyError as exc:
                raise ValueError(f"unknown recipe action: {clip.action!r}") from exc
            if not action.min_frames <= clip.frames <= action.max_frames:
                raise ValueError(
                    f"frames for {clip.action!r} must be between "
                    f"{action.min_frames} and {action.max_frames}"
                )
    if any(export.kind == "character_bundle" for export in recipe.exports) and not recipe.clips:
        raise ValueError("character bundle recipes require at least one clip")


class RecipeRunner:
    def __init__(self, runtime, *, catalog: ActionCatalog | None = None):
        self.runtime = runtime
        self.catalog = catalog or load_action_catalog(
            get_settings().action_packs_dir or None
        )

    def preflight(self, recipe: RecipeV1) -> None:
        validate_recipe_semantics(recipe, self.catalog)
        required = {ProviderCapability.GENERATE}
        if recipe.clips:
            required.update(
                {ProviderCapability.EDIT, ProviderCapability.IDENTITY_REFERENCE}
            )
        if any(
            clip.custom_motion is None and self.catalog.get(clip.action).guides
            for clip in recipe.clips
        ):
            required.add(ProviderCapability.POSE_REFERENCE)
        self.runtime.providers.resolve(
            recipe.provider, ProviderRequirements(frozenset(required))
        )

    def run(self, recipe: RecipeV1) -> str:
        self.preflight(recipe)
        service = self.runtime.service_for_provider(recipe.provider)
        generated = service.generate_sprite(
            GenerateSpriteInput(
                prompt=recipe.prompt,
                style=recipe.style,
                view_mode=recipe.view_mode,
                direction=recipe.direction,
            )
        )
        project_id = generated.project_id
        service.set_render_settings(project_id, recipe.render_settings)
        for clip in recipe.clips:
            self.runtime.service_for_project(project_id).animate(
                AnimateRequest(
                    project_id=project_id,
                    clip_id=uuid.uuid4().hex[:16],
                    action=clip.action,
                    clip_name=clip.name,
                    frames=clip.frames,
                    fps=clip.fps,
                    direction=clip.direction,
                    loop_mode=clip.loop_mode,
                    custom_motion=clip.custom_motion,
                    first_pose=clip.first_pose,
                    last_pose=clip.last_pose,
                )
            )
        for export in recipe.exports:
            if export.kind == "sheet":
                self.runtime.storage_service().export_sheet(
                    project_id, ExportOptions()
                )
            else:
                self.runtime.storage_service().export_character_bundle(
                    project_id,
                    scope=export.scope,
                    engine_profile=export.engine_profile,
                )
        project = self.runtime.store.read_manifest(project_id)
        project.recipe_provenance = {
            "format": RECIPE_FORMAT,
            "version": str(RECIPE_VERSION),
            "digest": recipe.digest(),
        }
        self.runtime.store.write_manifest(
            project_id, project, expected_revision=project.revision
        )
        return project_id
