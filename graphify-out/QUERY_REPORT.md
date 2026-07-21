# SpriteGameGen — Graph Query Report

Generated from `graphify-out/graph.json` (541 nodes, 976 edges, 31 communities).

**Method:** BFS traversal via `graphify query`, shortest-path via `graphify path`, node inspection via `graphify explain`, and manual verification of INFERRED edges against source files.

---

## Executive Summary

SpriteGameGen is organized around a **filesystem-backed `ProjectStore`** as the persistence hub and **FastAPI dependency injection** (`get_store`, `get_gemini_client`) as the wiring layer. Every major API route — generate, animate, export, frame edit/delete — reads and writes projects through `ProjectStore`. That architectural choice makes `ProjectStore` the graph's highest-betweenness bridge (0.109), connecting config/deps, all route handlers, domain models, and test fixtures.

Three cross-cutting error/type nodes — `EmptyImageError`, `RegenerateFrameRequest`, and the Gemini/Style cluster — sit at the boundaries between the **deterministic image pipeline** (trim, pixelate, pack) and the **AI + API layers**. Most INFERRED edges are **directionally correct at the module/route level** but **over-connect at the Pydantic model level** (e.g. `DeleteFrameRequest` linked to `Style` even though the request body has no `style` field).

---

## Query 1 — Why does `ProjectStore` bridge so many communities?

**Expanded tokens:** `project store config animate generate export frame manifest`

**Graph finding:** `ProjectStore` has degree 34 — the highest in the graph. Shortest path to App Config: `ProjectStore ←references— get_store()` (1 hop, EXTRACTED).

### Structural explanation

`ProjectStore` is the **single persistence abstraction** for the entire app:

| Community | Connection | Mechanism | Confidence |
|-----------|------------|-----------|------------|
| App Config and Deps | `_default_store()`, `get_store()` | `deps.py` constructs `ProjectStore(root=settings.projects_dir)` | EXTRACTED |
| Generate Route API | `generate()` | `Depends(get_store)` — create project, save sprite, write manifest | EXTRACTED |
| Animate Route API | `animate()`, `regenerate_frame()`, `delete_frame()` | All three inject `ProjectStore` via `get_store` | EXTRACTED |
| Export Route Models | `export()` | Reads manifest + loads frame images from store | EXTRACTED |
| Frame Domain Models | `Project`, `Frame` | Store serializes/deserializes `Project` manifest | EXTRACTED (store↔Project), INFERRED (store↔Frame) |
| Project Manifest Model | `Project` | `read_manifest` / `write_manifest` operate on `Project` | EXTRACTED |
| Animate/Export/Stage1 Tests | `app_and_store()`, `_make()`, `store()` | Tests override `get_store` with tmp-path `ProjectStore` | INFERRED |

### Key path (Generate → Store → Manifest)

```
get_store() --references [EXTRACTED]--> ProjectStore
generate() --references [EXTRACTED]--> ProjectStore
generate() --calls--> store.create(), store.save_image(), store.write_manifest()
ProjectStore --uses [INFERRED]--> Project (models.py)
```

### Source evidence

- `backend/app/deps.py` L17–28: `_default_store()` returns `ProjectStore`
- `backend/app/routes/generate.py` L37–38: injects both `GeminiClient` and `ProjectStore`
- `backend/app/routes/animate.py` L45–46, L162–163, L238: all animate endpoints inject `ProjectStore`
- `backend/app/routes/export.py` L27: export injects `ProjectStore`
- `backend/app/storage/project_store.py` L16: imports `Project` from `app.models`

**Verdict:** The bridge is **real and intentional**. `ProjectStore` is the filesystem spine connecting config → routes → domain → tests. The graph correctly surfaces the hub-and-spoke architecture from the design spec ("Filesystem Project Storage").

---

## Query 2 — Why does `EmptyImageError` connect Image Trim to Frame Domain Models?

**Expanded tokens:** `empty image error trim frame domain`

**Graph finding:** Shortest path `EmptyImageError ←uses— RegenerateFrameRequest —uses→ Frame` (2 hops, both INFERRED).

### Structural explanation

`EmptyImageError` is defined in the trim pipeline (`backend/app/pipeline/trim.py` L15) and raised when an image has no opaque pixels. It connects to frame domain models **indirectly through the animate routes**, not through the `Frame` Pydantic model itself:

