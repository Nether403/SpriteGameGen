"""Live end-to-end smoke test — MANUAL ONLY, makes real Gemini calls.

This is intentionally kept out of the pytest suite (the automated tests use a
fake SDK and never touch the network). Run it by hand with real Vertex AI
credentials to confirm the live integration works and the SDK request/response
signatures still match what ``gemini_client`` expects.

What it does:
  1. generate() one base sprite from a text prompt,
  2. edit() it once into a walk-frame pose (the Stage 2 base-anchored call),
  3. run the deterministic pipeline (bg removal -> trim) on both,
  4. write the results to ``scripts/smoke_out/`` for eyeballing.

Usage (from the backend/ directory, with the venv active and .env configured):
    python ../scripts/smoke_generate.py "a knight with a sword"

Requires env: GOOGLE_APPLICATION_CREDENTIALS, GOOGLE_CLOUD_PROJECT
(see backend/.env). Exits non-zero with a clear message on any failure.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root or backend/ by putting backend/ on the path.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models import Style  # noqa: E402
from app.pipeline import background, trim  # noqa: E402
from app.services.gemini_client import build_default_client  # noqa: E402
from app.services.prompt_builder import frame_prompt  # noqa: E402


def main() -> int:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "a knight with a sword"
    out_dir = Path(__file__).resolve().parent / "smoke_out"
    out_dir.mkdir(exist_ok=True)

    try:
        client = build_default_client()
    except Exception as exc:  # noqa: BLE001
        print(f"[smoke] config/auth error: {exc}", file=sys.stderr)
        return 2

    print(f"[smoke] generating base sprite for: {prompt!r}")
    base_raw = client.generate(prompt, Style.PIXEL)
    base_raw.save(out_dir / "01_base_raw.png")

    base = trim.autocrop(background.remove(base_raw), padding=0)
    base.save(out_dir / "02_base_clean.png")
    print(f"[smoke] base sprite: {base.size}")

    edit_prompt = frame_prompt("walk", index=2, total=6)
    print(f"[smoke] editing into a walk frame: {edit_prompt!r}")
    frame_raw = client.edit(base, edit_prompt)
    frame_raw.save(out_dir / "03_frame_raw.png")

    frame = trim.autocrop(background.remove(frame_raw), padding=0)
    frame.save(out_dir / "04_frame_clean.png")
    print(f"[smoke] walk frame: {frame.size}")

    print(f"[smoke] OK — wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
