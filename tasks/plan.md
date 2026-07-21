# Implementation Plan: Project Continuity, Creative Controls, and MCP

## Overview

Deliver the next product increment as one roadmap with three independently releasable phases:

1. make filesystem projects discoverable and resumable;
2. add camera-aware directional animation and an explicit, previewable prompt enhancer;
3. move workflow logic behind an application-service boundary and expose it through a local MCP server.

The existing filesystem store remains the source of truth. FastAPI, React, and MCP become adapters around shared domain and application services. Each phase must leave the current Generate -> Animate -> Export workflow working and must pass the repository's full validation suite.

## Goals

- A user can find, inspect, resume, and delete prior projects without losing workflow state.
- Side-scroller projects support left/right; top-down/2.5D projects support eight directions.
- Prompt enhancement is opt-in, previewable, editable, and never required for generation.
- HTTP and MCP invoke the same application workflow functions and error rules.
- Existing project manifests remain readable with safe defaults.

## Non-goals for this roadmap

- User accounts, cloud sync, multi-user locking, or a database migration.
- Arbitrary project renaming/tagging/folders.
- Concurrent frame generation or a background job protocol.
- Automatic prompt rewriting without a visible preview.
- Remote MCP transport, authentication, or destructive MCP project/frame deletion.
- Reference-image ingestion through MCP v1; the HTTP interface keeps this capability.

## Current architecture findings

- `ProjectStore` is the persistence hub used by every workflow.
- FastAPI route handlers currently own orchestration for generation, animation, frame repair, and export.
- `useProjectStore` is the frontend workflow hub, but prompt input remains local to `GeneratePanel`, which prevents complete resume.
- `GET /projects` and `DELETE /projects/{id}` already exist, but listing returns raw manifests and there is no project-detail/resume endpoint or browser UI.
- Prompt construction is centralized in the pure `prompt_builder` module.
- `GeminiClient` already owns model selection, retry, timeout, and error classification, making it the correct home for a text-only enhancement primitive.
- Current official SDK documentation supports text output through `generate_content`, per-call `HttpOptions`, and typed FastMCP tools with lifespan-shared dependencies.

## Architecture decisions

### Project continuity

- Keep filesystem folders and `project.json`; do not add a database.
- Add `schema_version`, `created_at`, and `updated_at` to the manifest. Old manifests are enriched from file metadata before validation and are not rewritten merely by reading them.
- Separate persisted `Project` from API-facing `ProjectSummary` and `ProjectDetail` models.
- `GET /projects` returns compact summaries sorted by `updated_at` descending.
- `GET /projects/{id}` returns a resumable detail payload with freshly constructed sprite/frame asset URLs.
- Catalog scans isolate corrupt or incomplete folders instead of failing the whole list. Such entries remain deletable but cannot be resumed.
- A resumed project clears transient export results and restores prompt, style, sprite, action, FPS, frames, camera mode, and direction.

### Directional controls

- Add `ViewMode`: `side_scroller` and `top_down_2_5d`.
- Add eight `Direction` values: `left`, `right`, `up`, `down`, `up_left`, `up_right`, `down_left`, and `down_right`.
- Side-scroller validation accepts only left/right. Top-down/2.5D accepts all eight.
- Existing manifests default to `side_scroller` + `left`.
- View mode is chosen before base-sprite generation because it determines camera perspective. Direction can be changed for animation and is persisted with the project.
- Backend validation is authoritative; a backend options endpoint supplies the frontend's allowed directions to avoid duplicated rules.
- Generate and frame prompts include explicit camera/direction language while preserving base-anchored edits and shared-bbox processing.

### Prompt enhancement

- Add `POST /prompts/enhance` as a text-only preview operation.
- The user explicitly enables enhancement and clicks a preview action. Generation never performs a hidden enhancement call.
- The enhanced subject description is visible and editable before generation.
- `prompt` remains the original user text for backward compatibility. `enhanced_prompt` and `prompt_source` record the accepted text and whether raw or enhanced input produced the asset.
- On enhancer timeout, refusal, empty output, or API failure, the raw prompt remains available and generation remains enabled.
- Add a separately configurable Vertex text model (`GEMINI_MODEL_TEXT`); do not reuse an image model implicitly.
- `GeminiClient` reuses its timeout/retry classification but parses text independently from image responses.

