# AI Sprite & Game Asset Tool — Design Spec

**Date:** 2026-07-20
**Status:** Approved design, ready for implementation planning
**Type:** Personal learning tool / MVP

---

## 1. Purpose & Scope

Build a locally-run web app that turns a text prompt (and optional reference image)
into a clean, engine-ready **animated sprite sheet**. The goal is learning: exercise
the full pipeline from AI image generation through deterministic asset production and
export, using the Gemini API for the hard generative work and real Python code for the
deterministic craft (background removal, pixel-art quantization, sprite-sheet packing,
atlas metadata).

**This is explicitly NOT:** a multi-tenant SaaS, a billing platform, a scalable cloud
service, or a competitor to AutoSprite/PixelLab. Those are noted as future expansion
paths only.

### Guiding decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Primary goal | Learning / personal tool | No billing, auth, or multi-tenant scaling |
| AI approach | Gemini API + local post-processing | Cheap AI where it's hard; real code where determinism matters |
| Core loop | Animated sprite → sheet, built in 2 stages | Motion is the "moat"; static alone is too small |
| Art style | Both pixel-art and hi-res, user-selectable | Differ mainly in one post-processing step |
| Tech stack | React (Vite) + Python (FastAPI) | Python owns the deterministic image work |
| Animation types | Small preset library | idle/walk/run reliable; attack/jump best-effort |

---

## 2. Architecture Overview

A two-tier local app with a hard line between the **AI layer** (non-deterministic,
Gemini) and the **pipeline layer** (deterministic, pure Python).

```
┌─────────────────┐     HTTP/JSON      ┌──────────────────────┐
│  React (Vite)   │ ◄────────────────► │  FastAPI (Python)    │
│  - upload/prompt │    + image blobs   │                      │
│  - style toggle  │                    │  ┌────────────────┐  │
│  - frame preview │                    │  │ Gen service    │──┼──► Gemini API
│  - anim player   │                    │  │ (Gemini calls) │  │  (3.1 Flash Image)
│  - export button │                    │  └────────────────┘  │
└─────────────────┘                     │  ┌────────────────┐  │
                                         │  │ Image pipeline │  │  (local, deterministic)
                                         │  │ - bg removal   │  │
                                         │  │ - quantize     │  │
                                         │  │ - trim/pad     │  │
                                         │  │ - sheet packer │  │
                                         │  │ - atlas writer │  │
                                         │  └────────────────┘  │
                                         │  ┌────────────────┐  │
                                         │  │ Storage (disk) │  │  ./projects/<id>/
                                         │  └────────────────┘  │
                                         └──────────────────────┘
```

**Core principle:** the pipeline layer never calls Gemini; it only transforms images.
It is a set of pure functions (`Image → Image`) testable with fixed input PNGs, giving
identical output every run. The one non-deterministic seam (Gemini) is isolated to a
single module.

**Storage:** plain filesystem, no database. Each project is a folder
`./projects/<uuid>/` containing the source image, generated frames, the packed sheet,
and a `project.json` manifest.

---

## 3. Components & Module Boundaries

### Backend (`/backend`)

```
app/
  main.py                 # FastAPI app, route wiring, CORS
  config.py               # env: GEMINI_API_KEY, model IDs (gen/edit), paths, defaults
  routes/
    generate.py           # POST /generate      (prompt/image → base sprite)
    animate.py            # POST /animate        (base sprite → N frames)
    export.py             # POST /export         (frames → sheet + atlas)
    projects.py           # GET/list/delete projects
  services/
    gemini_client.py      # ONLY file that talks to Gemini. Wraps SDK.
    prompt_builder.py     # style/action → structured prompt text
  pipeline/               # pure, deterministic, no network
    background.py         # rembg-based alpha cutout
    pixelate.py           # quantize + downscale (pixel-art mode only)
    trim.py               # autocrop to content + uniform padding
    packer.py             # frames → grid sprite sheet (numpy)
    atlas.py              # sheet layout → JSON/XML metadata
  storage/
    project_store.py      # create/read/write project folders + manifest
  models.py               # pydantic: Project, Frame, ExportOptions, Style
```

**Key boundaries:**
- `gemini_client.py` is the *only* module importing the Gemini SDK. Everything else
  receives PIL Images. Swapping AI provider later touches one file.
- `pipeline/*` functions are pure (`Image → Image` / `[Image] → Image`): no network,
  no I/O, no config reads. This is the primary test surface.