1. **`animate()` batch path** (L85–90): After generating frames, `trim.shared_bbox()` may raise `EmptyImageError`. Caught → all frames marked `FrameStatus.FAILED` → persisted as `Frame` objects with `url=None`.
2. **`regenerate_frame()` path** (L204): Catches `(GeminiError, SafetyBlockedError, EmptyImageError, DegenerateBBoxError)` → sets `FrameStatus.FAILED`.

So the bridge is: **trim pipeline exception → route error handling → Frame status in manifest**.

### EXTRACTED vs INFERRED

| Edge | Status | Verdict |
|------|--------|---------|
| `content_bbox()` → raises `EmptyImageError` | EXTRACTED | Correct |
| `shared_bbox()` → catches `EmptyImageError` | EXTRACTED | Correct |
| `RegenerateFrameRequest` → uses `EmptyImageError` | INFERRED | **Correct at route level** — `regenerate_frame()` catches it |
| `DeleteFrameRequest` → uses `EmptyImageError` | INFERRED | **Incorrect** — `delete_frame()` never references trim or this exception |
| `Frame` → uses `EmptyImageError` | INFERRED | **Indirect only** — Frame model has no error field; connection is via route logic |

**Verdict:** The cross-community link is **real for animate/regenerate flows** but **overstated for delete_frame and the Frame model**. The graph correctly identifies trim→frame coupling for partial-failure handling; one spurious edge to `DeleteFrameRequest` should be treated as noise.

---

## Query 3 — Why does `RegenerateFrameRequest` span so many communities?

**Expanded tokens:** `regenerate frame request gemini trim animate export`

**Graph finding:** Shortest path to `GeminiClient`: `RegenerateFrameRequest —uses [INFERRED]→ GeminiClient` (1 hop).

### What `RegenerateFrameRequest` actually is

A minimal Pydantic body (`project_id`, `index`) at `animate.py` L126–134. The **cross-community span comes from its handler** `regenerate_frame()`, not from the request schema.

### Handler dependency chain

```
RegenerateFrameRequest
  └─ regenerate_frame() [animate.py L159]
       ├─ ProjectStore (read manifest, load base/sibling frames, save result)
       ├─ GeminiClient.edit() (AI frame generation)
       ├─ background.remove() (pipeline)
       ├─ trim.autocrop(), _fit_to_size() (trim pipeline)
       ├─ pixelate.quantize() if project.style is Style.PIXEL
       ├─ catches: GeminiError, SafetyBlockedError, EmptyImageError, DegenerateBBoxError
       └─ returns: Frame (domain model)
```

### Community crossings

| Community | Node | Role in regenerate flow |
|-----------|------|-------------------------|
| Frame Domain Models | `Frame`, `FrameStatus` | Return type + manifest update |
| Gemini AI Client | `GeminiClient`, `GeminiError`, `SafetyBlockedError` | AI edit + error handling |
| Image Trim Pipeline | `EmptyImageError`, `DegenerateBBoxError`, trim funcs | Post-process + failure detection |
| App Config and Deps | `get_store`, `get_gemini_client` | DI wiring |
| Domain Model Validation | `Style` (via `project.style`) | Pixel vs hires post-processing |
| Animate Route API | `regenerate_frame()`, `animate.py` | Route container |

**Verdict:** **Fully correct.** `RegenerateFrameRequest` is the HTTP entry point for the most cross-cutting operation in the codebase — single-frame regeneration touches AI, storage, trim, pixelate, and domain models in one handler. High betweenness (0.069) is expected.

---

## Query 4 — Are `ProjectStore`'s 11 INFERRED edges correct?

| Edge | Verdict | Notes |
|------|---------|-------|
| `ProjectStore` → uses `Project` | ✅ Correct | Direct import in `project_store.py` |
| `RegenerateFrameRequest` → uses `ProjectStore` | ✅ Correct | `Depends(get_store)` in `regenerate_frame()` |
| `DeleteFrameRequest` → uses `ProjectStore` | ✅ Correct | `Depends(get_store)` in `delete_frame()` |
| `ExportRequest` → uses `ProjectStore` | ✅ Correct | `Depends(get_store)` in `export()` |
| `app_and_store()` → calls `ProjectStore` | ✅ Correct | Test fixture constructs `ProjectStore(tmp_path)` |
| `store()` → calls `ProjectStore` | ✅ Correct | `test_project_store.py` fixture |
| `_make()` → calls `ProjectStore` | ✅ Correct | `test_routes_animate.py` helper |
| `FakeGemini` → uses `ProjectStore` (×3) | ⚠️ Indirect | Co-occurrence in test helpers; FakeGemini doesn't call store directly |