### Shared application services and MCP

- Introduce a framework-neutral `SpriteService` (or equivalently named application module) that accepts `ProjectStore`, `GeminiClient`, and the remover dependency.
- Service inputs use domain values/Pillow images, not `Request`, `UploadFile`, `HTTPException`, or MCP context objects.
- Service results are typed Pydantic models. Service exceptions are typed and adapter-neutral.
- FastAPI routes translate transport input/output and map service errors to HTTP status codes.
- MCP tools call the same service methods directly; they never call HTTP endpoints.
- Use the stable MCP Python SDK v1 FastMCP API (`mcp>=1.12,<2`). The dependency is justified because it supplies protocol schemas, stdio transport, lifespan management, and structured tool output; the `<2` cap avoids adopting the current v2 beta contract accidentally.
- The MCP server uses stdio, writes diagnostics only to stderr, and initializes one shared store/client/service in its lifespan.
- Initial tools: `list_projects`, `get_project`, `enhance_prompt`, `generate_sprite`, `animate`, `regenerate_frame`, and `export_sheet`.
- MCP v1 omits destructive delete tools and reference-image file access. These can be added later with explicit safety boundaries.

## Target contracts

### Project catalog

`ProjectSummary` should contain:

- id and prompt preview;
- style, view mode, direction, and action;
- thumbnail URL;
- total/OK/failed frame counts;
- created/updated timestamps;
- health (`ready`, `incomplete`, or `corrupt`) and `resume_available`.

`ProjectDetail` should contain the complete resumable state plus a fresh `sprite_url`. Failed frame URLs remain null.

### Prompt provenance

Persist:

- `prompt`: original user text;
- `enhanced_prompt`: accepted preview or null;
- `prompt_source`: `raw` or `enhanced`.

The effective generation text is `enhanced_prompt` only when `prompt_source=enhanced`; otherwise it is `prompt`.

### MCP outputs

Return structured models rather than prose. Mutation results include `project_id`, current project/frame state, and saved asset paths. Expected validation or recoverable generation failures become tool errors with actionable messages; unexpected exceptions remain visible in server logs and do not leak credentials.

## Dependency graph

```text
Manifest compatibility
  -> project catalog/detail API
     -> frontend hydrate/resume state
        -> project browser UI

Direction enums + prompt rules
  -> backend generate/animate persistence
     -> frontend direction contracts
        -> direction controls UI

Gemini text primitive
  -> enhance endpoint + prompt provenance
     -> enhancer preview UI

All stable workflows
  -> application-service extraction
     -> FastAPI thin adapters
        -> FastMCP thin adapter
```

## Phase 1: Project browser and resume

### Task 1: Add backward-compatible manifest metadata

**Description:** Add schema/timestamp metadata and centralize timestamp updates in `ProjectStore` without breaking existing manifests.

**Acceptance criteria:**

- Old manifests without metadata load successfully using UTC timestamps derived from the manifest/folder.
- New projects persist `schema_version`, `created_at`, and `updated_at`; subsequent mutations advance only `updated_at`.
- Merely reading a project does not rewrite its manifest.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_project_store.py -q`
- Fixture test covers an old manifest and stable repeated reads.

**Dependencies:** None

**Files likely touched:**

- `backend/app/models.py`
- `backend/app/storage/project_store.py`
- `backend/tests/test_models.py`
- `backend/tests/test_project_store.py`

**Estimated scope:** Medium

### Task 2: Build resilient project summary and detail APIs

**Description:** Replace the raw-manifest catalog response with a compact, sorted summary and add a detail endpoint suitable for resume.

**Acceptance criteria:**

- `GET /projects` returns newest-first summaries with counts, thumbnail, health, and resume availability.
- `GET /projects/{id}` returns full state with fresh asset URLs and returns 404/409 for missing/unresumable projects.
- One corrupt or incomplete folder does not prevent healthy projects from appearing; delete of an unknown id returns 404.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_routes_projects.py tests/test_project_store.py -q`
- API test covers healthy, old, incomplete, corrupt, missing, and delete cases.

