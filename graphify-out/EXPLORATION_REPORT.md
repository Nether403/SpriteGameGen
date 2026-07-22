# SpriteGameGen Graph Exploration Report

**Date:** 2026-07-22  
**Graph version:** 1,581 nodes · 4,737 edges · 110 communities  
**Update delta:** +727 nodes, +2,614 edges (123 files re-extracted)  
**Graph health:** OK — no dangling, missing, or collapsed edges

---

## Executive Summary

The updated graph reveals SpriteGameGen as a **three-layer local-first architecture**:

1. **Persistence layer** — `ProjectStore` (filesystem manifest V2, atomic writes, per-project locks)
2. **Domain layer** — `SpriteService` (generate → animate → export → bundle; partial-failure tolerant)
3. **Transport layer** — FastAPI routes + MCP `AppContext`, both wired through `deps.py`

The graph's highest-value insight is that **bridge nodes are real architectural seams, not extraction noise** — but **enum over-connection** (`Direction`, `ViewMode`, `Style` → 75+ INFERRED edges each) is genuine graph noise that should be filtered in future queries.

---

## 1. Graph Update Summary

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| Nodes | 947 | 1,581 | +634 net (+727 new, −93 removed) |
| Edges | 2,362 | 4,737 | +2,375 net |
| Communities | 48 | 110 | +62 |
| Files scanned | 72 | 195 | +123 changed |

**Major new surface area captured:**
- Character bundles + Godot 4.7 export profile
- ComfyUI loopback provider + workflow compiler
- Recipe/batch execution (`recipes.py`, `recipe_batch.py`)
- Action catalog (`actions.py`, `actions.v1.json`)
- CI governance (issue templates, license checker, dependabot)
- Provider registry (`provider_selection.py`, `ProviderRegistry`)
- Prior graphify query memories (8 session traces)

---

## 2. God Nodes (Core Abstractions)

| Rank | Node | Edges | Role |
|------|------|-------|------|
| 1 | `ProjectStore` | 126 | Filesystem persistence hub |
| 2 | `SpriteService` | 104 | Framework-neutral domain core |
| 3 | `Project` | 82 | Canonical manifest model |
| 4 | `Direction` | 80 | Enum — **over-connected (graph noise)** |
| 5 | `ViewMode` | 78 | Enum — **over-connected (graph noise)** |
| 6 | `Style` | 76 | Enum — **over-connected (graph noise)** |
| 7 | `OperationControl` | 70 | Cancellation + progress reporting |
| 8 | `AnimateRequest` | 68 | Stage-2 input DTO |
| 9 | `ProviderCapability` | 68 | Provider feature matrix |
| 10 | `ImageProviderName` | 63 | Provider selection enum |

---

## 3. Recommended Questions — Traced Answers

### Q1: Why does `ProjectStore` bridge so many communities?

**Verdict: CORRECT — intentional persistence hub.**

`ProjectStore` (`backend/app/storage/project_store.py:56`) is the single filesystem authority for:
- Manifest read/write (V2, with V1 in-memory migration)
- Per-project file locks (`project_lock()`)
- Image asset I/O (`save_image`, `load_image`)
- Atomic writes via `_atomic_replace`

**Wiring paths:**
- **HTTP routes** → `get_store()` in `deps.py:63` → injected into `SpriteService`
- **MCP server** → `AppContext` holds store via `_default_service()` chain
- **Tests** → `app.dependency_overrides` swap fakes at `get_store` boundary

`ProjectStore` does not call business logic — every route, MCP tool, and test that touches persisted state must traverse it. High betweenness (0.066) is expected.

---

### Q2: Why does `DependencyMetadataError` bridge CI/Governance to Project Store?

**Verdict: PARTIALLY CORRECT — bridge is real but indirect.**

`DependencyMetadataError` (`scripts/check_dependency_licenses.py:117`) is raised when Python/npm license metadata cannot be audited safely. It inherits `ValueError` and is caught in `main()` to produce a sorted compliance report.

**Actual connection chain:**
```
CI workflow (ci.yml) → check_dependency_licenses.py → DependencyMetadataError
                     → test_dependency_licenses.py (unit tests)
```

The graph links it to `ProjectStore` via shared `ValueError` inheritance through `CharacterBundleError` and pipeline errors (`EmptyImageError`, `DegenerateBBoxError`). This is a **type-hierarchy artifact**, not a runtime dependency. The governance→storage bridge is **semantically misleading** in the graph; the real bridge is **CI → license audit script**.

