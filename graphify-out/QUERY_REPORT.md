# SpriteGameGen — Graph Query Report

Generated from `graphify-out/graph.json` (**947** nodes, **2,362** edges, **48** communities) after the 2026-07-21 incremental update.

**Method:** Vocab-constrained BFS via `graphify query`, shortest-path via `graphify path`, node inspection via `graphify explain`, INFERRED-edge audit against `graph.json`, and manual verification against source files.

**Note:** Several high-traffic labels are duplicated across the graph (e.g. **7** `Style` nodes, **9** `ViewMode` nodes). Unless stated otherwise, analyses refer to the canonical backend domain nodes:

| Label | Canonical node ID | Degree | Community |
|-------|-------------------|--------|-----------|
| `ProjectStore` | `backend_app_storage_project_store_projectstore` | 77 | Projects API Routes |
| `SpriteService` | `backend_app_services_sprite_service_spriteservice` | 68 | MCP Server Core |
| `GeminiClient` | `backend_app_services_gemini_client_geminiclient` | 36 | Gemini Client |
| `ViewMode` | `backend_app_models_viewmode` | 53 | MCP Server Core |
| `Style` | `backend_app_models_style` | 50 | MCP Server Core |

---

## Executive Summary

SpriteGameGen’s knowledge graph is a **hub-and-spoke** architecture:

1. **`ProjectStore`** is the filesystem persistence hub (highest betweenness). HTTP routes inject it via `get_store()`; MCP constructs it inside `_default_service()`.
2. **`SpriteService`** is the framework-neutral application boundary. FastAPI routes and the MCP stdio server both call into it; it owns store + image provider + prompt enhancer.
3. **`GeminiClient`** is the Vertex AI image/prompt adapter, wired through deps and consumed by animate/generate routes and live-validation scripts.
4. **`ViewMode` / `Style`** are small domain enums that the AST/LLM merge **over-connects** with INFERRED `uses` edges to MCP DTOs, error types, and test fakes. The *architectural* story (they parameterize generation/animation) is real; many pairwise INFERRED edges are **not** direct code relationships.

**Overall verdict on INFERRED hubs:**

| Node | EXTRACTED | INFERRED | Verdict |
|------|-----------|----------|---------|
| `ProjectStore` | 37 | 40 | Bridge is real; ~half of INFERRED edges are module-level correct, ~half are DTO/error over-links |
| `SpriteService` | 22 | 46 | Bridge is real; route/MCP links correct; many model/error INFERRED edges are co-location inflation |
| `ViewMode` | 6 | 47 | Real as camera enum; most INFERRED neighbors are **incorrect as direct edges** |
| `Style` | 4 | 46 | Real as art-style enum; same over-connection pattern as `ViewMode` |

---

## Query 1 — Why does `ProjectStore` bridge so many communities?

**Original question:** Why does `ProjectStore` connect Projects API Routes to MCP Server Core, Deps And Settings, Animate Route Tests, Animate Routes, Stage1 Route Tests, Project Store Tests?

**Expanded tokens (from graph vocab):** `project store mcp deps settings animate routes frame`

**Graph finding:** Degree **77**. Own community: **Projects API Routes**. Cross-community edges:

| Target community | Edges | Mechanism |
|------------------|------:|-----------|
| MCP Server Core | 30 | `AppContext`, `_default_service()`, MCP* DTOs (mostly INFERRED `uses`) |
| Deps And Settings | 11 | `get_store()`, `_default_store()` **EXTRACTED**; test helpers INFERRED |
| Animate Routes | 4 | `animate()`, `regenerate_frame()`, `delete_frame()`, `generate()` **EXTRACTED** `references` |
| Animate Route Tests | 2 | `FakeGemini`, `_make()` INFERRED |
| Stage1 Route Tests | 2 | `app_and_store()` INFERRED |
| Project Store Tests | 1 | `store()` fixture INFERRED |

**Shortest paths:**

