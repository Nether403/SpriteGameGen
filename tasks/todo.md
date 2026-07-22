# Local-First Character Animation Workbench Checklist

## Phase 0: Open-Source Foundation

- [x] 0.1 Add Apache-2.0 LICENSE and contributor NOTICE
- [x] 0.2 Add Python/npm license and project metadata
- [x] 0.3 Add CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, PR template, and issue templates
- [x] 0.4 Replace machine-specific example credential paths
- [x] 0.5 Add redacted secret scanning
- [x] 0.6 Add dependency-license policy and third-party notices
- [x] 0.7 Add credential-safe readiness doctor
- [x] 0.8 Harden CI and dependency automation
- [x] 0.9 Add changelog and version-contract documentation
- [x] 0.10 Update onboarding and release documentation

### Phase 0 Checkpoint

- [x] Backend full suite passes
- [x] Frontend full suite and build pass
- [x] Backend/frontend dependency checks pass
- [x] Secret scan passes without exposing values
- [x] Doctor runs without provider credentials
- [x] Windows and Linux CI remain credential-free

## Phase 1: Deterministic Quality and Repair

- [x] 1.1 Add Manifest V2 models and pure migration
- [x] 1.2 Reject future/malformed schemas safely
- [x] 1.3 Add pure bottom-center frame compositor
- [x] 1.4 Add target size, scale, shared/preset/custom palette processing
- [x] 1.5 Persist source and rendered base assets
- [x] 1.6 Persist source and rendered clip frames
- [x] 1.7 Add provider-free render-settings/frame-adjustment services
- [x] 1.8 Add quality/flip/enable/nudge/reset HTTP routes
- [x] 1.9 Make sheet/atlas export enabled-frame aware
- [x] 1.10 Add deterministic individual-frame ZIP and atomic blob commits
- [x] 1.11 Add frontend quality and repair controls
- [x] 1.12 Replace normal destructive frame deletion with curation controls
- [x] 1.13 Add frontend-only preview backgrounds
- [x] 1.14 Surface sheet, atlas, and frame ZIP downloads
- [x] 1.15 Extend MCP deterministic DTOs/capabilities/tools
- [ ] 1.16 Pass live directional correction acceptance

### Phase 1 Checkpoint

- [x] Legacy read does not rewrite manifest/assets
- [x] First legacy mutation writes V2 atomically
- [x] Deterministic rerender tests pass
- [x] Quality/repair performs no provider call
- [x] Generate -> animate -> repair -> resume -> export passes
- [x] Backend/frontend/MCP full verification passes

## Phase 2: Character Animation Workspace

- [x] 2.1 Add framework-neutral clip workspace
- [x] 2.2 Namespace new assets by stable clip ID
- [x] 2.3 Add canonical clip and clip-frame routes
- [x] 2.4 Preserve active-clip compatibility routes
- [x] 2.5 Add clip loop/duration/enabled/provenance metadata
- [x] 2.6 Add clip-aware project summaries and health
- [x] 2.7 Replace singular frontend animation state with clip state
- [x] 2.8 Add character workspace UI
- [x] 2.9 Add loop-range/per-frame-duration playback
- [x] 2.10 Add selected/active clip legacy export
- [x] 2.11 Extend MCP with clip selectors and clip tools
- [x] 2.12 Harden migration, rollback, stale-response, and isolation tests

### Phase 2 Checkpoint

- [x] Multiple clips survive creation, repair, reload, and export
- [x] Sibling clips remain unchanged by target mutations
- [x] Existing no-clip-ID clients still work
- [x] Full backend/frontend/MCP verification passes

## Phase 3: Character Bundles and Godot

- [x] 3.1 Define generic character bundle V1
- [x] 3.2 Add deterministic bundle ZIP and checksums
- [x] 3.3 Add one-clip and all-enabled bundle scopes
- [x] 3.4 Add bundle HTTP endpoint and frontend controls
- [x] 3.5 Add direct MCP character-bundle export
- [x] 3.6 Add Godot 4.7 AnimatedSprite2D profile/importer
- [x] 3.7 Generate SpriteFrames resource and AnimatedSprite2D scene
- [x] 3.8 Add pinned headless Godot CI validation
- [x] 3.9 Package and document bundle/Godot contracts

### Phase 3 Checkpoint

- [x] Same project revision produces byte-identical bundle
- [x] Scope-specific failure gating passes
- [x] Godot headless import/load assertions pass
- [x] Full backend/frontend/MCP verification passes

## Phase 4: Action Packs, Recipes, CLI, and Batch

- [x] 4.1 Define strict versioned action-pack models
- [x] 4.2 Move current actions to bundled data pack
- [x] 4.3 Add idle/run/attack/jump phases and declarative guides
- [x] 4.4 Add ACTION_PACKS_DIR configuration
- [x] 4.5 Add bounded non-executable external pack loading
- [x] 4.6 Enforce reserved IDs and collision rejection
- [x] 4.7 Persist action reference/version/digest/snapshot
- [x] 4.8 Add custom text actions and first/last pose text
- [x] 4.9 Define recipe V1 and project capture
- [x] 4.10 Add sequential recipe runner with preflight
- [x] 4.11 Install sprite CLI
- [x] 4.12 Add atomic resumable sequential batch state
- [x] 4.13 Add read-only MCP recipe tools
- [x] 4.14 Publish validated examples and documentation

### Phase 4 Checkpoint

- [x] External packs cannot execute code or access arbitrary paths
- [x] Saved clips regenerate after source pack removal
- [x] Recipe output contains no secrets/endpoints/environment paths
- [x] Batch resume does not repeat completed provider calls
- [x] CLI, backend, frontend, and MCP verification passes

## Phase 5: ComfyUI Local Provider

- [x] 5.1 Add operation-specific provider capabilities
- [x] 5.2 Declare Azure/Gemini capabilities without behavior changes
- [x] 5.3 Add bounded loopback-only ComfyUI settings/readiness
- [x] 5.4 Add strict workflow descriptor/compiler
- [x] 5.5 Add upload/submit/poll/retrieve/decode adapter
- [x] 5.6 Add queued cancellation and safe running-job drain behavior
- [x] 5.7 Register cached provider in shared runtime
- [x] 5.8 Add requirement preflight and seed plumbing
- [x] 5.9 Add capability-aware HTTP/MCP metadata and UI
- [x] 5.10 Add mocked workflow/transport/security tests
- [x] 5.11 Add manual live acceptance harness
- [x] 5.12 Document installation ownership and security boundary
- [ ] 5.13 Apply generation/edit/pose promotion gates

### Phase 5 Checkpoint

- [x] CI passes without ComfyUI/GPU/models
- [x] Loopback/proxy/redirect/output bounds pass
- [x] Cancellation/timeout never commits project changes
- [ ] Live generation acceptance passes before generation support claim
- [ ] Identity edit acceptance passes before animation support claim
- [ ] Pose acceptance passes before pose-guided support claim
- [x] Full backend/frontend/MCP verification passes

## Final Verification

- [x] `backend`: `uv lock --check`
- [x] `backend`: full pytest suite
- [x] `backend`: `uv pip check`
- [x] `frontend`: full Vitest suite
- [x] `frontend`: production build
- [x] `frontend`: production dependency audit
- [x] MCP: credential-free stdio smoke
- [x] Godot: pinned headless import/load smoke
- [x] Repository: redacted secret scan
- [x] Repository: dependency-license check
- [x] Repository: `git diff --check`
- [ ] Manual: legacy project migration and complete character workflow
- [x] Manual: configured cloud provider live acceptance
- [ ] Manual: ComfyUI promotion matrix for advertised capabilities
