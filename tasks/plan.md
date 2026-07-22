# Implementation Plan: Local-First Character Animation Workbench

## Overview

Evolve SpriteGameGen from a stable single-animation generator into a local-first,
provider-neutral character animation workbench. The completed product will retain
deterministic repair sources, preserve multiple clips per character, export versioned
engine-ready bundles, load data-only action packs, replay workflows through recipes and
CLI automation, and optionally use an independently operated local ComfyUI server.

Work is delivered in six independently verifiable phases. Every phase must leave the
existing Generate -> Animate -> Export path usable and keep old filesystem projects
readable. CI remains credential-free; live provider checks stay manual and opt-in.

## Locked Decisions

| Area | Decision |
|---|---|
| License | Apache-2.0 |
| Copyright holder | SpriteGameGen contributors |
| First engine profile | Godot 4.7 AnimatedSprite2D/SpriteFrames |
| First local provider | ComfyUI |
| ComfyUI network boundary | Loopback only |
| Action extensions | Strict installable JSON data packs |
| Executable plugins | Not supported |
| Persistence | Revision-checked filesystem projects remain canonical |
| SaaS concerns | No accounts, billing, database, cloud sync, or remote MCP |

## Cross-Phase Architecture

### Canonical Manifest V2

Phase 1 introduces the only broad persistence migration needed by this roadmap:

```text
Project
  schema_version / revision / timestamps
  generation prompt and provider provenance
  style / view mode / base direction
  pixel quality profile
  project pivot and baseline
  clips: map<clip_id, AnimationClip>
  active_clip_id
  recipe provenance

AnimationClip
  stable ID and user-visible name
  action reference or inline action snapshot
  direction / FPS / loop mode and range
  enabled / horizontal correction
  frames / provider provenance / timestamps

AnimationFrame
  stable positional index
  source and rendered filenames
  enabled / nudge_x / nudge_y / duration_ms
  status / safe error / generation provenance
```

- Clip IDs are project-scoped UUID-derived safe identifiers, not action names.
- Multiple variants of the same action and direction are allowed.
- Browser URLs are reconstructed by adapters and never persisted.
- Reads migrate old manifests in memory without rewriting them.
- The first successful mutation writes V2 and clip-scoped assets atomically.
- Unsupported future schema versions are never downgraded.
- HTTP and MCP retain active-clip compatibility projections for one release window.

### Source and Rendered Assets

New projects retain cleaned, pre-quantization sources separately from current output:

```text
source_sprite.png
source_clip_<clip-id>_0000.png
clip_<clip-id>_0000.png
```

Every quality change renders from `source_*`. Legacy projects bootstrap a source from
their current PNG only on the first deterministic mutation; colors already removed by
legacy quantization cannot be recovered.

### Versioned Public Formats

Application package version, manifest schema, character bundle format, action-pack
format, recipe format, and batch-state format evolve independently. A package release
must not silently change any persisted/public format without a compatibility rule.

## Delivery Rules

- Implement one small vertical slice at a time and run its focused tests before moving on.
- New behavior is test-first; documentation/config-only changes do not require artificial tests.
- Never make provider calls from automated tests or CI.
- Never expose credentials, environment values, workflow bodies, or arbitrary upstream errors.
- Do not dual-write legacy and canonical manifest fields; compatibility lives in adapters.
- Do not commit local generated projects, provider output, browser capture logs, or credentials.
- Do not commit, push, tag, or publish releases unless explicitly requested.

## Phase 0: Open-Source Foundation

### Goals

- Make the repository legally open source and contributor-ready.
- Make local setup diagnosable without revealing secrets.
- Add supply-chain and secret checks while preserving the existing build.

### Tasks