- `ProjectStore ←references [EXTRACTED]— get_store()` (1 hop)
- `ProjectStore ←references [EXTRACTED]— list_projects()` (1 hop)
- `ProjectStore ←uses [INFERRED]— AppContext` (1 hop)

### Structural explanation

`ProjectStore` is the **single persistence abstraction**:

```
Settings.projects_dir
        │
        ▼
_default_store() / get_store()     _default_service()  (MCP)
        │                                 │
        ▼                                 ▼
   ProjectStore  ◄──────────────  SpriteService(store=...)
        ▲
        │ Depends(get_store)
   generate / animate / export / projects / prompts / assets
```

### Source evidence

- `backend/app/deps.py` L17–45: `_default_store()` → `ProjectStore(root=...)`; `get_store()` returns it
- `backend/app/routes/projects.py`, `generate.py`, `animate.py`, `export.py`, `prompts.py`, `assets.py`: all inject `ProjectStore = Depends(get_store)`
- `backend/app/mcp_server.py` L93–97: `_default_service()` builds `SpriteService(store=ProjectStore(settings.projects_dir), ...)`
- `backend/app/services/sprite_service.py` L138: constructor requires `store: ProjectStore`
- `backend/tests/test_project_store.py`: dedicated store fixture community

**Verdict:** The bridge is **real and intentional**. EXTRACTED edges to deps + HTTP routes are trustworthy. The large MCP INFERRED fan-out (`MCPProjectSummary`, `MCPAnimationResult`, …) is **directionally right at the module level** (MCP uses the store via `SpriteService`) but **over-specific as pairwise `uses` edges** from each DTO to `ProjectStore`.

---

## Query 2 — Why does `SpriteService` bridge MCP, routes, and deps?

**Original question:** Why does `SpriteService` connect MCP Server Core to Animate Routes, Frame Edit Helpers, Deps And Settings, Projects API Routes?

**Expanded tokens:** `sprite service mcp animate frame deps project`

**Graph finding:** Degree **68**. Own community: **MCP Server Core**. Cross-community:

| Target community | Edges | Notes |
|------------------|------:|-------|
| Projects API Routes | 12 | Store + MCP workflow tests; mix EXTRACTED/INFERRED |
| Animate Routes | 4 | `animate` / `regenerate_frame` / `delete_frame` / `generate` INFERRED `calls` |
| Deps And Settings | 2 | `_default_service()` EXTRACTED; `enhance_prompt` INFERRED |
| Frame Edit Helpers | 1 | `._edit_frame()` EXTRACTED `method` |

**Shortest path:** `SpriteService ←uses [INFERRED]— AppContext` (1 hop) — `AppContext` is a dataclass holding `service: SpriteService` (`mcp_server.py` L88–90).

### Structural explanation

`SpriteService` is the **application core** shared by two transports:

| Transport | How it gets a `SpriteService` | Evidence |
|-----------|-------------------------------|----------|
| HTTP (FastAPI) | Routes construct `SpriteService(store=..., gemini=...)` per request | `animate.py` L100+, `generate.py` L108+ |
| MCP (stdio) | Lifespan yields `AppContext(service=...)` from `_default_service()` | `mcp_server.py` L93–121 |

Methods like `.animate()`, `.generate_sprite()`, `.export_sheet()`, `._edit_frame()` are EXTRACTED from the class AST; route functions are linked INFERRED as callers.

### Source evidence

- `backend/app/mcp_server.py` L1 docstring: “Local stdio MCP adapter over the framework-neutral SpriteService”
- `backend/app/mcp_server.py` L88–107: `AppContext`, `_default_service()`, `_service(ctx)`
- `backend/app/routes/animate.py` / `generate.py`: instantiate `SpriteService` with injected deps
- `backend/app/services/sprite_service.py` L134+: class definition and public API

**Verdict:** The bridge is **architecturally correct**. Prefer EXTRACTED method/contains edges and the `AppContext → SpriteService` composition. Treat INFERRED `calls` from route names and MCP DTO `uses` edges as **approximate**, not AST-proven call graphs.