**Summary:** 8/11 clearly correct; 3 are test-fixture co-occurrence (harmless, not structural calls).

---

## Query 5 — Are `GeminiClient`'s 12 INFERRED edges correct?

| Edge | Verdict | Notes |
|------|---------|-------|
| `GeminiClient` → uses `Style` | ✅ Correct | `generate(prompt, style: Style, ...)` in `gemini_client.py` L71 |
| `RegenerateFrameRequest` → uses `GeminiClient` | ✅ Correct | Route injects client |
| `DeleteFrameRequest` → uses `GeminiClient` | ❌ Incorrect | `delete_frame()` has no Gemini dependency |
| `_Candidate`, `_Content`, `FakeSDK`, etc. → uses `GeminiClient` | ⚠️ Test-only | Test doubles in `test_gemini_client.py`; not production edges |
| `_make_client()` → calls `GeminiClient` | ✅ Correct | Test helper |

**Summary:** 4/12 are production-correct; 1 is wrong (`DeleteFrameRequest`); 7 are test-module co-occurrence.

---

## Query 6 — Are `Style`'s 16 INFERRED edges correct?

| Edge | Verdict | Notes |
|------|---------|-------|
| `GeminiClient` → uses `Style` | ✅ Correct | Typed parameter on `generate()` |
| `DeleteFrameRequest` → uses `Style` | ❌ Incorrect | Request model has no style field |
| `RegenerateFrameRequest` → uses `Style` | ⚠️ Indirect | Style read from `project.style` in handler, not request body |
| `GeminiError`, `GeminiTimeoutError`, `SafetyBlockedError` → uses `Style` | ❌ Incorrect | Exception classes don't reference Style |
| Test fakes → uses `Style` | ⚠️ Partial | `FakeGemini.generate()` accepts style param |
| `test_style_enum_values()` → calls `Style` | ✅ Correct | Direct enum test |

**Summary:** 2 clearly correct; 3 indirect/plausible; 11 are over-connected via route-module co-location or test co-occurrence.

---

## Query 7 — Are `GeminiError`'s 13 INFERRED edges correct?

| Edge | Verdict | Notes |
|------|---------|-------|
| `GeminiError` → uses `Style` | ❌ Incorrect | Exception class has no Style dependency |
| `RegenerateFrameRequest` → uses `GeminiError` | ✅ Correct | Caught in `regenerate_frame()` L204 |
| `DeleteFrameRequest` → uses `GeminiError` | ❌ Incorrect | Not referenced in delete handler |
| Test fakes → uses `GeminiError` | ⚠️ Test-only | `FakeGemini.edit()` raises `GeminiError`; test co-occurrence |
| `GeminiError` inheritance chain | ✅ EXTRACTED | `GeminiTimeoutError`, `SafetyBlockedError` subclass it |

**Summary:** 2 production-correct; 2 incorrect spurious links; 9 test/co-location noise.

---

## Architecture Insights

### 1. Hub-and-spoke persistence
Everything flows through `ProjectStore` + DI. This matches the design spec's "Filesystem Project Storage" and "Seam Dependency Injection" decisions (Community 6 — Design Spec and Plan).

### 2. Two-stage pipeline with shared post-processing
Generate (Stage 1) and Animate (Stage 2) share: `GeminiClient` → `background.remove` → `trim` → optional `pixelate.quantize`. The graph's "Deterministic Python Pipeline ↔ Pipeline Layer" surprising connection (README ↔ spec) reflects this.

### 3. Partial-failure tolerance creates cross-layer edges
The spec's "Partial Animation Failure Tolerance" decision manifests as exception-handling edges from trim (`EmptyImageError`) and Gemini (`GeminiError`, `SafetyBlockedError`) into `FrameStatus.FAILED`. This is why error types bridge pipeline and domain communities.

### 4. INFERRED edge quality
INFERRED edges are **strongest at route/handler level** (correct DI, catch blocks, imports) and **weakest at request-model level** (linking `DeleteFrameRequest` to `Style`, `GeminiError`, `EmptyImageError` because they share `animate.py`).

