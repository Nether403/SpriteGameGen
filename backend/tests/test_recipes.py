from app.models import AnimationClip, Frame, Project, Style
from app.recipes import RecipeV1, capture_project_recipe


def test_recipe_is_strict_versioned_and_credential_free():
    recipe = RecipeV1(
        prompt="knight",
        style="pixel",
        clips=[{"action": "walk", "frames": 4, "fps": 8, "direction": "left"}],
    )

    text = recipe.model_dump_json()
    assert recipe.format_version == 1
    assert "endpoint" not in text
    assert "credential" not in text
    assert "projects_dir" not in text


def test_project_capture_uses_clip_snapshots_without_paths():
    clip = AnimationClip(
        id="walk-a",
        name="Walk",
        action="walk",
        frames=[Frame(index=0), Frame(index=1)],
    )
    project = Project(
        id="p", prompt="knight", style=Style.PIXEL,
        clips={clip.id: clip}, active_clip_id=clip.id,
    )

    recipe = capture_project_recipe(project)

    assert recipe.clips[0].action == "walk"
    assert "source_filename" not in recipe.model_dump_json()
