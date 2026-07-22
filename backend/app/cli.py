"""`sprite` command-line interface; JSON to stdout, diagnostics to stderr."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from app import deps
from app.actions import load_action_catalog
from app.recipe_batch import new_batch, run_batch
from app.recipes import (
    RecipeRunner,
    RecipeV1,
    capture_project_recipe,
    load_recipe,
    validate_recipe_semantics,
)
from app.config import get_settings
from app.services.sprite_runtime import SpriteRuntime


def _runtime() -> SpriteRuntime:
    return SpriteRuntime(store=deps.get_store(), providers=deps.build_provider_registry())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sprite")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    actions = commands.add_parser("actions")
    actions.add_subparsers(dest="action_command", required=True).add_parser("list")
    recipe = commands.add_parser("recipe")
    recipes = recipe.add_subparsers(dest="recipe_command", required=True)
    validate = recipes.add_parser("validate")
    validate.add_argument("path")
    capture = recipes.add_parser("capture")
    capture.add_argument("project_id")
    capture.add_argument("--output")
    run = recipes.add_parser("run")
    run.add_argument("path")
    batch = commands.add_parser("batch")
    batch.add_argument("state")
    batch.add_argument("recipes", nargs="*")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            settings = get_settings()
            result = {
                "storage": "ready" if Path(settings.projects_dir).parent.exists() else "not_ready",
                "providers": {
                    key: value.available
                    for key, value in settings.provider_availability().items()
                },
            }
        elif args.command == "actions":
            catalog = load_action_catalog(get_settings().action_packs_dir or None)
            result = {
                "actions": [
                    action.model_dump(mode="json")
                    for action in catalog.actions.values()
                ],
                "errors": catalog.errors,
            }
        elif args.command == "recipe" and args.recipe_command == "validate":
            recipe = load_recipe(args.path)
            validate_recipe_semantics(recipe)
            result = {"valid": True, "digest": recipe.digest()}
        elif args.command == "recipe" and args.recipe_command == "capture":
            recipe = capture_project_recipe(_runtime().store.read_manifest(args.project_id))
            text = recipe.model_dump_json(indent=2)
            if args.output:
                Path(args.output).write_text(text + "\n", encoding="utf-8")
            result = recipe.model_dump(mode="json")
        elif args.command == "recipe" and args.recipe_command == "run":
            project_id = RecipeRunner(_runtime()).run(load_recipe(args.path))
            result = {"project_id": project_id}
        else:
            runtime = _runtime()
            runner = RecipeRunner(runtime)
            state_path = Path(args.state)
            state = None
            if args.recipes:
                state = new_batch([load_recipe(path) for path in args.recipes])
            result = run_batch(state_path, runner, state).model_dump(mode="json")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"sprite: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