---

## Query 3 — Why does `GeminiClient` bridge Gemini Client to routes, MCP, deps, and live validation?

**Original question:** Why does `GeminiClient` connect Gemini Client to Animate Routes, MCP Server Core, Deps And Settings, Config And Live Validation?

**Expanded tokens:** `gemini client animate mcp deps settings config`

**Graph finding:** Degree **36** (18 EXTRACTED / 18 INFERRED). Cross-community:

| Target community | Edges | Mechanism |
|------------------|------:|-----------|
| MCP Server Core | 8 | INFERRED `uses` to `Style`/`ViewMode`/`Direction` and request/error types |
| Deps And Settings | 4 | `_default_gemini()`, `get_gemini_client()`, `build_default_client()` **EXTRACTED** |
| Animate Routes | 3 | `animate()`, `regenerate_frame()`, `generate()` **EXTRACTED** `references` |
| Config And Live Validation | 1 | `_wrapper()` in `validate_live_models.py` **EXTRACTED** |

**Shortest paths:**

- `GeminiClient ←references [EXTRACTED]— get_gemini_client()` (1 hop)
- `GeminiClient ←references [EXTRACTED]— _wrapper() → Settings` (2 hops)

### Structural explanation

```
Settings (Vertex auth)
    │
    ▼
build_default_client() / _default_gemini() / get_gemini_client()
    │
    ├── HTTP routes (Depends) → SpriteService(gemini=...) / direct GeminiClient use
    ├── MCP _default_service() → SpriteService(gemini=build_default_client())
    └── scripts/validate_live_models.py (_wrapper, probes)
```

### Source evidence

- `backend/app/deps.py` L22–50: `_default_gemini()`, `get_gemini_client()`
- `backend/app/services/gemini_client.py` L64+, L295+: `GeminiClient`, `build_default_client()`
- `backend/app/routes/animate.py` / `generate.py`: `gemini: GeminiClient = Depends(get_gemini_client)`
- `backend/app/mcp_server.py` L96–97: `gemini=build_default_client()`
- `scripts/validate_live_models.py`: live harness wraps settings + client

**Verdict:** The bridge is **real**. EXTRACTED wiring through deps and route references is solid. INFERRED edges from `GeminiClient` to MCP request DTOs (`RegenerateFrameRequest`, `DeleteFrameRequest`) are **weak** — those models live in animate routes and do not type-reference `GeminiClient`; the real link is route → client → edit/generate.

---

## Query 4 — Are the ~40 INFERRED relationships involving `ProjectStore` correct?

**Examples called out by the report:** `AppContext`, `_default_service()`

**INFERRED neighbor set (35 unique labels):** includes service types (`SpriteService`, error hierarchy), MCP DTOs (`MCPAnimationResult`, …), route request models (`RegenerateFrameRequest`, `DeleteFrameRequest`, `ExportRequest`), test helpers (`app_and_store()`, `store()`, `FakeGemini`, `_make()`), and domain types (`Project`, `FrameStatus`, `ProjectHealth`).

### Verdict table

| Neighbor | Graph claim | Source reality | Correct? |
|----------|-------------|----------------|----------|
| `_default_service()` | `calls`/`uses` | Constructs `ProjectStore(...)` then passes to `SpriteService` | **Yes** (composition) |
| `AppContext` | `uses` | Holds `SpriteService`, not `ProjectStore` directly | **Indirect only** — edge overstates direct use |
| `SpriteService` | `uses` | Constructor requires `store: ProjectStore` | **Yes** |
| `Project` | `uses` | Store read/write manifest | **Yes** |
| MCP* DTOs | `uses` | DTOs never import/call store; service does | **Module-level yes, pairwise no** |
| `RegenerateFrameRequest` / `DeleteFrameRequest` / `ExportRequest` | `uses` | Request bodies; handlers inject store separately | **Route-level yes, type-level no** |
| `SpriteServiceError` and subclasses | `uses` | Errors from service layer, not store | **Mostly no** as direct edges |
| `app_and_store()` / `store()` | test helpers | Fixtures build/override store | **Yes** |
| `FakeGemini` | `uses` | Unrelated to store | **No** |

