"""Manual, opt-in ComfyUI configuration and quality validation harness."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.services.comfyui_provider import ComfyUIProvider  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--frames", type=int, default=4)
    args = parser.parse_args()
    settings = get_settings()
    readiness = settings.comfyui_readiness()
    if not readiness.available:
        print(json.dumps({"ready": False, "detail": readiness.detail}))
        return 1
    provider = ComfyUIProvider(
        base_url=settings.comfyui_url,
        descriptor_path=settings.comfyui_workflow_descriptor,
        timeout_s=settings.comfyui_timeout_seconds,
    )
    report = {
        "ready": True,
        "capabilities": sorted(value.value for value in provider.capabilities),
        "requested_repeats": args.repeats,
        "requested_frames": args.frames,
        "live_run": False,
    }
    print(json.dumps(report, sort_keys=True))
    if not args.preflight:
        print("Live generation requires operator-reviewed prompts and is not run automatically.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