**Dependencies:** Task 1

**Files likely touched:**

- `backend/app/models.py`
- `backend/app/storage/project_store.py`
- `backend/app/routes/projects.py`
- `backend/tests/test_routes_projects.py`

**Estimated scope:** Medium

### Task 3: Add frontend project hydration

**Description:** Extend the API and Zustand contracts so a detail response can restore all workflow state, including the prompt editor.

**Acceptance criteria:**

- Typed client methods distinguish project summaries from project detail.
- `loadProject(detail)` restores prompt/style/sprite/action/FPS/frames and clears transient export state.
- Generating a new project, resetting, or loading another project cannot leave state from the prior project behind.

**Verification:**

- `cd frontend && npm test -- --run src/api/client.test.ts src/state/project.test.ts`

**Dependencies:** Task 2

**Files likely touched:**

- `frontend/src/api/client.ts`
- `frontend/src/api/client.test.ts`
- `frontend/src/state/project.ts`
- `frontend/src/state/project.test.ts`

**Estimated scope:** Medium

### Task 4: Add the project browser UI

**Description:** Add a catalog view that loads on app startup, supports resume/refresh/delete, and makes unhealthy entries explicit.

**Acceptance criteria:**

- Cards show thumbnail, prompt preview, updated time, style/action, and frame success summary.
- Opening a healthy project restores the Generate -> Animate -> Export UI; corrupt/incomplete entries explain why resume is unavailable.
- Delete requires confirmation, refreshes the catalog, and resets the active project when it was deleted.

**Verification:**

- `cd frontend && npm test -- --run src/components/ProjectBrowser.test.tsx`
- Manual check: generate, reload browser, resume, animate/export, then delete.

**Dependencies:** Task 3

**Files likely touched:**

- `frontend/src/components/ProjectBrowser.tsx`
- `frontend/src/components/ProjectBrowser.test.tsx`
- `frontend/src/App.tsx`
- `frontend/src/index.css`

**Estimated scope:** Medium

### Checkpoint 1: Project continuity

- All backend and frontend tests pass.
- Production frontend build succeeds.
- Old manifests remain readable.
- A project survives a full page reload and can continue from its prior step.

## Phase 2A: Directional controls

### Task 5: Define camera/direction rules and pure prompts

**Description:** Add domain enums, validation, options data, and deterministic prompt language for both camera modes.

**Acceptance criteria:**

- Side-scroller rejects six invalid directions; top-down/2.5D accepts all eight.
- Old projects validate as side-scroller/left.
- Generate and frame prompt tests assert explicit camera and direction wording without changing action/frame numbering semantics.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_prompt_builder.py -q`

**Dependencies:** Task 1

**Files likely touched:**

- `backend/app/models.py`
- `backend/app/services/prompt_builder.py`
- `backend/tests/test_models.py`
- `backend/tests/test_prompt_builder.py`

**Estimated scope:** Medium

### Task 6: Carry direction through backend generation and animation

**Description:** Accept/persist view mode during generation and direction during generation/animation; ensure regeneration uses stored values.

**Acceptance criteria:**

- Generate, animate, and regenerate call prompt builders with the persisted mode/direction.
- Invalid mode/direction combinations return 422 before any Gemini call or file mutation.
- Animation responses and project detail expose the selected values, including after reload.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_routes_stage1.py tests/test_routes_animate.py -q`

**Dependencies:** Task 5

**Files likely touched:**

- `backend/app/routes/generate.py`
- `backend/app/routes/animate.py`
- `backend/tests/test_routes_stage1.py`
- `backend/tests/test_routes_animate.py`

**Estimated scope:** Medium

### Task 7: Add direction contracts to frontend state and API

**Description:** Extend typed requests/results and state transitions while keeping compatibility defaults for resumed older projects.

**Acceptance criteria:**

- Client requests serialize `view_mode` and `direction` exactly once and parse backend options.
- State hydration preserves values across generate, animate, repair, and resume.
- Changing view mode automatically selects a valid default direction.