---

## Graph Health Caveat

Build reported 179 dangling-endpoint edges. These do not affect the bridge-node analysis above (all cited nodes exist in source), but indicate some AST-extracted symbol references couldn't be resolved. Treat peripheral `calls`/`references` edges with lower confidence.

---

## Recommendations

1. **Trust EXTRACTED edges** for navigation; treat INFERRED edges on Pydantic request models as hints, not facts.
2. **Start exploration from god nodes:** `ProjectStore` → routes → pipeline → `GeminiClient`.
3. **For frame lifecycle questions**, trace through `animate.py` handlers rather than `RegenerateFrameRequest` / `DeleteFrameRequest` nodes alone.
4. **Re-run with `--directed`** if you need call-direction clarity (caller → callee).
5. **Set `GEMINI_API_KEY`** and re-run semantic extraction on docs for richer design-spec ↔ code linking.

---

## Follow-up Traces (sequential)

### Follow-up 1 — `generate` → `export` (Stage 1 sprite to sprite sheet)

**Query:** `graphify path "generate" "export"`

**Graph shortest path (2 hops):**
```
generate() --references [EXTRACTED]--> ProjectStore <--references [EXTRACTED]-- export()
```

The graph finds the **storage hub** only. The full user/data pipeline is longer:

```
POST /generate                    POST /animate (optional)              POST /export
─────────────────                 ────────────────────────              ──────────────
gemini.generate()                 gemini.edit() × N frames              read manifest
  → background.remove               → background.remove                     filter FrameStatus.OK
  → trim.autocrop                   → shared_bbox + align_to_bbox         load frame PNGs
  → pixelate (if PIXEL)             → pixelate (if PIXEL)                 packer.pack()
store.create()                    store.save_image(frame_i)             atlas.write_atlas()
store.save_image("sprite")        store.write_manifest()                store.save_image("sprite_sheet")
store.write_manifest()                                                  store.write_text(atlas)
  frames: [Frame(0, ok)]            frames: [Frame(0..N, ok|failed)]      skips failed frames
```

**Extended graph paths:**
- `generate → animate`: 2 hops via `ProjectStore`
- `animate → export`: 2 hops via `ProjectStore`

**Source evidence:**
- `generate.py` L79–89: creates project, saves `sprite.png`, writes manifest with single `Frame(index=0)`
- `test_export_multi.py` L60–68: integration test calls `/generate` → `/animate` → `/export`
- `export.py` L33–40: loads only `FrameStatus.OK` frames; Stage 1 single-frame projects use `"sprite"` filename, multi-frame use `"frame_{index}"`

**Stage 1-only export:** A project that never ran `/animate` still exports — one frame, name `"sprite"`. Multi-frame export requires `/animate` first.

**Verdict:** Graph correctly identifies `ProjectStore` as the join point; the operational pipeline is **generate → (animate) → export** with manifest + PNG assets as the handoff contract.

---

### Follow-up 2 — `FakeGemini` and test DI vs production

**Query:** `graphify explain "FakeGemini"`

**Graph node:** `backend/tests/test_export_multi.py` L19 (degree 6). Three separate `FakeGemini` classes exist in the repo (export_multi, routes_stage1, routes_animate) — graphify indexed one; all follow the same pattern.

**Production wiring (`deps.py`):**
```python
def get_store() -> ProjectStore:        return _default_store()
def get_gemini_client() -> GeminiClient: return _default_gemini()
```

**Test wiring (all three test modules):**
```python
app = create_app(remover=_fake_remover)
app.dependency_overrides[get_store] = lambda: store          # tmp_path ProjectStore
app.dependency_overrides[get_gemini_client] = lambda: fake   # FakeGemini instance
```

| Concern | Production | Test (FakeGemini) |
|---------|------------|-------------------|
| Store | Real `ProjectStore(projects_dir)` | `ProjectStore(tmp_path)` |
| AI client | `GeminiClient` (Vertex/Gemini SDK) | `FakeGemini` — returns synthetic RGBA sprites |
| Background removal | `rembg` (lazy) | `_fake_remover` — green-screen key |
| Network | Real API calls | Zero network |
| Failure injection | Real Gemini errors | `fail_on={indices}` in `test_routes_animate.py` |