- `prompt_builder.py` isolates prompt engineering so iterating on prompts never touches
  API or pipeline code.

### Frontend (`/frontend`)

```
src/
  api/client.ts           # typed fetch wrappers for the 4 endpoints
  components/
    GeneratePanel.tsx     # prompt input, image upload, style toggle
    FrameStrip.tsx        # thumbnails of generated frames, regenerate/delete
    AnimationPlayer.tsx   # canvas loop preview w/ FPS control
    ExportPanel.tsx       # grid/padding/format options, download
  state/project.ts        # current project state (Zustand)
  App.tsx                 # 3-step layout: Generate → Animate → Export
```

The frontend is a thin client: it uploads images/params and renders results. All image
transformation happens server-side, keeping the interesting code in one language and
one test suite.

---

## 4. Data Flow & Staging

### Stage 1 — Static sprite (foundation milestone)

```
User: prompt "knight with sword" + style=pixel  [+ optional reference image]
  │
  ▼  POST /generate
prompt_builder → gemini_client.generate()  →  raw RGBA image (Gemini)
  │
  ▼  pipeline (deterministic)
background.remove()  →  trim.autocrop()  →  [if pixel] pixelate.quantize()
  │
  ▼
project_store.save()  →  returns { project_id, sprite_url }
  │
  ▼  POST /export  (single frame)
packer (1×1)  →  atlas.write()  →  sprite.png + sprite.json  →  download
```

At this point the tool is complete and usable: describe → clean sprite → export.
Stage 1 is a shippable milestone on its own.

### Stage 2 — Animation (the moat)

```
User: picks base sprite + action "walk", frames=6, fps=8
  │
  ▼  POST /animate
For each frame i:
  prompt_builder.frame_prompt(action, i, total)
  gemini_client.edit(base_sprite, frame_prompt)   ← image-editing mode; base
  │                                                  sprite passed every call
  ▼                                                  for identity anchoring
  pipeline: background.remove → trim (shared bbox!) → [pixelate]
  │
  ▼  frames[]  →  AnimationPlayer preview (loop in browser canvas)
  │
  ▼  POST /export
packer.pack(frames, grid, padding)  →  sheet.png
atlas.write(layout, format=json|xml)  →  sheet.json
  │
  ▼  download sheet.png + sheet.json
```

### Three consistency decisions (the hard part)

