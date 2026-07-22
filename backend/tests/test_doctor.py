"""Credential-safe local readiness doctor."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "doctor.py"


def _load_doctor():
    spec = importlib.util.spec_from_file_location("sprite_doctor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ready_inputs(doctor, tmp_path: Path, **overrides):
    expected = {
        tmp_path / "backend" / "pyproject.toml",
        tmp_path / "backend" / "app" / "main.py",
        tmp_path / "frontend" / "package.json",
        tmp_path / "frontend" / "src" / "main.tsx",
    }
    values = {
        "root": tmp_path,
        "environ": {},
        "python_version": (3, 11, 0),
        "command_available": lambda command: command in {"node", "npm"},
        "file_exists": lambda path: path in expected,
        "project_writable": lambda _path: True,
        "rembg_cache_present": lambda: False,
    }
    values.update(overrides)
    return doctor.DoctorInputs(**values)


def test_ready_core_with_unconfigured_optional_providers_exits_zero(tmp_path):
    doctor = _load_doctor()

    report = doctor.inspect(_ready_inputs(doctor, tmp_path))

    assert report.exit_code == 0
    assert report.status("Gemini identity") == "unconfigured"
    assert report.status("Azure identity") == "unconfigured"
    assert report.status("rembg model cache") == "not cached"


def test_missing_core_prerequisites_exit_nonzero(tmp_path):
    doctor = _load_doctor()
    inputs = _ready_inputs(
        doctor,
        tmp_path,
        python_version=(3, 10, 9),
        command_available=lambda command: command == "node",
        file_exists=lambda _path: False,
        project_writable=lambda _path: False,
    )

    report = doctor.inspect(inputs)

    assert report.exit_code == 1
    assert report.status("Python >= 3.11") == "missing"
    assert report.status("npm") == "missing"
    assert report.status("backend files") == "missing"
    assert report.status("frontend files") == "missing"
    assert report.status("project directory") == "unwritable"


def test_provider_identity_states_use_presence_and_credential_file_existence(tmp_path):
    doctor = _load_doctor()
    credential_path = tmp_path / "private-service-account.json"
    checked_paths = []

    def credential_exists(path: Path) -> bool:
        checked_paths.append(path)
        return path == credential_path

    configured = _ready_inputs(
        doctor,
        tmp_path,
        environ={
            "GOOGLE_CLOUD_PROJECT": "sensitive-project-id",
            "GOOGLE_APPLICATION_CREDENTIALS": str(credential_path),
            "AZURE_OPENAI_ENDPOINT": "https://secret.example.invalid",
            "AZURE_OPENAI_API_KEY": "super-secret-key",
            "AZURE_OPENAI_DEPLOYMENT": "private-deployment",
        },
        file_exists=lambda path: credential_exists(path)
        if path == credential_path
        else path
        in {
            tmp_path / "backend" / "pyproject.toml",
            tmp_path / "backend" / "app" / "main.py",
            tmp_path / "frontend" / "package.json",
            tmp_path / "frontend" / "src" / "main.tsx",
        },
    )

    report = doctor.inspect(configured)

    assert report.exit_code == 0
    assert report.status("Gemini identity") == "configured"
    assert report.status("Azure identity") == "configured"
    assert checked_paths == [credential_path]


def test_partial_or_missing_provider_identity_is_invalid(tmp_path):
    doctor = _load_doctor()
    missing_credential = tmp_path / "missing.json"
    inputs = _ready_inputs(
        doctor,
        tmp_path,
        environ={
            "GOOGLE_CLOUD_PROJECT": "sensitive-project-id",
            "GOOGLE_APPLICATION_CREDENTIALS": str(missing_credential),
            "AZURE_OPENAI_ENDPOINT": "https://secret.example.invalid",
        },
    )

    report = doctor.inspect(inputs)

    assert report.exit_code == 1
    assert report.status("Gemini identity") == "invalid"
    assert report.status("Azure identity") == "invalid"


def test_gemini_project_without_explicit_credentials_uses_configured_adc(tmp_path):
    doctor = _load_doctor()
    inputs = _ready_inputs(
        doctor,
        tmp_path,
        environ={"GOOGLE_CLOUD_PROJECT": "sensitive-project-id"},
    )

    report = doctor.inspect(inputs)

    assert report.exit_code == 0
    assert report.status("Gemini identity") == "configured"


def test_rendered_output_never_contains_configuration_values_or_paths(tmp_path):
    doctor = _load_doctor()
    secrets = {
        "GOOGLE_CLOUD_PROJECT": "sensitive-project-id",
        "GOOGLE_APPLICATION_CREDENTIALS": str(tmp_path / "credentials.json"),
        "AZURE_OPENAI_ENDPOINT": "https://secret.example.invalid",
        "AZURE_OPENAI_API_KEY": "super-secret-key",
        "AZURE_OPENAI_DEPLOYMENT": "private-deployment",
        "PROJECTS_DIR": str(tmp_path / "private-projects"),
        "U2NET_HOME": str(tmp_path / "private-model-cache"),
    }
    report = doctor.inspect(
        _ready_inputs(doctor, tmp_path, environ=secrets, file_exists=lambda _path: True)
    )

    output = doctor.render(report)

    assert "Gemini identity: configured" in output
    assert "Azure identity: configured" in output
    for value in secrets.values():
        assert value not in output


def test_relative_project_directory_and_repository_files_are_not_cwd_relative(
    monkeypatch, tmp_path
):
    doctor = _load_doctor()
    foreign_cwd = tmp_path / "elsewhere"
    foreign_cwd.mkdir()
    monkeypatch.chdir(foreign_cwd)
    seen_project_paths = []
    inputs = _ready_inputs(
        doctor,
        tmp_path,
        environ={"PROJECTS_DIR": "custom-projects"},
        project_writable=lambda path: seen_project_paths.append(path) or True,
    )

    report = doctor.inspect(inputs)

    assert report.exit_code == 0
    assert seen_project_paths == [tmp_path / "backend" / "custom-projects"]
    assert doctor.repository_root() == SCRIPT_PATH.parents[1]


def test_project_directory_probe_leaves_no_files_for_existing_or_missing_target(
    tmp_path,
):
    doctor = _load_doctor()
    existing = tmp_path / "existing-projects"
    existing.mkdir()
    missing = tmp_path / "missing" / "nested-projects"
    before = set(tmp_path.rglob("*"))

    assert doctor.project_directory_writable(existing) is True
    assert doctor.project_directory_writable(missing) is True

    assert set(tmp_path.rglob("*")) == before


def test_main_prints_report_and_returns_report_exit_code(tmp_path):
    doctor = _load_doctor()
    lines = []

    exit_code = doctor.main(
        inputs=_ready_inputs(doctor, tmp_path), output=lines.append
    )

    assert exit_code == 0
    assert lines == [doctor.render(doctor.inspect(_ready_inputs(doctor, tmp_path)))]