**Verification:**

- `cd frontend && npm test -- --run src/api/client.test.ts src/state/project.test.ts`

**Dependencies:** Task 6

**Files likely touched:**

- `frontend/src/api/client.ts`
- `frontend/src/api/client.test.ts`
- `frontend/src/state/project.ts`
- `frontend/src/state/project.test.ts`

**Estimated scope:** Medium

### Task 8: Add camera-aware direction controls

**Description:** Add accessible controls before generation and animation, with allowed directions driven by backend options.

**Acceptance criteria:**

- Side-scroller visibly offers only left/right; top-down/2.5D offers eight labeled directions.
- The base-sprite view mode is visible during animation; switching camera mode requires generating a compatible base sprite.
- Resumed projects render the saved selection and submit it unchanged unless the user edits it.

**Verification:**

- `cd frontend && npm test -- --run src/components/GeneratePanel.test.tsx src/components/AnimatePanel.test.tsx`
- Manual check both modes, a diagonal animation, and invalid-request error text.

**Dependencies:** Task 7

**Files likely touched:**

- `frontend/src/components/GeneratePanel.tsx`
- `frontend/src/components/GeneratePanel.test.tsx`
- `frontend/src/components/AnimatePanel.tsx`
- `frontend/src/components/AnimatePanel.test.tsx`
- `frontend/src/index.css`

**Estimated scope:** Medium

### Checkpoint 2A: Directional animation

- Existing left-facing side-scroller behavior remains the default.
- UI and backend enforce identical direction rules.
- A resumed top-down diagonal project regenerates frames using its stored context.

## Phase 2B: Prompt enhancer

### Task 9: Add a text-only Gemini enhancement primitive

**Description:** Add a separately configured text model and typed `enhance_prompt` operation inside `GeminiClient`.

**Acceptance criteria:**

- Text calls use text output configuration, low variance, bounded output, and the existing per-call timeout policy.
- Non-empty text is returned without markdown wrappers; refusal, empty output, timeout, and transport errors use existing typed Gemini errors.
- Image generation/edit tests remain unchanged and continue using image response modalities.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_gemini_client.py tests/test_config.py -q`

**Dependencies:** Task 5

**Files likely touched:**

- `backend/app/config.py`
- `backend/app/services/gemini_client.py`
- `backend/tests/test_gemini_client.py`
- `backend/tests/test_config.py`
- `backend/.env.example`

**Estimated scope:** Medium

### Task 10: Add enhancement API and prompt provenance

**Description:** Add a preview endpoint and teach generation to persist raw versus accepted enhanced text honestly.

**Acceptance criteria:**

- `POST /prompts/enhance` validates length/style/view context and returns original plus enhanced text without creating a project.
- Generate uses raw input unless an explicit enhanced value is supplied; manifests persist `prompt`, `enhanced_prompt`, and `prompt_source`.
- Enhancer failure never mutates storage and never prevents a later raw generation request.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_routes_prompts.py tests/test_routes_stage1.py -q`

**Dependencies:** Task 9

**Files likely touched:**

- `backend/app/models.py`
- `backend/app/routes/prompts.py`
- `backend/app/routes/generate.py`
- `backend/app/main.py`
- `backend/tests/test_routes_prompts.py`

**Estimated scope:** Medium

### Task 11: Add opt-in prompt preview and fallback UI

**Description:** Bind prompt state to Zustand and add an explicit enhance/preview/edit/revert interaction in `GeneratePanel`.

**Acceptance criteria:**

- Enabling enhancement does not call Gemini until the user asks for a preview.
- The preview is labeled as enhanced, editable, and can be accepted or reverted before generation.
- An enhancement error keeps the raw prompt intact, shows a concise message, and leaves Generate enabled.

**Verification:**

- `cd frontend && npm test -- --run src/api/client.test.ts src/components/GeneratePanel.test.tsx src/state/project.test.ts`
- Manual check raw, enhanced, edited-enhanced, timeout fallback, and resumed provenance.

**Dependencies:** Task 10

**Files likely touched:**

