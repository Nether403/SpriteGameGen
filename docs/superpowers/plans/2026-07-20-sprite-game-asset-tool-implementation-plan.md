# AI Sprite & Game Asset Tool — Implementation Plan

**Date:** 2026-07-20
**Source spec:** [2026-07-20-sprite-game-asset-tool-design.md](../specs/2026-07-20-sprite-game-asset-tool-design.md)
**Approach:** TDD. Deterministic pipeline is tested exhaustively against committed fixtures; the single non-deterministic seam (Gemini) is mocked in CI and smoke-tested by hand.

---

## 0. Ground truth verified before planning

- **Gemini SDK shape (confirmed via `google-genai` docs, 2026-07-20).** There is **no** "Interactions API". Both generation and editing use one call:
  ```python
  from google import genai
  from google.genai import types

  # Vertex AI / Google Agent Platform mode (this project authenticates with a
  # service-account JSON, NOT an API key). Auth is via Application Default
  # Credentials: GOOGLE_APPLICATION_CREDENTIALS points at the service-account
  # JSON file. project + location come from config.
  client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

  # Text -> image
  resp = client.models.generate_content(
      model="gemini-3.1-flash-image",
      contents="a knight with a sword, pixel art",
      config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
  )

  # Base-anchored edit: prompt + reference image in the same contents list
  resp = client.models.generate_content(
      model="gemini-3.1-flash-image",
      contents=[
          "same character, now in walk pose, foot forward, frame 3 of 6",
          types.Part.from_bytes(data=base_png_bytes, mime_type="image/png"),
      ],
      config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
  )

  # Extract bytes
  for part in resp.candidates[0].content.parts:
      if part.inline_data:
          image_bytes = part.inline_data.data  # PNG bytes
  ```
  This shape is isolated to `gemini_client.py`; if the real model IDs differ at runtime, only that file and `config.py` change. The mocked tests validate our wrapper logic (request built correctly, bytes/errors parsed), not the SDK internals; `scripts/smoke_generate.py` catches live signature drift.

- **Auth model: Vertex AI via service account.** This project connects through Google Agent Platform (formerly Vertex AI) using the service-account JSON in the repo root — not a `GEMINI_API_KEY`. `config.py` exposes `GOOGLE_APPLICATION_CREDENTIALS` (path to the JSON), `GOOGLE_CLOUD_PROJECT`, and `GOOGLE_CLOUD_REGION` (default `us-central1`); a missing credentials file or project fails loudly at startup. Model IDs still live only in config.

- **Not a git repo.** Task 1 initializes git so the per-task commit workflow works.

- **Security note (do before any commit):** the `project-<id>.json` service-account key in the repo root must be git-ignored so it is never pushed. Task 1 adds it (and `*.json` credential patterns) to `.gitignore`. Local use of the key is fine.

---

## Conventions

- **Language/runtime:** Python 3.11+, `uv` or `pip` + `venv`. Node 20+ for frontend.
- **One task = one focused change + its tests + a commit.** Each task lists: files, the test written *first*, the implementation, and the verification command.
- **Pipeline purity:** every `pipeline/*` function is `Image -> Image` or `[Image] -> Image`. No network, no disk, no config reads. This is the primary test surface.
- **Dependency injection at the seams:** `rembg` and the Gemini SDK client are injected so tests substitute fakes.
- **Commit message prefix:** `feat:`, `test:`, `chore:` per task.

---

# STAGE 1 — Static sprite (shippable milestone, tasks 1–13)

## Task 1 — Repo scaffold, git, tooling

