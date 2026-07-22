# Local-First Character Animation Workbench Checklist

## Phase 0: Open-Source Foundation

- [ ] 0.1 Add Apache-2.0 LICENSE and contributor NOTICE
- [ ] 0.2 Add Python/npm license and project metadata
- [ ] 0.3 Add CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, PR template, and issue templates
- [ ] 0.4 Replace machine-specific example credential paths
- [ ] 0.5 Add redacted secret scanning
- [ ] 0.6 Add dependency-license policy and third-party notices
- [ ] 0.7 Add credential-safe readiness doctor
- [ ] 0.8 Harden CI and dependency automation
- [ ] 0.9 Add changelog and version-contract documentation
- [ ] 0.10 Update onboarding and release documentation

### Phase 0 Checkpoint

- [ ] Backend full suite passes
- [ ] Frontend full suite and build pass
- [ ] Backend/frontend dependency checks pass
- [ ] Secret scan passes without exposing values
- [ ] Doctor runs without provider credentials
- [ ] Windows and Linux CI remain credential-free

## Phase 1: Deterministic Quality and Repair

- [ ] 1.1 Add Manifest V2 models and pure migration
- [ ] 1.2 Reject future/malformed schemas safely
- [ ] 1.3 Add pure bottom-center frame compositor
- [ ] 1.4 Add target size, scale, shared/preset/custom palette processing
- [ ] 1.5 Persist source and rendered base assets
- [ ] 1.6 Persist source and rendered clip frames
- [ ] 1.7 Add provider-free render-settings/frame-adjustment services
- [ ] 1.8 Add quality/flip/enable/nudge/reset HTTP routes
- [ ] 1.9 Make sheet/atlas export enabled-frame aware
- [ ] 1.10 Add deterministic individual-frame ZIP and atomic blob commits
- [ ] 1.11 Add frontend quality and repair controls
- [ ] 1.12 Replace normal destructive frame deletion with curation controls
- [ ] 1.13 Add frontend-only preview backgrounds
- [ ] 1.14 Surface sheet, atlas, and frame ZIP downloads
- [ ] 1.15 Extend MCP deterministic DTOs/capabilities/tools
- [ ] 1.16 Pass live directional correction acceptance

### Phase 1 Checkpoint

- [ ] Legacy read does not rewrite manifest/assets
- [ ] First legacy mutation writes V2 atomically
- [ ] Deterministic rerender tests pass
- [ ] Quality/repair performs no provider call
- [ ] Generate -> animate -> repair -> resume -> export passes
- [ ] Backend/frontend/MCP full verification passes

## Phase 2: Character Animation Workspace

- [ ] 2.1 Add framework-neutral clip workspace
- [ ] 2.2 Namespace new assets by stable clip ID
- [ ] 2.3 Add canonical clip and clip-frame routes
- [ ] 2.4 Preserve active-clip compatibility routes
- [ ] 2.5 Add clip loop/duration/enabled/provenance metadata
- [ ] 2.6 Add clip-aware project summaries and health
- [ ] 2.7 Replace singular frontend animation state with clip state
- [ ] 2.8 Add character workspace UI
- [ ] 2.9 Add loop-range/per-frame-duration playback
- [ ] 2.10 Add selected/active clip legacy export
- [ ] 2.11 Extend MCP with clip selectors and clip tools
- [ ] 2.12 Harden migration, rollback, stale-response, and isolation tests

### Phase 2 Checkpoint

- [ ] Multiple clips survive creation, repair, reload, and export
- [ ] Sibling clips remain unchanged by target mutations
- [ ] Existing no-clip-ID clients still work
- [ ] Full backend/frontend/MCP verification passes

## Phase 3: Character Bundles and Godot