---

### Q3: Why does `CharacterBundleError` bridge MCP to Project Store?

**Verdict: CORRECT — export errors propagate through the service stack.**

`CharacterBundleError` (`backend/app/character_bundle.py:56`) is raised during bundle validation/packing. The graph correctly shows paths through:
- `SpriteService` → `CharacterBundleResult`
- `MCPBundleResult` / `MCPExportResult` DTOs
- `ProjectStore` for reading clip frames and writing bundle ZIP

Bundle export is a **cross-cutting operation**: it reads persisted project state, runs deterministic packing, and returns via both HTTP and MCP adapters.

---

### Q4–Q7: Are INFERRED edges on `ProjectStore`, `SpriteService`, `Project`, `Direction` correct?

| Node | INFERRED edges | Verdict |
|------|----------------|---------|
| `ProjectStore` | 56 | **~70% correct** — real `store.load_image`/`_commit_project` deps; some BundleClip/BundleFrame links are type-co-occurrence |
| `SpriteService` | 67 | **~85% correct** — `animate()`, `regenerate_frame()`, `export_sheet()` calls are EXTRACTED; INFERRED links to MCP DTOs are structural |
| `Project` | 76 | **~60% correct** — model fields shared across DTOs create co-occurrence edges |
| `Direction` | 75 | **~20% meaningful** — enum appears in every request/DTO/MCP type; most INFERRED edges are **extraction noise** |

**Recommendation:** When querying, prefer `SpriteService`, `ProjectStore`, `GeminiClient` as start nodes (confirmed by 8 prior useful sessions in `LESSONS.md`). Avoid starting from `Direction`/`ViewMode`/`Style`.

---

## 4. Follow-Up Traces

### F1: `_edit_frame` → pose reference → provider

**Path (verified in source):**

```
regenerate_frame() / animate()
  → _request_frame_prompt() / _clip_frame_prompt()
  → _edit_frame()                          [sprite_service.py:837]
      → pose_reference.walk_pose_reference()  [if walk + side_scroller]
      → pose_reference.declarative_pose_reference()  [if guide_specs]
      → image_provider.edit(base, prompt, pose_reference=guide)
```

For `walk` + `SIDE_SCROLLER`, an 8-phase stick skeleton is generated and passed as `pose_reference` guide image. The prompt explicitly instructs the model to copy pose positions but not stick-figure style.

---

### F2: Partial failure concurrency in `animate()`

**Path (verified in source):**

```
animate() [sprite_service.py:413]
  → ThreadPoolExecutor(max_workers=min(provider.max_concurrency, total))
  → generate_frame(index) per frame (provider.edit only — concurrent)
  → process_result() serially (background removal + trim — NOT concurrent)
  → mark_failed(index, exc) on ImageProviderError / ImageSafetyBlockedError
  → shared_bbox alignment: if fails, ALL ok frames marked failed
  → saves Frame(status=OK|FAILED) per index
```

**Key invariant:** Concurrency is **only** on network-bound `provider.edit` calls. Post-processing is serial because native inference sessions are not thread-safe.

---

### F3: Export failed-frame gate + regenerate

**Path (verified in source):**

```
export_sheet() [sprite_service.py:917]
  → counts FrameStatus.FAILED among enabled frames
  → raises ProjectUnavailableError (HTTP 409) if any failed
  → packs only FrameStatus.OK enabled frames

regenerate_frame() [sprite_service.py:694]
  → reads persisted clip.action, view_mode, direction from project
  → rebuilds frame_prompt from clip metadata (body: project_id + index only)
  → calls _edit_frame() → saves new frame, sets status OK
```

**Recovery loop:** animate (partial fail) → user regenerates failed frames → export_sheet succeeds.

---

### F4: Character bundle → Godot export

**New communities:** Character Bundles, Version Contracts

- `sprite-character-bundle` V1 ZIP: `character.bundle.json` + `SHA256SUMS` + PNG frames
- `godot4_animatedsprite2d` profile with `import_character_bundle.gd`
- Export scope validation: `active`/`one` vs `all_enabled`
- Godot headless smoke gate required before claiming Godot support in releases

---

### F5: ComfyUI loopback boundary

**Locked architectural decision** (docs + plan + code aligned):