**FakeGemini interface contract** (must match `GeminiClient` surface):
- `generate(prompt, style, reference=None) → Image` — used by `/generate`
- `edit(base_img, prompt) → Image` — used by `/animate`, `/animate/frame`

**Per-test-file specialization:**
| File | FakeGemini behavior |
|------|---------------------|
| `test_routes_stage1.py` | `generate()` only; `edit()` raises `NotImplementedError` |
| `test_routes_animate.py` | Both methods; `fail_on` set simulates `GeminiError` per frame index |
| `test_export_multi.py` | Both methods; always succeeds (end-to-end export test) |

**Verdict:** Tests mirror production **exactly at the DI seam** — same route handlers, same `ProjectStore` API, swapped implementations. The graph's INFERRED `FakeGemini → ProjectStore` edge reflects fixture co-location, not a direct call; the real link is `app.dependency_overrides[get_store]`.

---

### Follow-up 3 — Partial failure and `FrameStatus`

**Query:** `graphify query "partial failure frame status"` (90 nodes)

**Graph anchors:** `Frame`, `FrameStatus`, `Partial Animation Failure Tolerance` (design doc, Community 6)

**Design → code chain:**

| Layer | Artifact | Role |
|-------|----------|------|
| Spec/plan | `Partial Animation Failure Tolerance` | One bad frame must not abort the batch |
| Spec/plan | `Regenerate-Per-Frame Escape Hatch` | Recovery path for failed frames |
| Domain | `FrameStatus` enum (`ok` \| `failed`) | Persisted per frame in manifest |
| Domain | `Frame.url: str \| None` | `None` when failed |
| Route | `animate()` L71–77, L111 | Catch `GeminiError`/`SafetyBlockedError` per frame → `FAILED` |
| Route | `animate()` L88–90 | Catch `EmptyImageError`/`DegenerateBBoxError` on shared bbox → all fail |
| Route | `regenerate_frame()` L204–216 | Single-frame retry; same catch set |
| Route | `export()` L33 | **Only exports `FrameStatus.OK`** — failed frames excluded from sheet |
| Frontend | `FrameStrip.tsx` L51–55 | Placeholder + regenerate button for `status === "failed"` |
| Frontend | `AnimationPlayer.tsx` L18 | Playback filters `status === "ok" && url` |
| Tests | `test_animate_partial_failure_marks_frame_failed` | 1 of 4 frames fails; other 3 OK |
| Tests | `test_regenerate_failed_frame_recovers_it` | Failed frame → regenerate → `ok` |

**Failure flow (batch animate):**
```
for each frame index:
  try: gemini.edit → background.remove
  except GeminiError, SafetyBlockedError: mark index failed, continue

shared_bbox( successful frames ):
  try: align all to common box
  except EmptyImageError, DegenerateBBoxError: mark ALL successful indices failed

persist: Frame(index, url=None, status=FAILED) for failures
         Frame(index, url=/projects/.../frame_N.png, status=OK) for successes
```

**Export interaction:** If all frames fail → `export()` returns 422 `"project has no usable frames"`. Partial failure → sheet contains OK frames only; atlas frame count matches OK count.

**Verdict:** Partial failure is **fully implemented end-to-end** — spec concept → Pydantic model → route catch blocks → manifest persistence → UI placeholder → export filter → dedicated tests. The graph links design doc nodes to `RegenerateFrameRequest` and `FrameStatus` through semantic extraction; runtime coupling is through `animate.py` exception handling.

---

## Frontend Path Trace — GeneratePanel → AnimatePanel → ExportPanel

**Graph hub:** `useProjectStore` (degree 12, Community 1 — Frontend API Client) mirrors backend `ProjectStore` as the shared-state spine. `client.ts` (degree 27) is the typed fetch layer.

### Layout shell (`App.tsx`)

All three panels are **siblings** — no direct panel-to-panel calls:

```
App.tsx
  ├── GeneratePanel()     "1. Generate"
  ├── AnimatePanel()      "2. Animate"
  └── ExportPanel()       "3. Export"
```

**Graph paths between panels:**
| Path | Hops | Via |
|------|------|-----|
| GeneratePanel → AnimatePanel | 2 | `App.tsx` imports both |
| GeneratePanel → ExportPanel | 2 | `App.tsx` imports both |
| AnimatePanel → ExportPanel | 2 | `useProjectStore` (shared state) |

Runtime coupling is **state + API**, not component hierarchy.

