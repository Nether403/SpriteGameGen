"""Filesystem-backed project store.

One directory per project (``<root>/<uuid>/``) holding PNG assets and a
``project.json`` manifest. No database. IDs and asset names are validated to
prevent path traversal outside the project root.
"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from PIL import Image

from app.models import Project

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MANIFEST_NAME = "project.json"


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
        path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        return path

    def read_manifest(self, pid: str) -> Project:
        path = self._project_dir(pid) / MANIFEST_NAME
        if not path.is_file():
            raise FileNotFoundError(path)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def list_projects(self) -> list[Project]:
        projects: list[Project] = []
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            manifest = child / MANIFEST_NAME
            if manifest.is_file():
                projects.append(
                    Project.model_validate_json(manifest.read_text(encoding="utf-8"))
                )
        return projects