**Summary:** Roughly **~40% clearly correct**, **~35% correct only as “same feature flow”**, **~25% spurious** (errors, FakeGemini, DTO fan-out). The suggested question’s two examples: `_default_service()` **yes**; `AppContext` **only via `SpriteService`**.

---

## Query 5 — Are the ~46 INFERRED relationships involving `SpriteService` correct?

**Examples:** `AppContext`, `MCPAnimationResult`

### Verdict table

| Neighbor | Source reality | Correct? |
|----------|----------------|----------|
| `AppContext` | `service: SpriteService` field | **Yes** |
| `ProjectStore` | Required constructor dep | **Yes** |
| `ViewMode` / `Style` / `Direction` / `Frame` / `Project` | Used in inputs/results and method bodies | **Yes** |
| `ImageProvider` / `PromptEnhancer` / provider errors | Constructor + method contracts | **Yes** |
| `animate()` / `generate()` / `export()` route fns | Routes construct and call service | **Yes** (call-site; relation tag is INFERRED) |
| `MCPAnimationResult` | Built from `AnimationResult` in MCP tools; does not reference `SpriteService` type | **Indirect** — tool handlers use service, DTO does not |
| Other MCP* DTOs | Same pattern | **Indirect** |
| `DeleteFrameRequest` / `RegenerateFrameRequest` | Route models; service methods take primitives/ids | **Route-level yes, type-level no** |
| Named unit tests | Tests call service API | **Yes** as test→SUT |

**Summary:** Core composition edges (`AppContext`, `ProjectStore`, domain enums, provider protocol) are **correct**. MCP DTO fan-out is the main inflation. Example `AppContext`: **correct**. Example `MCPAnimationResult`: **over-linked** (should be tool handler → service → `AnimationResult` → MCP DTO).

---

## Query 6 — Are the ~47 INFERRED relationships involving `ViewMode` correct?

**Examples:** `AppContext`, `MCPAnimationResult`

**EXTRACTED neighbors (trusted):** `models.py`, `Enum`, `str`, docstring, `directions_for()`, `validate_direction()`.

**INFERRED neighbors (45):** heavy fan-out to MCP DTOs, `SpriteService`, `GeminiClient`, Azure/Gemini error types, test fakes (`FakeGemini`, `FakeSDK`, `_Part`, `_Response`, …), and service result dataclasses.

### Verdict

| Neighbor class | Correct as direct edge? | Why |
|----------------|-------------------------|-----|
| `SpriteService`, `GeminiClient`, `ImageProvider`, `AzureImageProvider`, `PromptEnhancer` | **Yes** | APIs take `view_mode: ViewMode` |
| `GenerateSpriteInput` / `AnimationResult` fields | **Yes** | Dataclasses include `view_mode` |
| `AppContext` | **No** | Only holds `SpriteService` |
| `MCPAnimationResult` / other MCP* | **No / weak** | DTOs carry `Project` (which has `view_mode`), not a `ViewMode` field on every MCP type; `MCPProjectSummary` **does** expose `view_mode` — that one is closer to correct |
| Gemini/Azure error types, Fake* helpers | **No** | Co-occurrence in files/tests, not type usage |
| `_Candidate` / `_Content` / `_Part` | **No** | Test SDK stubs |

**Summary:** Only a **small minority** of the 47 INFERRED edges are precise. The enum is a real cross-cutting parameter; the graph **massively over-attributes** it. Example edges to `AppContext` and generic `MCPAnimationResult`: **not directly correct**.

---

## Query 7 — Are the ~46 INFERRED relationships involving `Style` correct?