### Shared state (`useProjectStore` — Zustand)

| Field | Set by | Cleared by |
|-------|--------|------------|
| `projectId`, `spriteUrl` | `setGenerated()` (GeneratePanel) | `reset()` |
| `style` | `setStyle()` (GeneratePanel radio) | — |
| `action`, `fps`, `frames` | `setAnimation()` (AnimatePanel, FrameStrip delete) | `setGenerated()` |
| `exportResult` | `setExport()` (ExportPanel) | `setGenerated()`, `setAnimation()` |
| single `frame` update | `setFrame()` (FrameStrip regenerate) | — |

**State lifecycle:**
```
[empty] ──generate──► projectId + spriteUrl
         ──animate──► + action, fps, frames[]     (clears exportResult)
         ──regenerate frame──► patches frames[i]
         ──export──► + exportResult               (sheet_url, atlas_url)
```

### Step 1 — GeneratePanel

**Graph:** `GeneratePanel() --calls--> useProjectStore`; imports `generate` from `client.ts`

**Flow:**
```
User prompt + style + optional reference file
  → generate(prompt, style, reference)     POST /generate (multipart FormData)
  → setGenerated(project_id, sprite_url)   stores id + preview URL
  → renders <img src={spriteUrl}>
```

**Gating:** None — always available.

**Backend handoff:** Creates project on server; frontend only stores `project_id` and relative `sprite_url`.

---

### Step 2 — AnimatePanel (+ sub-components)

**Graph:** `AnimatePanel() --calls--> useProjectStore`; imports `animate`, `listPresets` from `client.ts`

**On mount:**
```
listPresets()  →  GET /presets  →  populates action dropdown
```

**On "Generate animation":**
```
requires projectId (hint shown if missing)
  → animate(projectId, action, { frames })   POST /animate (JSON)
  → setAnimation(action, fps, frames)          clears exportResult
  → currentAction set → renders AnimationPlayer + FrameStrip
```

**Sub-components (only after successful animate):**

| Component | Role | API calls |
|-----------|------|-----------|
| `AnimationPlayer` | Canvas loop of OK frames at configurable FPS | none (reads `frames`, `fps` from store) |
| `FrameStrip` | Thumbnails + per-frame regenerate/delete | `regenerateFrame()`, `deleteFrame()` |

**AnimationPlayer filtering:**
```typescript
frames.filter(f => f.status === "ok" && f.url)  // skips failed frames in preview
```

**FrameStrip partial-failure UI:**
- `status === "ok"` → thumbnail image
- `status === "failed"` → placeholder + Regenerate button
- Regenerate → `POST /animate/frame` → `setFrame(frame)` (single frame patch)
- Delete → `DELETE /animate/frame` → `setAnimation(...)` (full frame list refresh)

**Graph:** `AnimationPlayer ← AnimatePanel ← FrameStrip` (AnimatePanel imports both)

---

### Step 3 — ExportPanel

**Graph:** `ExportPanel() --calls--> useProjectStore`; imports `exportProject` from `client.ts`

**Flow:**
```
requires projectId (hint shown if missing)
  → exportProject(projectId, format, { padding, cols })   POST /export (JSON)
  → setExport({ sheet_url, atlas_url })
  → download links for PNG sheet + JSON/XML atlas
```

**Gating:** Disabled when `!projectId`. Does **not** require animate — a Stage-1-only project (single sprite frame) can export immediately after generate.

---

### End-to-end frontend → backend map

```
GeneratePanel          AnimatePanel              ExportPanel
     │                      │                         │
     ▼                      ▼                         ▼
 generate()            animate()               exportProject()
 listPresets()     regenerateFrame()                  │
                   deleteFrame()                      │
     │                      │                         │
     ▼                      ▼                         ▼
 POST /generate        POST /animate              POST /export
                       GET  /presets
                       POST /animate/frame
                       DELETE /animate/frame
     │                      │                         │
     └────────── useProjectStore (projectId) ──────────┘
                           │
                    backend ProjectStore
```

### Frontend design patterns

