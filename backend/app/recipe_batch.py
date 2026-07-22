"""Atomic, locked, resumable sequential recipe batches."""
from __future__ import annotations

import json
import os
from pathlib import Path
import uuid

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from app.recipes import RecipeRunner, RecipeV1

BATCH_FORMAT = "sprite-batch-state"
BATCH_VERSION = 1


class BatchItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: RecipeV1
    recipe_digest: str
    status: str = Field(pattern=r"^(pending|running|completed|failed|indeterminate)$")
    project_id: str | None = None
    error: str | None = Field(default=None, max_length=200)


class BatchState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = BATCH_FORMAT
    format_version: int = BATCH_VERSION
    items: list[BatchItem]


def new_batch(recipes: list[RecipeV1]) -> BatchState:
    return BatchState(
        items=[
            BatchItem(recipe=recipe, recipe_digest=recipe.digest(), status="pending")
            for recipe in recipes
        ]
    )


def run_batch(path: str | Path, runner: RecipeRunner, state: BatchState | None = None) -> BatchState:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(target) + ".lock"):
        current = state or BatchState.model_validate_json(target.read_text(encoding="utf-8"))
        for item in current.items:
            if item.recipe.digest() != item.recipe_digest:
                raise ValueError("batch recipe digest changed")
            if item.status == "completed":
                continue
            if item.status == "running":
                item.status = "indeterminate"
                item.error = "previous provider operation did not reach a safe checkpoint"
                _write_state(target, current)
                continue
            if item.status == "indeterminate":
                continue
            runner.preflight(item.recipe)
        _write_state(target, current)
        for item in current.items:
            if item.status != "pending":
                continue
            item.status = "running"
            item.error = None
            _write_state(target, current)
            try:
                item.project_id = runner.run(item.recipe)
                item.status = "completed"
            except Exception as exc:  # safe batch diagnostic; never include recipe/provider body
                item.status = "indeterminate"
                item.error = "provider work did not reach a safe completion checkpoint"
                _write_state(target, current)
                raise
            _write_state(target, current)
        return current


def _write_state(path: Path, state: BatchState) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