1. Add Apache-2.0 `LICENSE` and contributor `NOTICE`.
2. Add license/project metadata to Python and npm manifests.
3. Add `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and PR/issue templates.
4. Replace machine-specific example credential paths with generic placeholders.
5. Add redacted secret scanning and narrowly documented test allowlists.
6. Add runtime dependency-license policy and `THIRD_PARTY_NOTICES.md`.
7. Add a credential-safe `scripts/doctor.py` readiness command.
8. Harden CI with immutable action pins, concurrency cancellation, security checks, and dependency automation.
9. Add `CHANGELOG.md` and document independent version contracts.
10. Update onboarding and release documentation.

### Acceptance

- GitHub/license tooling recognizes Apache-2.0.
- Contributor and security paths are discoverable from README.
- The doctor reports runtimes, storage, and provider readiness without printing values.
- CI requires no cloud/local-model credentials and still passes on Windows and Linux.
- No tracked file contains a live credential or machine-specific credential filename.

### Verification

```powershell
git diff --check
gitleaks detect --source . --redact --no-banner
Set-Location backend
uv lock --check
uv run pytest -q
uv pip check
uv run python ..\scripts\doctor.py
Set-Location ..\frontend
npm ci
npm test
npm run build
npm audit --omit=dev --audit-level=high
```

## Phase 1: Deterministic Quality and Repair

### Goals

- Reduce paid rerolls with reversible local controls.
- Establish Manifest V2 and source/render separation.
- Export enabled individual frames as a deterministic ZIP.

### Tasks

1. Add strict V2 models and a pure version-dispatched manifest migration.
2. Reject future schemas and malformed/non-contiguous legacy frame mappings safely.
3. Add a pure bottom-center frame compositor with clip flip and integer nudges.
4. Extend pixel processing with target logical size, output scale, color limits, shared-auto palettes, preset palettes, and custom palettes.
5. Persist source and rendered base assets in one revision-checked commit.
6. Persist source and rendered clip frames; rerender shared-palette outputs after regeneration.
7. Add provider-free render-settings and frame-adjustment service operations.
8. Add HTTP routes for quality, flip, enable/disable, nudge, and reset.
9. Make sheet/atlas export include only enabled successful frames while preserving original indices.
10. Add deterministic, bounded `frames.zip` generation and atomic blob commits.
11. Add frontend quality controls and a project repair panel.
12. Replace normal destructive frame deletion with enable/disable, nudge, reset, and regenerate controls.
13. Add frontend-only checker/light/dark/green/magenta preview backgrounds.
14. Return sheet, atlas, and frame ZIP links from the export UI.
15. Extend MCP DTOs/capabilities, then add `set_render_settings` and `set_frame_adjustment`.
16. Complete live directional correction acceptance.

### Acceptance

- Identical source/profile input produces byte-identical output.
- Quality/repair operations make no provider call.
- Repeated transforms never compound because rendering starts from source assets.
- Disabled failed frames do not block export; enabled failed frames do.
- Frame indices and source files survive enable/disable/reset operations.
- Legacy projects remain readable and upgrade only on mutation.

### Verification

```powershell
Set-Location backend
uv run pytest tests/test_manifest_migrations.py tests/test_frame_render.py -q
uv run pytest tests/test_pixelate.py tests/test_sprite_service.py -q
uv run pytest tests/test_routes_animate.py tests/test_export_multi.py -q
uv run pytest tests/test_mcp_server.py -q
Set-Location ..\frontend
npm test
npm run build
```

## Phase 2: Character Animation Workspace

### Goals

- Preserve multiple independently editable clips per character.
- Keep active-clip compatibility for current HTTP, UI, and MCP callers.

### Tasks

1. Add a framework-neutral clip workspace for create, replace, select, update, and delete.
2. Namespace all new frame/export assets by stable clip ID.
3. Add canonical clip and clip-frame HTTP routes.
4. Preserve `/animate`, frame mutation, and no-selector export as active-clip adapters.
5. Add clip name, direction, FPS, loop/once mode, loop range, enabled state, durations, and provenance.
6. Add clip-aware project summaries and health checks.
7. Replace singular frontend animation state with a clip map and active projection.
8. Add character workspace UI for selecting, creating, renaming, replacing, enabling, and deleting clips.
9. Make preview playback loop-range and per-frame-duration aware.
10. Make export target one clip or the active clip without sibling interference.
11. Extend MCP inputs with optional clip IDs and add clip metadata/delete tools.
12. Harden legacy migration, rollback, stale-response, and cross-clip isolation tests.

### Acceptance

- Creating or replacing a clip never changes sibling assets or metadata.
- Clip selection survives reload.
- Late frontend responses cannot mutate another project or clip.
- Deleting a clip removes only its owned assets in the same transaction.
- Existing calls without a clip ID continue against the active clip.

### Verification

```powershell
Set-Location backend
uv run pytest tests/test_routes_clips.py tests/test_routes_animate.py -q
uv run pytest tests/test_export_workspace.py tests/test_mcp_server.py -q
Set-Location ..\frontend
npm test
npm run build
```

## Phase 3: Character Bundles and Godot

### Goals

- Export a complete, deterministic character package.
- Ship one tested Godot 4.7 AnimatedSprite2D integration.

### Tasks

1. Define strict engine-neutral `sprite-character-bundle` V1 models.
2. Add deterministic ZIP creation with manifest, checksums, and normalized frames.
3. Support one-clip and all-enabled scopes without changing legacy `/export`.
4. Add `POST /exports/character-bundle` and frontend bundle controls.
5. Add direct MCP `export_character_bundle`.
6. Add the `godot4_animatedsprite2d` profile and one-shot GDScript importer.
7. Generate `character_sprite_frames.tres` and `character_animated_sprite_2d.tscn`.
8. Add pinned Godot 4.7 headless import/load assertions in CI.
9. Package the helper and document bundle coordinates, limits, compatibility, and Godot import settings.

### Bundle Layout

```text
character.bundle.json
SHA256SUMS
frames/<clip-id>/0000.png
frames/<clip-id>/0001.png
```

The manifest includes clip/action/direction, duration, loop, pivot/baseline, frame
index, provider/action provenance, and checksums. It excludes prompts by default,
credentials, provider endpoints, environment values, and absolute local paths.

### Acceptance

- Re-exporting the same project revision produces byte-identical ZIP output.
- Single-clip export can succeed despite failures in unselected clips.
- All-enabled export fails before writing if selected clips are incomplete.
- Godot headless validation proves names, frame order, durations, loops, textures, and pivot.

### Verification

```powershell
Set-Location backend
uv run pytest tests/test_character_bundle.py tests/test_export_bundle.py -q
uv run pytest tests/test_godot_profile.py tests/test_mcp_server.py -q
godot --headless --path <temporary-project> --script <import-test-script>
Set-Location ..\frontend
npm test
npm run build
```

## Phase 4: Action Packs, Recipes, CLI, and Batch

### Goals

- Deepen animation choreography through safe data extensions.
- Make workflows versionable, replayable, and automatable.

### Tasks

1. Define strict versioned action-pack/action/phase/guide models with `extra=forbid`.
2. Move built-ins into a bundled V1 pack and preserve current behavior first.
3. Add distinct idle, run, attack, and jump phases and declarative pose guides.
4. Add optional `ACTION_PACKS_DIR` resolution relative to the selected dotenv file.
5. Load immediate regular JSON files only; reject symlinks, recursion, oversize content, duplicate keys, and collisions.
6. Reserve built-in IDs and reject all colliding external packs without affecting valid unrelated packs.
7. Persist action references, versions, digests, and complete snapshots on generated clips.
8. Add custom text actions with motion, optional first/last pose text, frames, FPS, and loop choice.
9. Define canonical credential-free recipe V1 and project capture.
10. Add a sequential recipe runner over `SpriteRuntime` with complete preflight.
11. Install the `sprite` CLI with doctor, actions, recipe validate/capture/run, and batch commands.
12. Add atomic, locked, resumable batch state with recipe digests and no duplicate billing on resume.
13. Add read-only direct MCP `validate_recipe` and `get_project_recipe` tools.
14. Publish validated example packs/recipes and format documentation.

### Acceptance

- Action packs are data only and can never import/execute code or access paths/URLs.
- Regeneration uses the clip's saved action snapshot after pack changes/removal.
- Recipes contain no endpoint, credential, environment dump, or arbitrary filesystem path.
- Recipe preflight completes before the first provider call.
- Batch execution is sequential and resumes without repeating completed provider calls.
- CLI machine output is stdout; progress and safe diagnostics are stderr.

### Verification

```powershell
Set-Location backend
uv run pytest tests/test_action_catalog.py tests/test_prompt_builder.py -q
uv run pytest tests/test_custom_actions.py tests/test_recipes.py -q
uv run pytest tests/test_recipe_runner.py tests/test_recipe_batch.py -q
uv run pytest tests/test_cli.py tests/test_mcp_server.py -q
uv run sprite doctor
uv run sprite actions list
uv run sprite recipe validate ..\examples\recipes\knight.v1.json
```

## Phase 5: ComfyUI Local Provider

### Goals

- Add a capability-aware local image provider without bundling inference infrastructure.
- Promote only the operations that pass live identity and pose quality gates.

### Tasks

1. Add operation-specific provider capabilities and requirement-aware selection.
2. Add explicit Azure/Gemini capabilities without changing current payloads.
3. Add bounded loopback-only ComfyUI settings and static readiness.
4. Define a strict operator-owned workflow descriptor and API-format template compiler.
5. Implement upload, submit, history polling, output retrieval, and bounded image decoding using `httpx`.
6. Add safe cancellation: delete queued app-owned prompt IDs; never use global `/interrupt`.
7. Retain the provider slot while cancelled running work drains; mark the provider not ready if safe drain cannot be confirmed.
8. Register one cached provider in HTTP/MCP runtime and preserve concrete stored-provider behavior.
9. Preflight generate/edit/identity/pose/seed requirements before any provider call or mutation.
10. Add capability-aware HTTP metadata and frontend provider selection.
11. Add comprehensive mocked workflow, transport, abuse-case, timeout, cancellation, and no-commit tests.
12. Add a manual production-adapter live validation harness and quality report.
13. Document external installation ownership, trusted workflow/node risk, loopback policy, and readiness troubleshooting.

### Capability Rules

- Static generation requires `generate`.
- Generation with a reference also requires identity-reference support.
- Animation/regeneration require edit and identity-reference support.
- Pose-guided actions require a distinct pose-reference binding.
- Explicit seeds require a real seed binding; unsupported seeds are never ignored.
- `auto` preserves Azure -> Gemini -> ComfyUI priority for compatibility.
- Stored concrete providers never silently fall back.

### Security Boundary

- Permit only localhost, `127.0.0.0/8`, or `::1` with an explicit port.
- Disable environment proxies and redirects.
- API/MCP callers cannot provide URLs, workflows, node IDs, model names, or paths.
- The app never starts ComfyUI, installs nodes/models, downloads checkpoints, or manages CUDA.
- Workflows/custom nodes are trusted local code and require operator review.
- `/interrupt` is global and is not used; queued prompt-ID deletion is used only for app-owned pending work.

### Promotion Gates

- Generation passes, edit fails: generation-only provider.
- Edit passes, pose fails: non-pose actions only.
- Any critical identity failure: no animation support.
- Persistent pose-guide leakage or frozen stances: no pose-guided support.
- If acceptable operation requires bundled models/custom nodes: stop the phase scope.

### Verification

```powershell
Set-Location backend
uv run pytest tests/test_comfyui_workflow.py tests/test_comfyui_provider.py -q
uv run pytest tests/test_provider_selection.py tests/test_sprite_service.py -q
uv run pytest tests/test_routes_animate.py tests/test_mcp_server.py -q
Set-Location ..\frontend
npm test
npm run build
```

Manual release validation:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe ..\scripts\validate_comfyui.py --preflight
.\.venv\Scripts\python.exe ..\scripts\validate_comfyui.py --repeats 3 --frames 8
```

## Dependency Graph

```text
Phase 0: license, governance, CI, doctor
  -> Phase 1: Manifest V2, source/render separation, deterministic repair
     -> Phase 2: multi-clip service, API, state, UI
        -> Phase 3: generic bundle and Godot profile
           -> Phase 4: action snapshots, packs, recipes, CLI, batch
              -> Phase 5: capability-aware providers and ComfyUI
```

## Full Definition of Done

- Focused tests pass for every increment.
- Backend full suite, lock check, and dependency compatibility pass.
- Frontend full suite, production build, and production dependency audit pass.
- MCP credential-free stdio smoke passes with the documented exact inventory.
- Existing persisted projects remain readable and mutate safely.
- CI performs no provider calls and requires no provider credentials.
- New persistent/public formats have explicit versions and deterministic fixtures.
- No provider input is silently ignored.
- No secrets, environment values, generated projects, browser captures, or workflow bodies enter committed output.
- User-visible errors distinguish validation, configuration, provider, cancellation, conflict, and partial-output failures.
- Documentation changes ship with the public contract they describe.
- Live provider and Godot gates pass before support claims are promoted.