- `frontend/src/api/client.ts`
- `frontend/src/api/client.test.ts`
- `frontend/src/state/project.ts`
- `frontend/src/components/GeneratePanel.tsx`
- `frontend/src/components/GeneratePanel.test.tsx`

**Estimated scope:** Medium

### Checkpoint 2B: Creative controls

- Direction and prompt provenance persist across reload/resume.
- No hidden model call occurs.
- Raw generation still works when the text model is unavailable.
- Full backend/frontend suites and frontend build are green.

## Phase 3: Shared application services and MCP

### Task 12: Define application result and error contracts

**Description:** Create the framework-neutral service boundary and first move project queries behind it.

**Acceptance criteria:**

- Service code imports neither FastAPI nor MCP.
- Typed results cover catalog/detail and asset references; typed errors distinguish not-found, invalid-state, validation, safety, and upstream failures.
- Project route schemas, status codes, and user-visible behavior remain compatible.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_sprite_service.py tests/test_routes_projects.py -q`

**Dependencies:** Checkpoint 2B

**Files likely touched:**

- `backend/app/services/sprite_service.py`
- `backend/app/routes/projects.py`
- `backend/tests/test_sprite_service.py`
- `backend/tests/test_routes_projects.py`

**Estimated scope:** Medium

### Task 13: Extract enhance and generate workflows

**Description:** Move prompt enhancement, image generation, deterministic processing, persistence, and result creation into `SpriteService`.

**Acceptance criteria:**

- FastAPI routes only parse transport data, invoke the service, and map results/errors.
- Service tests cover raw/enhanced generation, optional reference image, safety, timeout, and processing failures.
- Existing route response/status behavior and assets remain unchanged.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_sprite_service.py tests/test_routes_prompts.py tests/test_routes_stage1.py -q`

**Dependencies:** Task 12

**Files likely touched:**

- `backend/app/services/sprite_service.py`
- `backend/app/routes/generate.py`
- `backend/app/routes/prompts.py`
- `backend/tests/test_sprite_service.py`
- `backend/tests/test_routes_stage1.py`

**Estimated scope:** Medium

### Task 14: Extract animation and frame-repair workflows

**Description:** Move animate, regenerate, and frame-delete orchestration behind the same service boundary without weakening partial-failure behavior.

**Acceptance criteria:**

- Frame-local Gemini/background/pixel failures still produce persisted failed-frame statuses.
- Direction/camera context is shared by full animation and single-frame regeneration.
- FastAPI animation routes contain no pipeline/store orchestration.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_sprite_service.py tests/test_routes_animate.py -q`

**Dependencies:** Task 13

**Files likely touched:**

- `backend/app/services/sprite_service.py`
- `backend/app/routes/animate.py`
- `backend/tests/test_sprite_service.py`
- `backend/tests/test_routes_animate.py`

**Estimated scope:** Medium

### Task 15: Extract export workflow

**Description:** Move export validation, packing, atlas creation, persistence, and asset-result creation into the application service.

**Acceptance criteria:**

- Incomplete animations remain blocked consistently for HTTP and future MCP callers.
- Service results expose adapter-neutral asset filenames/paths; HTTP adds cache-busted URLs.
- JSON/XML, padding, columns, and static-sprite export tests remain green.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_sprite_service.py tests/test_export_multi.py tests/test_routes_stage1.py -q`

**Dependencies:** Task 14

**Files likely touched:**

- `backend/app/services/sprite_service.py`
- `backend/app/routes/export.py`
- `backend/tests/test_sprite_service.py`
- `backend/tests/test_export_multi.py`

**Estimated scope:** Medium

### Task 16: Add FastMCP server foundation and read tools

**Description:** Add the stable MCP dependency, a stdio entry point, lifespan dependency construction, and read-only catalog/detail tools.

**Acceptance criteria:**

