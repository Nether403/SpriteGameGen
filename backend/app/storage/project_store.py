"""Filesystem-backed project store.

One directory per project (``<root>/<uuid>/``) holding PNG assets and a
``project.json`` manifest. No database. IDs and asset names are validated to
prevent path traversal outside the project root.
"""
from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.models import Project, ProjectHealth, FrameStatus

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MANIFEST_NAME = "project.json"


@dataclass(frozen=True)
class ProjectRecord:
    """Catalog scan result, including projects that cannot currently resume."""

    id: str
    project: Project | None
    health: ProjectHealth
    updated_at: datetime
    has_sprite: bool


def _check_name(value: str, kind: str) -> str:
    if not _SAFE_NAME.match(value):
        raise ValueError(f"unsafe {kind}: {value!r}")
    return value


class ProjectStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, pid: str) -> Path:
        _check_name(pid, "project id")
        return self.root / pid

    # --- lifecycle ---
    def create(self) -> str:
        pid = uuid.uuid4().hex
        (self.root / pid).mkdir(parents=True, exist_ok=False)
        return pid

    def delete_project(self, pid: str) -> None:
        _check_name(pid, "project id")
        shutil.rmtree(self.root / pid, ignore_errors=True)

    def asset_path(self, pid: str, filename: str) -> Path:
        """Resolve a project asset path, rejecting traversal. Raises FileNotFoundError
        if the asset does not exist."""
        stem, _, ext = filename.rpartition(".")
        _check_name(stem or filename, "file name")
        if ext:
            _check_name(ext, "file extension")
        path = self._project_dir(pid) / filename
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    # --- images ---
    def save_image(self, pid: str, name: str, img: Image.Image) -> Path:
        _check_name(name, "image name")
        path = self._project_dir(pid) / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, format="PNG")
        return path

    def load_image(self, pid: str, name: str) -> Image.Image:
        _check_name(name, "image name")
        path = self._project_dir(pid) / f"{name}.png"
        if not path.is_file():
            raise FileNotFoundError(path)
        with Image.open(path) as im:
            return im.convert("RGBA")

    def delete_image(self, pid: str, name: str) -> None:
        """Remove a PNG asset if present; a missing file is not an error."""
        _check_name(name, "image name")
        (self._project_dir(pid) / f"{name}.png").unlink(missing_ok=True)

    # --- text assets (atlas files) ---
    def write_text(self, pid: str, filename: str, content: str) -> Path:
        stem, _, ext = filename.rpartition(".")
        _check_name(stem or filename, "file name")
        if ext:
            _check_name(ext, "file extension")
        path = self._project_dir(pid) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        return path

    # --- manifest ---
    def write_manifest(self, pid: str, project: Project) -> Path:
        path = self._project_dir(pid) / MANIFEST_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        project.schema_version = max(1, project.schema_version)
        project.updated_at = datetime.now(timezone.utc)
        path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read_manifest(self, pid: str) -> Project:
        path = self._project_dir(pid) / MANIFEST_NAME
        if not path.is_file():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest_time = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        data.setdefault("schema_version", 1)
        data.setdefault("created_at", manifest_time)
        data.setdefault("updated_at", manifest_time)
        return Project.model_validate(data)

    def get_project_record(self, pid: str) -> ProjectRecord:
        project_dir = self._project_dir(pid)
        if not project_dir.is_dir():
            raise FileNotFoundError(project_dir)
        manifest = project_dir / MANIFEST_NAME
        updated_at = datetime.fromtimestamp(
            (manifest if manifest.is_file() else project_dir).stat().st_mtime,
            tz=timezone.utc,
        )
        has_sprite = (project_dir / "sprite.png").is_file()
        if not manifest.is_file():
            return ProjectRecord(pid, None, ProjectHealth.INCOMPLETE, updated_at, has_sprite)
        try:
            project = self.read_manifest(pid)
        except Exception:  # noqa: BLE001 - catalog must isolate bad folders
            return ProjectRecord(pid, None, ProjectHealth.CORRUPT, updated_at, has_sprite)

        healthy = has_sprite
        if healthy and project.action is not None:
            healthy = all(
                frame.status is FrameStatus.FAILED
                or (project_dir / f"frame_{frame.index}.png").is_file()
                for frame in project.frames
            )
        health = ProjectHealth.READY if healthy else ProjectHealth.INCOMPLETE
        return ProjectRecord(pid, project, health, project.updated_at, has_sprite)

    def list_project_records(self) -> list[ProjectRecord]:
        records: list[ProjectRecord] = []
        for child in self.root.iterdir():
            if not child.is_dir() or not _SAFE_NAME.fullmatch(child.name):
                continue
            records.append(self.get_project_record(child.name))
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def list_projects(self) -> list[Project]:
        return [record.project for record in self.list_project_records() if record.project]
