---
name: sprite-game-gen
description: Operates SpriteGameGen through its MCP server to inspect, generate, animate, curate, resume, and export sprite projects. Use when a user mentions SpriteGameGen, sprite-mcp, sprite:// resources, AI sprite generation, animation clips, sprite sheets, recipes, or character and Godot bundles.
license: Apache-2.0
compatibility: Requires an MCP client connected to the local SpriteGameGen sprite-mcp stdio server. Creative operations also require a configured image provider.
metadata:
  author: SpriteGameGen contributors
  version: "1.0.0"
---

# SpriteGameGen

Use the local MCP server as the source of truth. Client hosts may prefix or
namespace tool names; match the discovered tool whose final name is the direct
tool name documented here.

## Operating Loop

### 1. Discover

1. Find the SpriteGameGen MCP server and its tools in the host's MCP inventory.
2. If the server or tools are unavailable, read
   [references/setup.md](references/setup.md) and diagnose the connection before
   attempting another operation.
3. Call `get_capabilities` once at the start of a task that may generate or
   animate. Treat its provider availability, presets, camera directions, and
   limits as authoritative over examples or remembered values.
4. If the user may be resuming work, call `list_projects`, then `get_project`
   for the selected project.

Discovery is complete when the intended operation is compatible with the live
capabilities and the target project, if any, is unambiguous.

### 2. Bound The Side Effect

Classify the next call before making it:

| Class | Operations | Required handling |
|---|---|---|
| Read-only, local | Capability, project, and recipe reads | Run directly. |
| Billable, no overwrite | `enhance_prompt`, `generate_sprite` | Run only when the user has requested that exact creative action. |
| Billable and destructive | `animate`, `regenerate_frame` | Confirm the project/clip and replacement scope unless the user's request already authorizes them explicitly. |
| Local and destructive | Render, frame, clip, and export mutations | Confirm ambiguous targets; state what will be replaced or deleted. |

Prompt enhancement is a review gate, not an invisible preprocessing step. Show
the returned `enhanced_prompt` to the user and obtain acceptance before passing
it to `generate_sprite`.

Do not claim that MCP tool annotations enforce safety. They are behavior hints;
the table above and the live tool descriptions define the handling policy.

### 3. Execute The Smallest Workflow

Choose one branch:

**Create a project**

1. Select only a provider reported as available. `auto` is valid only for
   initial generation.
2. Validate `style`, `view_mode`, and `direction` against live capabilities.
3. Optionally enhance and review the prompt.
4. Call `generate_sprite` once and retain the returned project ID, revision,
   concrete provider, sprite resource URI, and outcome.

**Animate or repair**

1. Read the project first. Use its concrete provider, `active_clip_id`, and
   `clip_count`.
2. Decide the clip target before the billable call. With no existing clip,
   omitting `clip_id` creates the first clip. With an active clip, omitting
   `clip_id` replaces that active clip and deletes its superseded frame assets.
   Passing an existing ID replaces it; passing a fresh valid ID creates a clip
   and makes it active. Because direct project reads do not enumerate every clip
   ID, treat a caller-selected ID as a possible collision and obtain explicit
   authorization for that add/replace scope.
3. Choose a preset and frame count from `get_capabilities`. Do not invent an
   action name or exceed its frame range.
4. Call `animate` only with the intended clip behavior above, or
   `regenerate_frame` for one bad frame.
5. If animation returns `partial_failure`, preserve successful frames. Report
   each failed index and error, then offer two explicit choices: a targeted,
   billable `regenerate_frame`, or credential-free
   `set_frame_adjustment(enabled=false)` to omit that frame from exports while
   preserving its canonical index. Never rerun the whole animation
   automatically or disable a frame without confirmation.

**Curate locally**

1. Use `set_render_settings` for deterministic size, scale, and palette changes.
2. Use `set_frame_adjustment` for frame enable/disable and nudge changes. Treat
   `horizontal_flip` as clip-wide even though the call requires a frame index.
   `reset` zeroes the selected frame's nudges, re-enables that frame, and clears
   the clip-wide horizontal flip. State and confirm this full scope before
   either flip or reset.
