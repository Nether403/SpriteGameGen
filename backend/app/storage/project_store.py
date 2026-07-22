"""Filesystem-backed project store.

One directory per project (``<root>/<uuid>/``) holding PNG assets and a
``project.json`` manifest. No database. IDs and asset names are validated to
prevent path traversal outside the project root.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from filelock import FileLock, Timeout
from PIL import Image

from app.manifest import load_manifest
from app.models import Frame, Project, ProjectHealth, FrameStatus

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
MANIFEST_NAME = "project.json"
PROJECT_MARKER = ".sprite-project"


class ProjectConflictError(RuntimeError):
    """A caller attempted to commit from an outdated project revision."""


class ProjectBusyError(RuntimeError):
    """A project lock could not be acquired within the configured timeout."""


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
    def __init__(self, root: str | Path, *, lock_timeout: float = 10.0):
        self.root = Path(root).expanduser().resolve()
        dangerous_roots = {
            Path.cwd().resolve(),
            Path.home().resolve(),
            Path(self.root.anchor).resolve(),
        }
        if self.root in dangerous_roots:
            raise ValueError("projects root must be a dedicated subdirectory")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock_root = self.root / ".locks"
        self._lock_timeout = lock_timeout
        self._locks: dict[str, FileLock] = {}

    def _project_dir(self, pid: str) -> Path:
        _check_name(pid, "project id")
        return self.root / pid

    def _canonical_project_dir(self, pid: str, *, require_owned: bool = True) -> Path:
        path = self._project_dir(pid)
        if not path.is_dir():
            raise FileNotFoundError(path)
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(self.root):
            raise ValueError("project directory resolves outside the project root")
        if require_owned and not self._is_owned_project(path, pid):
            raise ValueError(f"directory {pid!r} is not a sprite project")
        return resolved

    @staticmethod
    def _is_owned_project(path: Path, pid: str) -> bool:
        marker = path / PROJECT_MARKER
        if marker.is_file():
            try:
                return marker.read_text(encoding="utf-8").strip() == pid
            except OSError:
                return False
        manifest = path / MANIFEST_NAME
        if not manifest.is_file():
            return False
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return False
        return data.get("id") == pid

    def _lock_for(self, pid: str) -> FileLock:
        _check_name(pid, "project id")
        self._lock_root.mkdir(exist_ok=True)
        return self._locks.setdefault(
            pid,
            FileLock(str(self._lock_root / f"{pid}.lock"), timeout=self._lock_timeout),
        )

    @contextmanager
    def project_lock(self, pid: str) -> Iterator[None]:
        """Serialize one project's reads and writes across threads and processes."""

        try:
            with self._lock_for(pid):
                yield
        except Timeout as exc:
            raise ProjectBusyError(f"project {pid!r} is busy") from exc

    @staticmethod
    def _atomic_replace(target: Path, writer: Callable[[Path], None]) -> None:
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            writer(temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _stage_file(target: Path, writer: Callable[[Path], None]) -> Path:
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            writer(temporary)
            return temporary
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _asset_target(self, pid: str, filename: str, *, require_file: bool) -> Path:
        project_dir = self._canonical_project_dir(pid)
        target = project_dir / filename
        resolved = target.resolve(strict=False)
        if not resolved.is_relative_to(project_dir):
            raise ValueError("asset resolves outside the project root")
        if require_file and not target.is_file():
            raise FileNotFoundError(target)
        return target

    # --- lifecycle ---
    def create(self) -> str:
        pid = uuid.uuid4().hex
        project_dir = self.root / pid
        project_dir.mkdir(parents=True, exist_ok=False)
        (project_dir / PROJECT_MARKER).write_text(pid, encoding="utf-8")
        return pid

    def delete_project(self, pid: str) -> None:
        _check_name(pid, "project id")
        path = self._project_dir(pid)
        if not path.exists():
            return
        with self.project_lock(pid):
            owned = self._canonical_project_dir(pid)
            shutil.rmtree(owned)

    def asset_path(self, pid: str, filename: str) -> Path:
        """Resolve a project asset path, rejecting traversal. Raises FileNotFoundError
        if the asset does not exist."""
        stem, _, ext = filename.rpartition(".")
        _check_name(stem or filename, "file name")
        if ext:
            _check_name(ext, "file extension")
        with self.project_lock(pid):
            return self._asset_target(pid, filename, require_file=True)

    def commit_project(
        self,
        pid: str,
        project: Project,
        *,
        expected_revision: int,
        images: dict[str, Image.Image] | None = None,
        texts: dict[str, str] | None = None,
        blobs: dict[str, bytes] | None = None,
        delete_images: set[str] | None = None,
        delete_files: set[str] | None = None,
    ) -> Path:
        """Commit project assets and its manifest as one revision-checked unit.

        Asset replacements are staged before the lock is acquired. Existing files
        are retained as backups until the manifest commit succeeds, allowing normal
        I/O failures to roll back without exposing a half-written project.
        """

        image_targets = {
            self._asset_target(pid, f"{name}.png", require_file=False): image
            for name, image in (images or {}).items()
        }
        text_targets = {
            self._asset_target(pid, filename, require_file=False): content
            for filename, content in (texts or {}).items()
        }
        blob_targets = {
            self._asset_target(pid, filename, require_file=False): content
            for filename, content in (blobs or {}).items()
        }
        delete_targets = {
            self._asset_target(pid, f"{name}.png", require_file=False)
            for name in (delete_images or set())
        } | {
            self._asset_target(pid, filename, require_file=False)
            for filename in (delete_files or set())
        }
        delete_targets -= set(image_targets) | set(text_targets) | set(blob_targets)

        staged: dict[Path, Path] = {}
        try:
            for target, image in image_targets.items():
                staged[target] = self._stage_file(
                    target, lambda temporary, value=image: value.save(temporary, format="PNG")
                )
            for target, content in text_targets.items():
                staged[target] = self._stage_file(
                    target,
                    lambda temporary, value=content: temporary.write_text(
                        value, encoding="utf-8", newline=""
                    ),
                )
            for target, content in blob_targets.items():
                staged[target] = self._stage_file(
                    target,
                    lambda temporary, value=content: temporary.write_bytes(value),
                )
            with self.project_lock(pid):
                current_revision = self._current_revision_unlocked(pid)
                if current_revision != expected_revision:
                    raise ProjectConflictError("project changed during the operation")
                self._replace_staged_unlocked(
                    staged,
                    delete_targets,
                    lambda: self._write_manifest_unlocked(
                        pid, project, expected_revision=expected_revision
                    ),
                )
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)
        return self._project_dir(pid) / MANIFEST_NAME

    def commit_assets(
        self,
        pid: str,
        *,
        expected_revision: int,
        images: dict[str, Image.Image] | None = None,
        texts: dict[str, str] | None = None,
        blobs: dict[str, bytes] | None = None,
    ) -> None:
        """Commit derived assets only if the source project revision is unchanged."""

        image_targets = {
            self._asset_target(pid, f"{name}.png", require_file=False): image
            for name, image in (images or {}).items()
        }
        text_targets = {
            self._asset_target(pid, filename, require_file=False): content
            for filename, content in (texts or {}).items()
        }
        blob_targets = {
            self._asset_target(pid, filename, require_file=False): content
            for filename, content in (blobs or {}).items()
        }
        staged: dict[Path, Path] = {}
        try:
            for target, image in image_targets.items():
                staged[target] = self._stage_file(
                    target, lambda temporary, value=image: value.save(temporary, format="PNG")
                )
            for target, content in text_targets.items():
                staged[target] = self._stage_file(
                    target,
                    lambda temporary, value=content: temporary.write_text(
                        value, encoding="utf-8", newline=""
                    ),
                )
            for target, content in blob_targets.items():
                staged[target] = self._stage_file(
                    target,
                    lambda temporary, value=content: temporary.write_bytes(value),
                )
            with self.project_lock(pid):
                if self._current_revision_unlocked(pid) != expected_revision:
                    raise ProjectConflictError("project changed during the operation")
                self._replace_staged_unlocked(staged, set(), lambda: None)
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)

    def _current_revision_unlocked(self, pid: str) -> int:
        manifest = self._project_dir(pid) / MANIFEST_NAME
        return self._read_manifest_unlocked(pid).revision if manifest.is_file() else 0

    @staticmethod
    def _replace_staged_unlocked(
        staged: dict[Path, Path],
        delete_targets: set[Path],
        finalize: Callable[[], None],
    ) -> None:
        transaction_id = uuid.uuid4().hex
        backups: dict[Path, Path] = {}
        replaced: list[Path] = []
        targets = list(staged) + list(delete_targets)
        try:
            for target in targets:
                if target.exists():
                    backup = target.with_name(f".{target.name}.{transaction_id}.bak")
                    os.replace(target, backup)
                    backups[target] = backup
                if target in staged:
                    os.replace(staged[target], target)
                replaced.append(target)
            finalize()
        except Exception:
            for target in reversed(replaced):
                target.unlink(missing_ok=True)
                backup = backups.get(target)
                if backup is not None and backup.exists():
                    os.replace(backup, target)
            raise
        finally:
            for backup in backups.values():
                backup.unlink(missing_ok=True)

    # --- images ---
    def save_image(self, pid: str, name: str, img: Image.Image) -> Path:
        _check_name(name, "image name")
        path = self._asset_target(pid, f"{name}.png", require_file=False)
        with self.project_lock(pid):
            self._atomic_replace(path, lambda temporary: img.save(temporary, format="PNG"))
        return path

    def load_image(self, pid: str, name: str) -> Image.Image:
        _check_name(name, "image name")
        with self.project_lock(pid):
            path = self._asset_target(pid, f"{name}.png", require_file=True)
            with Image.open(path) as im:
                return im.convert("RGBA")

    def delete_image(self, pid: str, name: str) -> None:
        """Remove a PNG asset if present; a missing file is not an error."""
        _check_name(name, "image name")
        with self.project_lock(pid):
            self._asset_target(pid, f"{name}.png", require_file=False).unlink(
                missing_ok=True
            )

    # --- text assets (atlas files) ---
    def write_text(self, pid: str, filename: str, content: str) -> Path:
        stem, _, ext = filename.rpartition(".")
        _check_name(stem or filename, "file name")
        if ext:
            _check_name(ext, "file extension")
        path = self._asset_target(pid, filename, require_file=False)
        with self.project_lock(pid):
            self._atomic_replace(
                path,
                lambda temporary: temporary.write_text(
                    content, encoding="utf-8", newline=""
                ),
            )
        return path

    # --- manifest ---
    def write_manifest(
        self,
        pid: str,
        project: Project,
        *,
        expected_revision: int | None = None,
    ) -> Path:
        with self.project_lock(pid):
            return self._write_manifest_unlocked(
                pid, project, expected_revision=expected_revision
            )

    def _write_manifest_unlocked(
        self,
        pid: str,
        project: Project,
        *,
        expected_revision: int | None,
    ) -> Path:
        if project.id != pid:
            raise ValueError("manifest project id does not match its directory")
        path = self._asset_target(pid, MANIFEST_NAME, require_file=False)
        current_revision = 0
        if path.is_file():
            current_revision = self._read_manifest_unlocked(pid).revision
        if expected_revision is not None and current_revision != expected_revision:
            raise ProjectConflictError("project changed during the operation")

        persisted = project.model_copy(deep=True)
        persisted.schema_version = 2
        persisted.revision = current_revision + 1
        persisted.updated_at = datetime.now(timezone.utc)
        self._atomic_replace(
            path,
            lambda temporary: temporary.write_text(
                persisted.model_dump_json(indent=2), encoding="utf-8"
            ),
        )
        project.schema_version = persisted.schema_version
        project.revision = persisted.revision
        project.updated_at = persisted.updated_at
        return path

    def read_manifest(self, pid: str) -> Project:
        with self.project_lock(pid):
            return self._read_manifest_unlocked(pid)

    def _read_manifest_unlocked(self, pid: str) -> Project:
        path = self._asset_target(pid, MANIFEST_NAME, require_file=True)
        if not path.is_file():
            raise FileNotFoundError(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("id") != pid:
            raise ValueError("manifest project id does not match its directory")
        manifest_time = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        project = load_manifest(data, fallback_time=manifest_time)
        if not project.clips and not project.frames:
            project.frames = [
                Frame(
                    index=0,
                    source_filename=project.source_sprite_filename,
                    rendered_filename=project.sprite_filename,
                )
            ]
        return project

    def get_project_record(self, pid: str) -> ProjectRecord:
        with self.project_lock(pid):
            project_dir = self._canonical_project_dir(pid)
            manifest = project_dir / MANIFEST_NAME
            updated_at = datetime.fromtimestamp(
                (manifest if manifest.is_file() else project_dir).stat().st_mtime,
                tz=timezone.utc,
            )
            has_sprite = (project_dir / "sprite.png").is_file()
            if not manifest.is_file():
                return ProjectRecord(pid, None, ProjectHealth.INCOMPLETE, updated_at, has_sprite)
            try:
                project = self._read_manifest_unlocked(pid)
            except Exception:  # noqa: BLE001 - catalog must isolate bad folders
                return ProjectRecord(pid, None, ProjectHealth.CORRUPT, updated_at, has_sprite)

            healthy = has_sprite
            if healthy:
                healthy = all(
                    frame.status is FrameStatus.FAILED
                    or not frame.enabled
                    or bool(frame.rendered_filename)
                    and (project_dir / str(frame.rendered_filename)).is_file()
                    for clip in project.clips.values()
                    for frame in clip.frames
                )
            health = ProjectHealth.READY if healthy else ProjectHealth.INCOMPLETE
            return ProjectRecord(pid, project, health, project.updated_at, has_sprite)

    def list_project_records(self) -> list[ProjectRecord]:
        records: list[ProjectRecord] = []
        for child in self.root.iterdir():
            if not child.is_dir() or not _SAFE_NAME.fullmatch(child.name):
                continue
            if not self._is_owned_project(child, child.name):
                continue
            records.append(self.get_project_record(child.name))
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def list_projects(self) -> list[Project]:
        return [record.project for record in self.list_project_records() if record.project]