- Importing the module does not start the server; the console entry point starts stdio explicitly.
- `list_projects` and `get_project` return structured output through an in-process MCP client test.
- The lifespan shares exactly one configured store, Gemini client, and service; stdout contains protocol traffic only.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py -q`
- Tool schema snapshot/field assertions cover names, descriptions, and structured outputs.

**Dependencies:** Task 15

**Files likely touched:**

- `backend/pyproject.toml`
- `backend/app/mcp_server.py`
- `backend/app/deps.py`
- `backend/tests/test_mcp_server.py`

**Estimated scope:** Medium

### Task 17: Add creative and export MCP tools

**Description:** Expose the stable service operations without HTTP calls or duplicated workflow logic.

**Acceptance criteria:**

- `enhance_prompt`, `generate_sprite`, `animate`, `regenerate_frame`, and `export_sheet` return structured results.
- Invalid direction, missing project, safety refusal, partial failure, and blocked export surface actionable MCP tool errors.
- Tests fail if an MCP tool makes an HTTP request or bypasses `SpriteService`.

**Verification:**

- `cd backend && .\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py tests/test_sprite_service.py -q`
- In-process scenario: generate -> animate -> repair if needed -> export -> verify paths exist.

**Dependencies:** Task 16

**Files likely touched:**

- `backend/app/mcp_server.py`
- `backend/tests/test_mcp_server.py`

**Estimated scope:** Medium

### Task 18: Document and smoke-test MCP installation

**Description:** Document configuration, client registration, tool behavior, limitations, and a reproducible stdio smoke test.

**Acceptance criteria:**

- README includes install/run examples and a valid client configuration using the console entry point.
- Documentation states local filesystem scope, non-destructive initial tools, no MCP reference-image input, and required Vertex credentials/model settings.
- A stdio smoke test initializes the server and lists tools without calling Gemini.

**Verification:**

- Run the documented stdio initialization/tool-list command.
- `cd backend && .\.venv\Scripts\python.exe -m pip check`

**Dependencies:** Task 17

**Files likely touched:**

- `README.md`
- `backend/.env.example`
- `backend/pyproject.toml`
- `scripts/smoke_mcp.py`

**Estimated scope:** Small

### Checkpoint 3: MCP complete

- HTTP and MCP tests use the same service fakes and produce equivalent results.
- MCP has no imports from route modules and performs no HTTP calls.
- Stdio initialization and tool discovery work in a fresh environment.
- Full validation is green.

## Project-wide verification after every checkpoint

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check

cd ..\frontend
npm test -- --reporter=dot
npm run build
npm audit --omit=dev --audit-level=high

cd ..
git diff --check
```

No real Gemini calls run in automated tests; use injected fakes. Manual model smoke tests are optional and must use a disposable project.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Old/corrupt manifests break the browser | High | Compatibility enrichment plus per-folder health isolation |
| Top-down animation drifts from a side-view base | High | Choose/persist camera mode before generation and include it in every prompt |
| Enhanced prompt changes user intent | High | Explicit preview/edit/revert and raw/enhanced provenance |
| Text-model outage blocks generation | Medium | Separate preview endpoint; raw generation remains independent |
| Route-to-service extraction causes regressions | High | Extract one vertical workflow at a time while retaining route tests |
| MCP beta API churn | Medium | Pin stable v1 range below 2 and test tool schemas/protocol behavior |
| MCP returns web URLs unusable to local agents | Medium | Service returns asset references; MCP resolves local paths, HTTP resolves URLs |
| MCP exposes destructive or arbitrary file operations | High | No delete tools and no reference-image path input in MCP v1 |
| Synchronous Gemini calls block MCP event loop | Medium | Register synchronous tool functions initially; only add async/concurrency after measurement |

## Assumptions and deferred decisions

- The app remains local and single-user for this roadmap.
- Stable MCP v1 is preferred over the v2 beta. Re-evaluate only when implementation starts if v2 has become stable.
- Select and document a currently available Vertex text model when Task 9 begins; keep the model configurable.
- Project catalog thumbnails use the existing sprite asset rather than generating a new thumbnail file.
- Project names are prompt previews; explicit rename/tag/search can follow after usage validates the browser.

## Definition of done

- Every task's acceptance criteria and focused tests pass.
- Every checkpoint passes the project-wide verification commands.
- Existing manifests and the original default workflow remain compatible.
- New API/MCP contracts are typed and documented.
- No credentials, generated projects, or reference images are committed.
- The user reviews each checkpoint before the next phase begins.
