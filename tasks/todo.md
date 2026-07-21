# Next Roadmap Checklist

## Phase 1: Project browser and resume

- [x] Task 1 — Add backward-compatible manifest metadata
- [x] Task 2 — Build resilient project summary and detail APIs
- [x] Task 3 — Add frontend project hydration
- [x] Task 4 — Add the project browser UI

### Checkpoint 1

- [x] Backend suite passes
- [x] Frontend suite and production build pass
- [x] Old manifest opens successfully
- [x] Generate -> reload -> resume -> animate/export works

## Phase 2A: Directional controls

- [x] Task 5 — Define camera/direction rules and pure prompts
- [x] Task 6 — Carry direction through backend generation and animation
- [x] Task 7 — Add direction contracts to frontend state and API
- [x] Task 8 — Add camera-aware direction controls

### Checkpoint 2A

- [x] Side-scroller allows only left/right
- [x] Top-down/2.5D allows all eight directions
- [x] Stored direction survives reload and frame regeneration
- [x] Existing side-scroller/left behavior remains the default

## Phase 2B: Prompt enhancer

- [x] Task 9 — Add a text-only Gemini enhancement primitive
- [x] Task 10 — Add enhancement API and prompt provenance
- [x] Task 11 — Add opt-in prompt preview and fallback UI

### Checkpoint 2B

- [x] Raw, enhanced, edited-enhanced, revert, and failure fallback paths pass
- [x] No hidden enhancement call occurs
- [x] Prompt provenance survives resume
- [x] Full suites and build pass

## Phase 3: Shared services and MCP

- [ ] Follow-up — Add a disposable live-model validation matrix for configured Gemini model availability, latency, safety behavior, and sprite/output quality; document supported model/region combinations and a manual acceptance rubric
- [x] Task 12 — Define application result and error contracts
- [x] Task 13 — Extract enhance and generate workflows
- [x] Task 14 — Extract animation and frame-repair workflows
- [x] Task 15 — Extract export workflow
- [x] Task 16 — Add FastMCP server foundation and read tools
- [x] Task 17 — Add creative and export MCP tools
- [x] Task 18 — Document and smoke-test MCP installation

### Checkpoint 3

- [x] HTTP and MCP both call `SpriteService`
- [x] MCP performs no HTTP calls and imports no route modules
- [x] In-process MCP tool scenario passes
- [x] Stdio initialization and tool discovery pass
- [x] Full backend/frontend/dependency validation passes

## Final validation

- [x] `backend`: full pytest suite
- [x] `backend`: `pip check`
- [x] `frontend`: full Vitest suite
- [x] `frontend`: production build
- [x] `frontend`: production dependency audit
- [x] Repository: `git diff --check`
- [ ] Manual smoke: browse/resume, direction, enhancer fallback, MCP export