1. **Zustand as DI mirror** — panels never pass props to each other; `useProjectStore` is the frontend equivalent of FastAPI `Depends(get_store)`.
2. **client.ts as boundary** — all HTTP shaping + `ApiError` handling centralized; panels only catch and display errors.
3. **Progressive disclosure** — animate preview/frame strip appear only after `setAnimation`; export links appear only after `setExport`.
4. **Optimistic state resets** — new generate clears animation + export; new animate clears export (stale sheet links avoided).
5. **Partial failure surfaced in FrameStrip** — backend `FrameStatus.failed` drives placeholder UI; regenerate closes the loop with spec §4 escape hatch.

**Verdict:** The frontend path is a linear **Generate → Animate → Export** wizard with a shared Zustand store and a thin fetch client. Graph Community 1 ("Frontend API Client") correctly clusters `client.ts`, panels, and `useProjectStore`. The meaningful runtime path is **panel → client.ts API fn → backend route → useProjectStore update**, not panel-to-panel imports.

---

## Shared-Bbox Anti-Jitter — Deep Dive

**Graph hub:** `shared_bbox()` and `align_to_bbox()` in Community 3 ("Image Trim Pipeline"), degree 12 / linked pair.

**Design spec (§4):** After all frames are generated, compute **one bounding box covering every frame** and trim them identically so the character does not jitter or resize between frames.

### The problem

Gemini edits each frame independently. Even with base-anchored editing, the opaque subject can land at slightly different positions/sizes per frame. If each frame is `autocrop()`'d individually (Stage 1 style), playback would show the sprite **shifting and scaling** frame-to-frame.

### Two trim modes in this codebase

| Function | Input | Output | Used where |
|----------|-------|--------|------------|
| `autocrop(img)` | single image | crop to *that* image's content bbox | `/generate` (Stage 1), `regenerate_frame` pre-fit |
| `shared_bbox([imgs])` + `align_to_bbox([imgs], box)` | frame batch | all frames cropped to **same** box → identical dimensions | `/animate` batch (Stage 2) |

### Algorithm (`trim.py`)

**Step 1 — `content_bbox(img)`** — scan alpha channel; return `(left, top, right, bottom)` of opaque pixels. Raises `EmptyImageError` if fully transparent.

**Step 2 — `shared_bbox(images)`** — union of all per-frame boxes:
```
left   = min(frame.left)
top    = min(frame.top)
right  = max(frame.right)
bottom = max(frame.bottom)
```
Skips empty frames when computing union; raises `EmptyImageError` if none have content.

**Step 3 — `align_to_bbox(images, box, padding)`** — crop **every** frame to the same `(left, top, right, bottom)`. All outputs share size `(right-left + 2×padding, bottom-top + 2×padding)`. Raises `DegenerateBBoxError` on zero-area box.

**Unit test proof** (`test_trim.py`):
- Three frames with blocks at different positions → shared box `(3, 2, 14, 12)`
- After `align_to_bbox(..., padding=1)` → `len({img.size for img in aligned}) == 1`

### Integration in `/animate` (`animate.py`)

```
Phase 1 (per frame, NO shared crop yet):
  gemini.edit(base) → background.remove() → store in cut_by_index
  (failures → failed set, skip)

Phase 2 (batch anti-jitter — only successful frames):
  ordered = [cut_by_index[i] for i in ok_indices]
  box = trim.shared_bbox(ordered)
  aligned = trim.align_to_bbox(ordered, box, padding=0)
  except EmptyImageError, DegenerateBBoxError → mark all ok_indices failed

Phase 3:
  optional pixelate.quantize() per frame if Style.PIXEL
  store.save_image(frame_N) — all OK frames now same pixel dimensions
```

**Why defer cropping to Phase 2:** You need all frames in memory before you can compute the union bbox. Cropping per-frame in Phase 1 would defeat anti-jitter.

### Regenerate path — different but equivalent goal

`regenerate_frame()` does **not** re-run `shared_bbox` on the whole batch. Instead:

1. `trim.autocrop(cut)` — trim the new frame to its own content
2. `_fit_to_size(cut, target_size)` — center on a transparent canvas matching a **sibling OK frame's size** (or base sprite trimmed size)

This preserves the shared dimensions established at batch animate time without recomputing the union across all frames.

### Test coverage

| Test | Level | Asserts |
|------|-------|---------|
| `test_shared_bbox_covers_all_frames` | unit | Union bbox math |
| `test_align_to_bbox_yields_identical_sizes` | unit | All outputs same size |
| `test_animate_frames_share_identical_size_antijitter` | integration | All OK PNGs on disk have identical `.size` |
| `test_regenerate_frame_replaces_single_frame` | integration | Regenerated frame matches sibling size |