3. Use `update_clip` for clip metadata. Use `delete_clip` only for an explicitly
   identified clip.

These operations do not call a provider, but they overwrite local derived state.

**Export or reproduce**

1. Ensure every selected clip has no enabled failed frames and at least one
   enabled usable frame. Regenerate failed frames or explicitly disable them
   before export.
2. Use `export_sheet` for a sheet, atlas, and frame archive.
3. Use `export_character_bundle` for a deterministic portable bundle. Request
   `godot4_animatedsprite2d` only when the user wants the Godot profile.
4. Use `get_project_recipe` to capture a credential-free recipe and
   `validate_recipe` before relying on external recipe JSON.

Read [references/tool-contract.md](references/tool-contract.md) when constructing
arguments or interpreting a result.

### 4. Verify

After every project mutation, call `get_project` and verify:

- The project ID and intended clip still match.
- The revision and updated state are returned.
- `health`, `resume_available`, and every frame `status` are understood.
- Failed frames have `path: null` and `resource_uri: null`; do not treat them as
  usable assets.
- A creative result's `outcome` is `complete`, `partial_failure`, or `failed` as
  expected.

For exports, verify the returned resource URIs and paths. Prefer `sprite://`
resources when the MCP client can read them; use absolute paths only when the
user or downstream local tool needs filesystem access.

Verification is complete when the result, side effects, failures, project
revision, and usable artifact locations have all been reported.

## Invariants

- Never pass arbitrary filesystem paths, reference-image paths, URLs, or
  credentials to MCP tools. Direct MCP generation does not accept image uploads.
- Send only documented fields. This server version may ignore unknown top-level
  arguments instead of rejecting them.
- Never parallelize mutations against the same project. Serialize creative calls
  by default to avoid project conflicts, provider throttling, and accidental
  duplicate billing.
- Do not describe `horizontal_flip` as frame-local. It changes clip metadata;
  the indexed frame is the one rerendered immediately. Re-read the project after
  flip or reset so later curation does not rely on stale clip state.
- `auto` resolves to a concrete provider during generation. Animation and frame
  regeneration use the provider stored on the project or clip and never silently
  fall back to another provider.
- Missing creative-provider credentials do not make startup, project reads,
  resources, deterministic curation, or exports unavailable.
- Absence from `tools/list` means an operation is not directly exported by this
  MCP server. It does not prove that no internal or remote-agent capability
  exists. Hyperagent is experimental and unavailable in the direct MCP path.
- Treat returned project IDs, existing clip IDs, frame indices, revisions, and
  resource URIs as opaque. A caller-selected clip ID is permitted only for a
  deliberate add flow whose possible collision/replacement effect was disclosed.

## Recovery

| Result or error | Response |
|---|---|
| Provider unavailable | Re-read capabilities. Choose another provider only for a new project; do not switch an existing project's provider. |
| `partial_failure` | Keep successful frames and report failed indices/codes. Offer confirmed targeted billable regeneration or confirmed credential-free disabling; disabled frames are omitted from exports but retain canonical indices. |
| Timeout with "no project changes were committed" | Re-read the project, reduce frame count or ask the operator to raise the server timeout, then retry only with authorization. |
| Project busy or changed | Re-read the project and retry once after the competing operation finishes, if the original intent still applies. |
| Validation or not-found error | Correct the exact ID, enum, bound, or required field; do not broaden filesystem access. |
| Unexpected server error with request ID | Preserve the request ID for operator logs and stop blind retries. |

## Report Format

Return a compact operation receipt:

```text
Operation: <tool or workflow>
Billing: none | provider call(s) requested
Project: <id> revision <revision>
Outcome: complete | partial_failure | failed
Artifacts: <resource URIs and any requested local paths>
Issues: <failed frame indices/errors or none>
Next safe action: <one concrete option or none>
```

Omit fields that genuinely do not apply, but never omit billing, partial
failures, or destructive effects.

## Example Sequences

New animated sprite:

```text
get_capabilities
generate_sprite
get_project
animate
get_project
export_character_bundle
```

Credential-free resume and export:

```text
list_projects
get_project
export_sheet
```

Repair a partial animation:

```text
get_project
regenerate_frame  # only the accepted failed index
get_project
```
