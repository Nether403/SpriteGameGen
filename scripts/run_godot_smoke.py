"""Create generated Godot resources and verify them with pinned headless Godot."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.character_bundle import BundleClip, BundleFrame, _godot_files  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", default="godot")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="sprite-godot-smoke-") as temporary:
        project = Path(temporary)
        frame_path = project / "frames" / "walk-a"
        frame_path.mkdir(parents=True)
        Image.new("RGBA", (2, 2), "red").save(frame_path / "0000.png")
        clip = BundleClip(
            id="walk-a",
            name="Walk",
            action="walk",
            direction="left",
            loop_mode="loop",
            loop_start=0,
            loop_end=0,
            frames=[
                BundleFrame(
                    index=0,
                    path="frames/walk-a/0000.png",
                    duration_ms=125,
                    sha256="0" * 64,
                    width=2,
                    height=2,
                )
            ],
        )
        for name, payload in _godot_files([clip]).items():
            (project / name).write_bytes(payload)
        (project / "project.godot").write_text(
            '[application]\nconfig/name="SpriteBundleSmoke"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [
                args.godot,
                "--headless",
                "--path",
                str(project),
                "--script",
                str(ROOT / "scripts" / "godot_validate.gd"),
            ],
            check=False,
        )
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