- [ ] 3.1 Define generic character bundle V1
- [ ] 3.2 Add deterministic bundle ZIP and checksums
- [ ] 3.3 Add one-clip and all-enabled bundle scopes
- [ ] 3.4 Add bundle HTTP endpoint and frontend controls
- [ ] 3.5 Add direct MCP character-bundle export
- [ ] 3.6 Add Godot 4.7 AnimatedSprite2D profile/importer
- [ ] 3.7 Generate SpriteFrames resource and AnimatedSprite2D scene
- [ ] 3.8 Add pinned headless Godot CI validation
- [ ] 3.9 Package and document bundle/Godot contracts

### Phase 3 Checkpoint

- [ ] Same project revision produces byte-identical bundle
- [ ] Scope-specific failure gating passes
- [ ] Godot headless import/load assertions pass
- [ ] Full backend/frontend/MCP verification passes

## Phase 4: Action Packs, Recipes, CLI, and Batch

- [ ] 4.1 Define strict versioned action-pack models
- [ ] 4.2 Move current actions to bundled data pack
- [ ] 4.3 Add idle/run/attack/jump phases and declarative guides
- [ ] 4.4 Add ACTION_PACKS_DIR configuration
- [ ] 4.5 Add bounded non-executable external pack loading
- [ ] 4.6 Enforce reserved IDs and collision rejection
- [ ] 4.7 Persist action reference/version/digest/snapshot
- [ ] 4.8 Add custom text actions and first/last pose text
- [ ] 4.9 Define recipe V1 and project capture
- [ ] 4.10 Add sequential recipe runner with preflight
- [ ] 4.11 Install sprite CLI
- [ ] 4.12 Add atomic resumable sequential batch state
- [ ] 4.13 Add read-only MCP recipe tools
- [ ] 4.14 Publish validated examples and documentation

### Phase 4 Checkpoint

- [ ] External packs cannot execute code or access arbitrary paths
- [ ] Saved clips regenerate after source pack removal
- [ ] Recipe output contains no secrets/endpoints/environment paths
- [ ] Batch resume does not repeat completed provider calls
- [ ] CLI, backend, frontend, and MCP verification passes

## Phase 5: ComfyUI Local Provider

- [ ] 5.1 Add operation-specific provider capabilities
- [ ] 5.2 Declare Azure/Gemini capabilities without behavior changes
- [ ] 5.3 Add bounded loopback-only ComfyUI settings/readiness
- [ ] 5.4 Add strict workflow descriptor/compiler
- [ ] 5.5 Add upload/submit/poll/retrieve/decode adapter
- [ ] 5.6 Add queued cancellation and safe running-job drain behavior
- [ ] 5.7 Register cached provider in shared runtime
- [ ] 5.8 Add requirement preflight and seed plumbing
- [ ] 5.9 Add capability-aware HTTP/MCP metadata and UI
- [ ] 5.10 Add mocked workflow/transport/security tests
- [ ] 5.11 Add manual live acceptance harness
- [ ] 5.12 Document installation ownership and security boundary
- [ ] 5.13 Apply generation/edit/pose promotion gates

### Phase 5 Checkpoint

- [ ] CI passes without ComfyUI/GPU/models
- [ ] Loopback/proxy/redirect/output bounds pass
- [ ] Cancellation/timeout never commits project changes
- [ ] Live generation acceptance passes before generation support claim
- [ ] Identity edit acceptance passes before animation support claim
- [ ] Pose acceptance passes before pose-guided support claim
- [ ] Full backend/frontend/MCP verification passes

## Final Verification

- [ ] `backend`: `uv lock --check`
- [ ] `backend`: full pytest suite
- [ ] `backend`: `uv pip check`
- [ ] `frontend`: full Vitest suite
- [ ] `frontend`: production build
- [ ] `frontend`: production dependency audit
- [ ] MCP: credential-free stdio smoke
- [ ] Godot: pinned headless import/load smoke
- [ ] Repository: redacted secret scan
- [ ] Repository: dependency-license check
- [ ] Repository: `git diff --check`
- [ ] Manual: legacy project migration and complete character workflow
- [ ] Manual: configured cloud provider live acceptance
- [ ] Manual: ComfyUI promotion matrix for advertised capabilities