### Frontend playback coupling

`AnimationPlayer` draws OK frames centered on a fixed canvas with `imageSmoothingEnabled = false`. Identical frame dimensions from shared-bbox alignment mean the character stays visually stable when `frameAt()` advances the loop.

**Verdict:** Anti-jitter is a **pure, deterministic trim pipeline** (`shared_bbox` → `align_to_bbox`) invoked once per animate batch. It implements design spec decision #2 and is explicitly **not** used for Stage 1 single-sprite generate.

---

## Vite Dev Proxy — Request Routing Map

**Graph:** `vite.config.ts` (Community 2) proxies to backend; `main.py` mounts routers + CORS for `localhost:5173`.

### Dev topology

```
Browser  http://localhost:5173
    │
    ▼
Vite dev server (:5173)
    │  proxy table (prefix match)
    ▼
FastAPI uvicorn (:8000)
    │
    ▼
ProjectStore (./projects/)
```

Frontend `client.ts` uses **same-origin relative URLs** (`fetch("/generate", ...)`) — no hardcoded `:8000` in app code.

### Proxy table (`frontend/vite.config.ts`)

| Vite proxy prefix | Target | Backend route(s) |
|-------------------|--------|------------------|
| `/generate` | `http://localhost:8000` | `POST /generate` (multipart) |
| `/animate` | `http://localhost:8000` | `POST /animate`, `POST /animate/frame`, `DELETE /animate/frame` |
| `/presets` | `http://localhost:8000` | `GET /presets` |
| `/export` | `http://localhost:8000` | `POST /export` |
| `/projects` | `http://localhost:8000` | `GET /projects`, `DELETE /projects/{id}`, `GET /projects/{id}/{filename}` |
| `/health` | `http://localhost:8000` | `GET /health` |

**Prefix matching:** A request to `/projects/abc123/sprite.png` matches the `/projects` proxy rule and forwards to FastAPI `assets.get_asset`.

### Backend route registry (`main.py`)

```python
app.include_router(generate.router)   # POST /generate
app.include_router(animate.router)    # POST /animate, GET /presets, POST|DELETE /animate/frame
app.include_router(export.router)     # POST /export
app.include_router(projects.router)   # GET /projects, DELETE /projects/{id}
app.include_router(assets.router)     # GET /projects/{id}/{filename}
# + GET /health inline
```

### Frontend API → proxy → backend (full map)

| `client.ts` function | HTTP | Proxied path | FastAPI handler |
|----------------------|------|--------------|-----------------|
| `generate()` | POST | `/generate` | `generate.generate` |
| `listPresets()` | GET | `/presets` | `animate.presets` |
| `animate()` | POST | `/animate` | `animate.animate` |
| `regenerateFrame()` | POST | `/animate/frame` | `animate.regenerate_frame` |
| `deleteFrame()` | DELETE | `/animate/frame` | `animate.delete_frame` |
| `exportProject()` | POST | `/export` | `export.export` |
| `listProjects()` | GET | `/projects` | `projects.list_projects` |
| `deleteProject()` | DELETE | `/projects/{id}` | `projects.delete_project` |
| `<img src={spriteUrl}>` | GET | `/projects/{id}/sprite.png` | `assets.get_asset` |
| frame thumbnails | GET | `/projects/{id}/frame_N.png` | `assets.get_asset` |
| export download links | GET | `/projects/{id}/sprite_sheet.png`, `sprite.json` | `assets.get_asset` |

### CORS (belt-and-suspenders)

`main.py` also allows origins `http://localhost:5173` and `http://127.0.0.1:5173`. With the Vite proxy, browser requests are same-origin and CORS is not hit in normal dev. CORS matters if the frontend ever calls `:8000` directly.

### Production note

The proxy exists **only in Vite dev**. Production build (`npm run build`) serves static assets; you must either:
- serve the SPA behind a reverse proxy that forwards API paths to FastAPI, or
- configure the built frontend to call an absolute API base URL (not currently in `client.ts` — dev assumes proxy).

**Verdict:** Dev setup is **dual-process**: `uvicorn` on `:8000` + Vite on `:5173`. Six proxy prefixes cover every `client.ts` endpoint and all asset URLs returned in API responses. README documents this as "With both backend and frontend running, open http://localhost:5173."
