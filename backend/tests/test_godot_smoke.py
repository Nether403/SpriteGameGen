import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_godot_smoke.py"


def _load_smoke_module():
    spec = importlib.util.spec_from_file_location("run_godot_smoke", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_run_godot_smoke_imports_before_validation(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_godot_smoke.py", "--godot", "fake-godot"],
    )

    module = _load_smoke_module()
    assert module.main() == 0
    assert len(calls) == 2
    assert calls[0][0] == "fake-godot"
    assert "--import" in calls[0]
    assert calls[1][0] == "fake-godot"
    assert "--script" in calls[1]
