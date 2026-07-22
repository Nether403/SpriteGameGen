"""Credential-safe local readiness checks for SpriteGameGen."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory


MINIMUM_PYTHON = (3, 11)
BACKEND_FILES = (
    Path("backend/pyproject.toml"),
    Path("backend/app/main.py"),
)
FRONTEND_FILES = (
    Path("frontend/package.json"),
    Path("frontend/src/main.tsx"),
)


@dataclass(frozen=True)
class Check:
    name: str
    state: str
    failed: bool = False
    detail: str = ""


@dataclass(frozen=True)
class Report:
    checks: tuple[Check, ...]

    @property
    def exit_code(self) -> int:
        return int(any(check.failed for check in self.checks))

    def status(self, name: str) -> str:
        return next(check.state for check in self.checks if check.name == name)


@dataclass(frozen=True)
class DoctorInputs:
    root: Path
    environ: Mapping[str, str]
    python_version: tuple[int, ...]
    command_available: Callable[[str], bool]
    file_exists: Callable[[Path], bool]
    project_writable: Callable[[Path], bool]
    rembg_cache_present: Callable[[], bool]


def repository_root() -> Path:
    """Locate the repository from this script, never from the process CWD."""
    return Path(__file__).resolve().parents[1]


def _present(environ: Mapping[str, str], name: str) -> bool:
    return bool(environ.get(name, "").strip())


def _configured_path(root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = root / "backend" / path
    return path


def _gemini_state(inputs: DoctorInputs) -> str:
    project_present = _present(inputs.environ, "GOOGLE_CLOUD_PROJECT")
    credential_present = _present(inputs.environ, "GOOGLE_APPLICATION_CREDENTIALS")
    if not project_present and not credential_present:
        return "unconfigured"
    if not project_present:
        return "invalid"
    if not credential_present:
        return "configured"

    credential_path = _configured_path(
        inputs.root, inputs.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    )
    try:
        return "configured" if inputs.file_exists(credential_path) else "invalid"
    except OSError:
        return "invalid"


def _azure_state(environ: Mapping[str, str]) -> str:
    identity = (
        _present(environ, "AZURE_OPENAI_ENDPOINT"),
        _present(environ, "AZURE_OPENAI_API_KEY"),
        _present(environ, "AZURE_OPENAI_DEPLOYMENT"),
    )
    if all(identity):
        return "configured"
    if any(identity):
        return "invalid"
    return "unconfigured"


def _all_files_exist(
    root: Path, relative_paths: tuple[Path, ...], exists: Callable[[Path], bool]
) -> bool:
    try:
        return all(exists(root / path) for path in relative_paths)
    except OSError:
        return False


def _project_directory(inputs: DoctorInputs) -> Path:
    configured = inputs.environ.get("PROJECTS_DIR", "").strip() or "projects"
    return _configured_path(inputs.root, configured)


def inspect(inputs: DoctorInputs) -> Report:
    """Evaluate readiness using only injected, deterministic probes."""
    python_ready = inputs.python_version[:2] >= MINIMUM_PYTHON
    try:
        node_ready = inputs.command_available("node")
    except OSError:
        node_ready = False
    try:
        npm_ready = inputs.command_available("npm")
    except OSError:
        npm_ready = False

    backend_ready = _all_files_exist(inputs.root, BACKEND_FILES, inputs.file_exists)
    frontend_ready = _all_files_exist(inputs.root, FRONTEND_FILES, inputs.file_exists)
    try:
        projects_ready = inputs.project_writable(_project_directory(inputs))
    except OSError:
        projects_ready = False

    gemini_state = _gemini_state(inputs)
    azure_state = _azure_state(inputs.environ)
    try:
        model_cached = inputs.rembg_cache_present()
    except OSError:
        model_cached = False

    checks = (
        Check(
            "Python >= 3.11",
            "ready" if python_ready else "missing",
            failed=not python_ready,
            detail=".".join(str(part) for part in inputs.python_version[:3]),
        ),
        Check("Node.js", "available" if node_ready else "missing", failed=not node_ready),
        Check("npm", "available" if npm_ready else "missing", failed=not npm_ready),
        Check(
            "backend files",
            "present" if backend_ready else "missing",
            failed=not backend_ready,
        ),
        Check(
            "frontend files",
            "present" if frontend_ready else "missing",
            failed=not frontend_ready,
        ),
        Check(
            "project directory",
            "writable" if projects_ready else "unwritable",
            failed=not projects_ready,
        ),
        Check("Gemini identity", gemini_state, failed=gemini_state == "invalid"),
        Check("Azure identity", azure_state, failed=azure_state == "invalid"),
        Check("rembg model cache", "cached" if model_cached else "not cached"),
    )
    return Report(checks)


def project_directory_writable(target: Path) -> bool:
    """Probe project storage and clean every temporary artifact before returning."""
    try:
        if target.exists():
            if not target.is_dir():
                return False
            with NamedTemporaryFile(prefix=".sprite-doctor-", dir=target):
                return True

        ancestor = target.parent
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        if not ancestor.is_dir():
            return False
        with TemporaryDirectory(prefix=".sprite-doctor-", dir=ancestor) as temporary:
            with NamedTemporaryFile(dir=temporary):
                return True
    except OSError:
        return False


def _rembg_cache_present(environ: Mapping[str, str]) -> bool:
    configured = environ.get("U2NET_HOME", "").strip()
    cache_dir = Path(configured).expanduser() if configured else Path.home() / ".u2net"
    try:
        return cache_dir.is_dir() and any(cache_dir.glob("*.onnx"))
    except OSError:
        return False


def default_inputs() -> DoctorInputs:
    environ = dict(os.environ)
    return DoctorInputs(
        root=repository_root(),
        environ=environ,
        python_version=tuple(sys.version_info[:3]),
        command_available=lambda command: shutil.which(command) is not None,
        file_exists=Path.is_file,
        project_writable=project_directory_writable,
        rembg_cache_present=lambda: _rembg_cache_present(environ),
    )


def render(report: Report) -> str:
    """Render only fixed labels and safe states; never configuration values."""
    lines = ["SpriteGameGen readiness"]
    for check in report.checks:
        detail = f" ({check.detail})" if check.detail else ""
        lines.append(f"{check.name}: {check.state}{detail}")
    lines.append("Overall: ready" if report.exit_code == 0 else "Overall: not ready")
    return "\n".join(lines)


def main(
    *,
    inputs: DoctorInputs | None = None,
    output: Callable[[str], None] = print,
) -> int:
    report = inspect(inputs or default_inputs())
    output(render(report))
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