**Files:**
- `.gitignore` (Python + Node + `projects/` + `.env` + the service-account key: ignore `project-*.json` at repo root by name — **not** a blanket `*.json`, which would also ignore project `project.json` manifests and frontend config)
- `backend/pyproject.toml` (deps: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pillow`, `numpy`, `rembg`, `google-genai`, `python-multipart`; dev: `pytest`, `pytest-asyncio`, `httpx`)
- `backend/app/__init__.py` + empty package dirs (`routes/`, `services/`, `pipeline/`, `storage/`, `tests/`, `tests/fixtures/`)
- `backend/.env.example` (`GOOGLE_APPLICATION_CREDENTIALS=../project-<id>.json`, `GOOGLE_CLOUD_PROJECT=`, `GOOGLE_CLOUD_REGION=us-central1`, `GEMINI_MODEL_GENERATE=gemini-3.1-flash-image`, `GEMINI_MODEL_EDIT=gemini-3.1-flash-image`, `PROJECTS_DIR=./projects`)
- `README.md` (run instructions for both servers)

**Steps:** `git init`; create structure; `pip install -e ".[dev]"`; confirm `pytest` collects 0 tests without error.
**Verify:** `cd backend && pytest -q` exits clean. `git status` shows the key file ignored.
**Commit:** `chore: scaffold backend project structure and tooling`

## Task 2 — Config module

**Test first** (`tests/test_config.py`): `get_settings()` reads env; raises a clear `RuntimeError` at import/startup if the service-account credentials file is missing/unreadable or `GOOGLE_CLOUD_PROJECT` is unset (fail loud, not mid-request); model IDs and region default correctly and are overridable via env.
**Impl** (`app/config.py`): pydantic `Settings` (pydantic-settings) with `google_application_credentials` (path, validated to exist), `google_cloud_project`, `google_cloud_region` (default `us-central1`), `gemini_model_generate`, `gemini_model_edit`, `projects_dir`, upload size cap. `get_settings()` cached.
**Verify:** `pytest tests/test_config.py -q`
**Commit:** `feat: config module with fail-loud API key validation`

## Task 3 — Domain models

**Test first** (`tests/test_models.py`): construct/validate `Style` (`pixel|hires`), `FrameStatus` (`ok|failed`), `Frame`, `Project`, `ExportOptions` (grid auto/explicit, padding>=0, format `json|xml`); bad values rejected.
**Impl** (`app/models.py`): pydantic v2 models exactly as spec §3 lists (`Project, Frame, ExportOptions, Style`).
**Verify:** `pytest tests/test_models.py -q`
**Commit:** `feat: pydantic domain models`

## Task 4 — `pipeline/trim.py` (autocrop + shared bbox)

**Test first** (`tests/test_trim.py`, with generated fixture PNGs — a small RGBA with known transparent margins):
- `content_bbox(img) -> (l,t,r,b)` finds the alpha bounding box; raises `EmptyImageError` on fully-transparent input.
- `autocrop(img, padding) -> Image` crops to content + uniform padding; output size math is exact and asserted.
- `shared_bbox([imgs]) -> bbox` returns one box covering all frames.
- `align_to_bbox([imgs], bbox, padding) -> [imgs]` yields identically-sized frames (anti-jitter). Assert all outputs equal size.
**Impl:** pure NumPy on the alpha channel. Typed exceptions (`EmptyImageError`, `DegenerateBBoxError`).
**Verify:** `pytest tests/test_trim.py -q`
**Commit:** `feat: trim pipeline with shared-bbox frame alignment`

## Task 5 — `pipeline/pixelate.py`

**Test first** (`tests/test_pixelate.py`): `quantize(img, colors, downscale) -> Image` reduces the distinct-color count to `<= colors`, downscales by integer factor then nearest-neighbor upscales back (crisp pixels), preserves alpha. Deterministic: same input -> byte-identical output (assert twice).
**Impl:** Pillow `quantize`/`convert("P", ...)` + nearest resize; keep alpha via a mask.
**Verify:** `pytest tests/test_pixelate.py -q`
**Commit:** `feat: pixel-art quantize + downscale pipeline`

## Task 6 — `pipeline/background.py` (injected rembg)

**Test first** (`tests/test_background.py`): `remove(img, *, remover=...) -> RGBA Image` calls the injected remover and guarantees RGBA output; a fake remover returns a known mask and the test asserts the result is RGBA with expected alpha. No real rembg model load in unit tests.
**Impl:** thin wrapper; default `remover` lazily builds a rembg session, but the parameter allows substitution.
**Verify:** `pytest tests/test_background.py -q`
**Commit:** `feat: background removal wrapper with injectable remover`

## Task 7 — `pipeline/packer.py`

**Test first** (`tests/test_packer.py`): given 6 known frames, `pack(frames, cols=None, padding) -> (sheet_img, layout)` where `layout` is a list of `{index, x, y, w, h}`. Assert grid dims (e.g. 6 frames -> 3×2 or configured cols), each frame's pixel offset, and sheet total size. Deterministic.
**Impl:** compute grid (auto near-square when `cols=None`), paste onto a transparent sheet at padded offsets, return sheet + layout dicts (lightweight; not pydantic).
**Verify:** `pytest tests/test_packer.py -q`
**Commit:** `feat: sprite-sheet packer with layout metadata`

## Task 8 — `pipeline/atlas.py`

**Test first** (`tests/test_atlas.py`): `write_atlas(layout, sheet_size, fmt) -> str` produces JSON compared against a committed **golden file** (`tests/fixtures/atlas_golden.json`) and a valid XML variant. Byte-stable key order.
**Impl:** serialize layout to JSON (sorted keys) and a simple TexturePacker-ish XML.
**Verify:** `pytest tests/test_atlas.py -q`
**Commit:** `feat: atlas metadata writer (JSON/XML) with golden test`

## Task 9 — `storage/project_store.py`

**Test first** (`tests/test_project_store.py`, using `tmp_path`): `create() -> project_id` makes `projects/<uuid>/`; `save_image(pid, name, img)`, `load_image`, `write_manifest(pid, Project)`, `read_manifest`, `list_projects`, `delete_project`. Round-trip a manifest and a PNG.
**Impl:** filesystem only; manifest is `project.json` via pydantic `.model_dump_json()`.
**Verify:** `pytest tests/test_project_store.py -q`
**Commit:** `feat: filesystem project store + manifest`

## Task 10 — `services/prompt_builder.py`

**Test first** (`tests/test_prompt_builder.py`): `build_generate_prompt(desc, style)` injects style directives (pixel vs hires); `list_presets()` returns the action table; `frame_prompt(action, i, total)` renders the per-frame template (used in Stage 2). Table-driven; adding a preset = adding a row (assert presets come from data, not branches).
**Impl:** `app/services/prompt_builder.py` with a `PRESETS` dict/table and pure string builders.
**Verify:** `pytest tests/test_prompt_builder.py -q`
**Commit:** `feat: prompt builder with style directives and preset table`

## Task 11 — `services/gemini_client.py` (mocked SDK)

**Test first** (`tests/test_gemini_client.py`): inject a fake SDK client.
- `generate(prompt, style, reference=None) -> PIL.Image`: asserts `generate_content` called with the configured **generate** model, `response_modalities=["IMAGE"]`, and reference image appended to `contents` when provided; parses `inline_data.data` -> Image.
- `edit(base_img, prompt) -> PIL.Image`: asserts the **edit** model is used and the base image is passed as a `Part` every call.
- Error mapping: transient errors retried with bounded backoff (patch sleep); safety refusal -> `SafetyBlockedError`; hard timeout enforced; malformed/empty response -> typed error.
**Impl:** `GeminiClient` taking an injected `client` (defaults to `genai.Client(vertexai=True, project=..., location=...)` built from config); uses `types.Part.from_bytes`; the retry/backoff/timeout/error-classification logic lives here and nowhere else.
**Verify:** `pytest tests/test_gemini_client.py -q`
**Commit:** `feat: Gemini client wrapper with retry/error handling (mocked tests)`

## Task 12 — Stage 1 routes: `/generate` + `/export`, app wiring

**Test first** (`tests/test_routes_stage1.py`, `httpx.AsyncClient` + FastAPI app, Gemini client dependency overridden with a fake returning a fixture PNG):
- `POST /generate` (prompt + style [+ optional upload]) -> runs `gemini.generate` then `background.remove -> trim.autocrop -> (pixelate if pixel)`, saves via store, returns `{project_id, sprite_url}`. Assert the saved sprite is RGBA and trimmed.
- `POST /export` single-frame -> `packer(1×1) -> atlas.write` -> returns/download `sprite.png` + `sprite.json`.
- Validation: oversized upload -> 4xx; missing key already fails at startup.
**Impl:** `app/routes/generate.py`, `app/routes/export.py`, `app/routes/projects.py` (GET list/delete), `app/main.py` (route wiring + CORS for `localhost:5173`). Gemini client provided via FastAPI dependency for override.
**Verify:** `pytest tests/test_routes_stage1.py -q` then full `pytest -q`.
**Commit:** `feat: Stage 1 /generate and /export endpoints`

## Task 13 — Frontend Stage 1

**Files:** `frontend/` Vite React-TS scaffold; `src/api/client.ts` (typed wrappers for `/generate`, `/export`, projects); `src/state/project.ts` (Zustand); `src/components/GeneratePanel.tsx` (prompt, upload, pixel/hires toggle), `src/components/ExportPanel.tsx` (format + download); `src/App.tsx` (Generate → Export layout for now).
**Test:** one Vitest component test for `client.ts` request shaping (mock fetch) — light per spec §6.
**Verify:** `npm run build` succeeds; manual: `uvicorn` + `npm run dev`, generate a sprite end-to-end with the fake key path documented, export downloads two files.
**Commit:** `feat: Stage 1 frontend — generate + export`

> **Milestone: Stage 1 complete and usable** — describe → clean sprite → export.

---

# STAGE 2 — Animation (the moat, tasks 14–20)

## Task 14 — Frame status + animation models

**Test first:** extend `tests/test_models.py`: `Frame` carries `index`, `status (ok|failed)`, `url`; `AnimateRequest` (base project id, action, frames, fps) validated (frames within preset bounds).
**Impl:** extend `app/models.py`.
**Commit:** `feat: animation request + frame status models`

## Task 15 — `/animate` route (base-anchored, partial-failure tolerant)

**Test first** (`tests/test_routes_animate.py`, fake Gemini client): for `action=walk, frames=6`, asserts `gemini.edit(base_sprite, frame_prompt(action,i,6))` is called **6 times with the original base sprite each time** (not chained). One frame's fake call raises -> that frame returns `status:"failed"` with a placeholder while the other 5 succeed (successful frames never lost). After generation, all frames go through `background.remove` then **shared-bbox** `align_to_bbox` (anti-jitter), saved to the project.
**Impl:** `app/routes/animate.py`; loop calls edit per frame, collects successes/failures, then applies shared-bbox trim across successful frames only.
**Verify:** `pytest tests/test_routes_animate.py -q`
**Commit:** `feat: /animate with base-anchored frames and shared-bbox alignment`

## Task 16 — Multi-frame export

**Test first:** extend `tests/test_routes_stage1.py` (or new `test_export_multi.py`): `POST /export` with N frames -> `packer.pack(frames, grid, padding)` sheet + `atlas.write` with per-frame layout; grid/padding options honored; JSON and XML both work.
**Impl:** generalize export route to N frames (packer/atlas already support it).
**Commit:** `feat: multi-frame sprite-sheet export`

## Task 17 — `FrameStrip` (regenerate/delete escape hatch)

**Files:** `src/components/FrameStrip.tsx` — thumbnails, per-frame delete + regenerate (calls a single-frame regenerate path; reuse `/animate` for one index or add `POST /animate/frame`). Failed frames show placeholder + regenerate button.
**Test:** component test for the regenerate/delete callbacks firing with the right index.
**Commit:** `feat: FrameStrip with per-frame regenerate/delete`

## Task 18 — `AnimationPlayer`

**Files:** `src/components/AnimationPlayer.tsx` — canvas loop over frames with FPS control.
**Test first (this one matters per spec §6):** Vitest unit test on the loop/timing math — frame index advances correctly for a given fps and elapsed time; loops.
**Commit:** `feat: AnimationPlayer canvas loop with FPS control`

## Task 19 — Wire Stage 2 into App

**Files:** `src/App.tsx` 3-step layout Generate → Animate → Export; action/frames/fps controls in an Animate panel; `state/project.ts` holds frames.
**Verify:** manual end-to-end walk cycle with fake then (optionally) real key.
**Commit:** `feat: 3-step Generate/Animate/Export flow`

## Task 20 — Polish + live smoke test

**Files:** `scripts/smoke_generate.py` — one real end-to-end Gemini call (generate + one edit), run manually, kept out of the pytest suite; export-format finalization (JSON/XML), grid/padding UI; README run + smoke instructions.
**Verify:** `pytest -q` all green (no network); run smoke script manually with a real key to confirm live integration and SDK signature.
**Commit:** `feat: live smoke script + export polish`

> **Milestone: Stage 2 complete** — animated sprite → sheet + atlas, with manual regenerate cleanup.

---

## Test/verify summary

| Layer | How tested | Runs in CI? |
|---|---|---|
| `pipeline/*` | pure unit tests vs committed fixtures + golden atlas | yes (fast, free, deterministic) |
| `gemini_client` | mocked SDK — request built + response/errors parsed | yes |
| routes | FastAPI + `httpx`, Gemini dep overridden with fake | yes |
| frontend | Vitest: `client.ts` shaping + AnimationPlayer loop math | yes (light) |
| live integration | `scripts/smoke_generate.py` | no — manual only |

## Risks / watch-items

1. **Model IDs may differ at runtime.** `gemini-3.1-flash-image` is per the spec; if the live API rejects it, change only `config.py`. Smoke test surfaces this immediately.
2. **rembg model download** is heavy on first run — keep it out of unit tests (injected fake) and note the first-call latency in README.
3. **Gemini frame consistency is imperfect** — the regenerate-per-frame hatch (Task 17) is the honest mitigation, per spec §4.
4. **Service-account key in repo** — safe as long as the repo is never pushed; `.gitignore` covers `project-*.json` so an accidental push won't include it (Task 1).