**Caveat:** There are **7** nodes labeled `Style`. God-node / suggested-question stats refer to `backend_app_models_style` (degree 50: 4 EXTRACTED + 46 INFERRED). A low-degree duplicate (e.g. generate-route annotation node) can confuse naive `find`-by-label tools.

**Pattern:** Nearly identical to `ViewMode`.

| Neighbor class | Correct as direct edge? |
|----------------|-------------------------|
| `SpriteService`, `GeminiClient`, `ImageProvider`, `AzureImageProvider`, `PromptEnhancer`, `GenerateSpriteInput` | **Yes** — `style: Style` in APIs |
| `AppContext` | **No** |
| Most MCP* DTOs | **Weak** — via nested `Project.style`; `MCPProjectSummary.style` is the best MCP link |
| Error types / Fake* / `_Part`… | **No** |
| `test_style_enum_values()` | **Yes** as test coverage |

**Path tool note:** `Style ←uses [INFERRED]— MCPAnimationResult` exists in the graph but is an **over-inference**; `MCPAnimationResult` only has `project: Project` and `frame_paths`.

**Summary:** Same conclusion as Query 6 — **architectural role correct, pairwise INFERRED graph inflated**. Treat EXTRACTED enum definition edges as ground truth; treat INFERRED `uses` to unrelated errors/fakes as noise.

---

## Cross-cutting Findings

### 1. Duplicate labels dilute queries
`Style`×7 and `ViewMode`×9 mean BFS start-node selection and `graphify path` can attach to the wrong instance. Prefer canonical IDs when auditing.

### 2. INFERRED `uses` ≈ “mentioned in the same feature”
AST EXTRACTED edges (`contains`, `method`, `references` from deps/routes) are high trust. Semantic/INFERRED `uses` between types often mean “appear together in mcp_server.py / sprite_service.py,” not a real field/call.

### 3. Two adapters, one core
Hyperedge **Shared SpriteService HTTP and MCP Adapters** matches the code: FastAPI routes and FastMCP both sit on `SpriteService` + `ProjectStore`.

### 4. Persistence spine
Hyperedge / design theme **Filesystem Project Storage** is embodied by `ProjectStore` bridging deps → all mutating routes → tests.

---

## Suggested Follow-ups

1. Trace `SpriteService._edit_frame` → pose reference → Gemini edit (Frame Edit Helpers community).
2. Compare EXTRACTED vs INFERRED edge ratios after a `--mode deep` rebuild to see if DTO fan-out worsens.
3. Deduplicate cross-language `Style`/`ViewMode` aliases (frontend `client.ts` vs backend `models.py`) with explicit `semantically_similar_to` instead of competing same-label nodes.

---

## Appendix A — Query expansion audit

| # | Original focus | Vocab tokens used |
|---|----------------|-------------------|
| 1 | ProjectStore bridge | `project store mcp deps settings animate routes frame` |
| 2 | SpriteService bridge | `sprite service mcp animate frame deps project` |
| 3 | GeminiClient bridge | `gemini client animate mcp deps settings config` |
| 4 | ProjectStore INFERRED | start nodes: `AppContext`, `_default_service()`, `store()` |
| 5 | SpriteService INFERRED | start nodes: `AppContext`, `MCPAnimationResult`, `SpriteService` |
| 6–7 | ViewMode / Style INFERRED | degree audit on canonical model nodes + source review |

## Appendix B — Confidence mix for hubs

| Node | Degree | EXTRACTED | INFERRED |
|------|-------:|----------:|---------:|
| ProjectStore | 77 | 37 | 40 |
| SpriteService | 68 | 22 | 46 |
| ViewMode (models) | 53 | 6 | 47 |
| Style (models) | 50 | 4 | 46 |
| GeminiClient | 36 | 18 | 18 |

---

*Report written from graph traversal + source verification. Do not treat INFERRED edges as proven call/import facts without checking `source_file` / `source_location`.*