1. **Base-anchored editing, not free generation.** Every frame is generated by passing
   the *original base sprite* plus a per-frame prompt ("same character, now in walk
   pose, foot forward, frame 3 of 6"). Anchoring to one reference each call beats
   chaining frame→frame, which drifts.

2. **Shared bounding box.** After all frames are generated, the pipeline computes *one*
   bounding box covering every frame and trims them identically, so the character does
   not jitter or resize between frames. Deterministic and testable.

3. **Regenerate-per-frame escape hatch.** `FrameStrip` lets the user delete and
   regenerate a single bad frame. Since Gemini is not frame-perfect, this manual cleanup
   loop is the pragmatic, honest answer to the technology's limits.

### Preset actions

Reliable core: `idle` (2–4 frames), `walk` (6–8), `run` (6–8).
Best-effort (larger pose deltas, managed expectations): `attack`, `jump` (4–6).
All presets are rows in a table mapping `action → per-frame prompt templates`. Adding a
preset = adding rows, no new code. Attack/jump share the same code path as walk/idle;
only expectations differ.

---

## 5. Error Handling

**1. Gemini API failures** (rate limit, timeout, safety block, malformed response).
`gemini_client` wraps every call with bounded retries + exponential backoff for
transient errors, a distinct `SafetyBlockedError` for refusals (UI: "try rephrasing"),
and a hard timeout. Partial animation failures do not kill the batch — a failed frame
returns as `status: "failed"` and the UI shows a placeholder with a regenerate button.
Successful frames are never lost.

**2. Pipeline failures** (empty image after bg removal, degenerate bounding box,
unexpected mode). Pipeline functions validate input and raise typed exceptions with
clear messages. Because they are pure, any failure is reproducible from the saved input
PNG — debuggable offline without spending tokens.

**3. User/input errors** (missing API key, oversized upload, bad params). Validated at
the route boundary with pydantic; returned as 4xx with actionable messages. A missing
`GEMINI_API_KEY` fails loudly at startup, not mid-request.

---

## 6. Testing Strategy

Testing mirrors the deterministic/non-deterministic split.

- **Pipeline (bulk of tests):** pure unit tests with committed fixture PNGs.
  `test_packer` verifies a known 6-frame input produces expected grid dimensions and
  frame offsets; `test_atlas` compares JSON to a golden file; `test_trim` checks
  shared-bbox alignment. Fast, free, deterministic; run on every change.
- **Gemini client:** tested against a **mocked** SDK — assert the right request is built
  and responses/errors are parsed and handled correctly. No real API calls in CI.
- **Live smoke test:** `scripts/smoke_generate.py` makes one real end-to-end API call,
  run manually to verify live integration. Kept out of the automated suite so tests stay
  free and fast.
- **Frontend:** light — a couple of component tests for the animation player loop math
  and export option wiring. Not the focus.

Principle: everything deterministic is tested exhaustively and for free; the single
non-deterministic seam is mocked in CI and smoke-tested by hand.

---

## 7. Technology Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + Vite + TypeScript | Thin client |
| Frontend state | Zustand | Minimal, no Redux overhead |
| Backend | Python 3.11+ + FastAPI | Typed, async, auto API docs |
| AI generation | Gemini 3.1 Flash Image / `gemini-3.1-flash-image` (via `google-genai` SDK) | Text-to-image + image editing + character consistency; model ID configurable (see below) |
| Image ops | Pillow + NumPy | Quantization, packing, atlas |
| Background removal | rembg | Local, deterministic-enough cutout |
| Edge cleanup (optional) | OpenCV | Only if needed |
| Storage | Filesystem (`./projects/<uuid>/`) | No database for MVP |

**Note on stack tradeoff:** the two-language split means two dev servers to run and
slightly more deploy setup vs. an all-JS Next.js app. For a personal tool run locally
this is negligible, and Python's imaging ecosystem (Pillow/NumPy/rembg) is worth it.

### Model selection (configurable)

The model ID lives only in `config.py` and is read by `gemini_client.py`; no other
module knows which model is in use. Two config keys allow per-stage overrides:

| Config key | Default | Why |
|---|---|---|
| `GEMINI_MODEL_GENERATE` (Stage 1) | `gemini-3.1-flash-image` | Full Flash Image; can be swapped for `gemini-3.1-flash-lite-image` as a cost lever — Stage 1 is a single prompt with no reference chaining, so Lite's limits don't bite |
| `GEMINI_MODEL_EDIT` (Stage 2) | `gemini-3.1-flash-image` | **Must stay on full Flash Image.** Stage 2 uses base-anchored editing (original sprite passed as a reference on every frame call). Google documents Lite as *not optimized for multiple reference inputs or multi-turn sequential editing* — exactly our animation workload — so Lite would sabotage frame consistency |

Model options considered (Nano Banana lineup, per current Gemini API docs):
`gemini-3.1-flash-image` (workhorse, chosen), `gemini-3.1-flash-lite-image`
(cheapest/1K, Stage-1-only cost lever), `gemini-3-pro-image` (premium, overkill here),
`gemini-2.5-flash-image` (legacy, superseded).

---

## 8. Build Sequence

1. **Backend skeleton** — FastAPI app, config, project storage, models.
2. **Pipeline modules** — background, trim, pixelate, packer, atlas (pure, fully tested
   against fixtures). Buildable and testable *before any Gemini integration*.
3. **Gemini client** — generate + edit, with retry/error handling; mocked tests.
4. **Stage 1 wiring** — `/generate` + single-frame `/export` end to end.
5. **Frontend Stage 1** — GeneratePanel, style toggle, ExportPanel.
6. **Stage 2 backend** — `/animate`, preset table, shared-bbox trim, frame status model.
7. **Stage 2 frontend** — FrameStrip (regenerate/delete), AnimationPlayer.
8. **Polish** — export formats (JSON/XML), grid/padding options, smoke script.

Stage 1 (steps 1–5) is a complete, usable milestone. Stage 2 (steps 6–8) adds the moat.

---

## 9. Future Expansion (out of scope for MVP)

Noted only so the architecture doesn't preclude them: directional variants (4/8-way),
tilesets/maps, in-browser editing/inpainting, REST API + engine plugins, multi-user +
billing, provider swap (FLUX/SDXL + ComfyUI for higher control). The isolated
`gemini_client` and pure pipeline make a provider swap the least disruptive of these.