- Only `localhost`, `127.0.0.0/8`, `::1` permitted (`validate_loopback_url()`)
- HTTP proxies and redirects disabled
- Descriptor-bound workflows only — no caller-supplied node IDs/paths
- Safe cancellation: queued prompt IDs only, never global `/interrupt`
- Capability preflight rejects unsupported inputs rather than ignoring them

---

### F6: Provider registry (Gemini / Azure / ComfyUI)

```
deps.py: build_provider_registry()
  → ProviderRegistry(gemini, azure, comfyui)
  → SpriteService._require_provider_capabilities()
  → animate() checks EDIT + IDENTITY_REFERENCE + POSE_REFERENCE (walk) + SEED
```

Provider selection is capability-driven, not name-driven. `get_provider_availability()` exposes readiness without constructing clients.

---

## 5. Surprising Connections (Verified)

| Connection | Assessment |
|------------|------------|
| `Image Pipeline` ↔ `Deterministic Image Pipeline` | Same concept in bug template vs README — **valid** |
| `Local ComfyUI Provider` ↔ `ComfyUI loopback-only boundary` | Doc ↔ plan ↔ code — **valid, intentionally triple-documented** |
| `Hyperagent Not Listed` ↔ `MCP tools/list Audit Distinction` | AGENTS.md audit rule — **valid cross-doc link** |
| `Backend API` ↔ `Backend (FastAPI + ...)` | Template label vs README — **valid** |

---

## 6. Hyperedge Groups (Architectural Flows)

1. **Structured Issue Reporting Templates** — 5 GitHub issue templates form a governance bundle
2. **CI Verification Pipeline** — test, secrets, godot, doctor, smoke_mcp, license check jobs
3. **Provider Integration Safety** — credential safety, billing, deterministic tests, capability boundaries
4. **Character Bundle V1 Export Format** — bundle JSON + checksums + version contract
5. **Animate Frame Edit Pipeline** — frame_prompt → _edit_frame → walk_pose_reference → GeminiClient
6. **Independent Version Contracts** — manifest V2, bundle V1, action pack V1, recipe V1, batch state V1

---

## 7. Knowledge Gaps

- **~92+ isolated nodes** with ≤1 connection — mostly new concepts (recipe batch, action catalog, ComfyUI workflow compiler) not yet linked to routes
- **Enum over-connection** inflates `Direction`/`ViewMode`/`Style` centrality — filter in queries
- **Manifest migration** (`migrate_v1()`) under-connected to `ProjectStore` in semantic layer despite being critical
- **Frontend state** (`project.ts`) connected to backend models but thin edges to new bundle/export UI

---

## 8. Recommendations

### For development
1. **Treat `SpriteService` as the change boundary** — new features should extend service methods, not routes/MCP directly
2. **Export gates are strict** — always handle `ProjectUnavailableError` (409) in UI before calling export
3. **ComfyUI is sandboxed** — never relax loopback boundary; use descriptor bindings for new workflows
4. **Version contracts are independent** — bump format versions separately from package semver

### For graph hygiene
1. Filter enum nodes (`Direction`, `ViewMode`, `Style`) from betweenness rankings
2. Re-run `--update` after major feature merges (character bundles, ComfyUI added 634 nodes)
3. Prior sessions confirm: start queries at `SpriteService`, `ProjectStore`, `GeminiClient`

### For testing
1. Partial animation failure → regenerate → export is the critical user recovery path — ensure E2E coverage
2. Godot headless smoke is a release gate, not optional
3. License checker (`DependencyMetadataError`) must pass in CI before any release

---

## 9. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Transport Layer                           │
│  FastAPI Routes (/generate, /animate, /export, /projects)   │
│  MCP AppContext (stdio tools mirroring HTTP capabilities)    │
└──────────────────────────┬──────────────────────────────────┘
                           │ deps.py (get_store, get_provider_registry)
┌──────────────────────────▼──────────────────────────────────┐
│                    Domain Layer                                │
│  SpriteService                                               │
│    generate → animate → regenerate_frame → export_sheet      │
│    → export_character_bundle                                 │
│  ProviderRegistry (Gemini | Azure | ComfyUI)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ store.load/save, project_lock
┌──────────────────────────▼──────────────────────────────────┐
│                    Persistence Layer                           │
│  ProjectStore (manifest V2, atomic writes, per-project lock) │
│  Pipeline (trim, pixelate, packer, atlas, background)        │
└─────────────────────────────────────────────────────────────┘
```

---

*Generated from graphify query traversals against `graphify-out/graph.json` (2026-07-22).*
