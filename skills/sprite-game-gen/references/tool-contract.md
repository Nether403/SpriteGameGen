# Direct MCP Contract

This is a compact reference for SpriteGameGen 0.1.0. Always prefer the live
tool schemas and `get_capabilities` because later application and format
versions evolve independently.

## Tools

| Tool | Inputs | Effect |
|---|---|---|
| `get_capabilities` | none | Read-only, credential-free. Returns app version, provider status/capabilities, presets, camera directions, and limits. |
| `list_projects` | none | Read-only, credential-free. Returns project health, counts, resume state, thumbnail, and manifest URI. |
| `get_project` | `project_id` | Read-only, credential-free. Returns project/frame state plus sprite paths and URIs. |
| `enhance_prompt` | `prompt`, `style`, optional `view_mode`, `direction` | Billable Gemini text call; no overwrite. |
| `generate_sprite` | `prompt`, `style`, optional `view_mode`, `direction`, `enhanced_prompt`, `provider`, `seed` | Billable image call. Creates a new project without overwriting another project. |
| `animate` | `project_id`, `action`, optional `direction`, `frames`, `fps`, `clip_id`, `clip_name`, `seed` | Billable image edits. Omitted `clip_id` creates the first clip only when none is active; otherwise it replaces the active clip. A supplied ID replaces that clip or creates it if unused. Superseded frame assets are deleted. |
| `regenerate_frame` | `project_id`, `index`, optional `clip_id` | One billable image edit. Replaces one frame. |
| `export_sheet` | `project_id`, optional `format`, `padding`, `cols`, `clip_id` | Credential-free deterministic pack. Rejects any enabled failed frame and requires an enabled usable frame. Replaces matching sheet, atlas, and frame archive. |
| `set_render_settings` | `project_id`, optional `target_width`, `target_height`, `output_scale`, `color_limit`, `palette_mode`, `preset_palette`, `custom_palette` | Credential-free rerender from retained sources. |
| `set_frame_adjustment` | `project_id`, `index`, optional `clip_id`, `enabled`, `nudge_x`, `nudge_y`, `horizontal_flip`, `reset` | Credential-free curation. Enable and nudge are frame-local. Horizontal flip is clip-wide; reset clears selected-frame nudges, re-enables it, and clears the clip-wide flip. |
| `update_clip` | `project_id`, `clip_id`, optional `name`, `fps`, `enabled`, `loop_mode` | Credential-free clip metadata update. |
| `delete_clip` | `project_id`, `clip_id` | Credential-free destructive deletion of clip-owned state and assets. |
| `export_character_bundle` | `project_id`, optional `scope`, `clip_id`, `engine_profile` | Credential-free deterministic bundle export. Rejects enabled failed frames in selected clips and omits disabled frames. Replaces matching bundle ZIP. |
| `validate_recipe` | `recipe_json` | Read-only strict recipe validation and digest. |
| `get_project_recipe` | `project_id` | Read-only recipe capture and digest. |

## Resources

```text
sprite://projects/{project_id}/manifest
sprite://projects/{project_id}/assets/{filename}
```

The manifest is sanitized JSON. Asset resources return bytes. Both resolve only
inside the canonical project store and reject unsafe IDs, traversal, and symlink
escapes. Do not synthesize filenames when a result already provides a resource
URI.

## Core Values

```text
style:          pixel | hires
view_mode:      side_scroller | top_down_2_5d
side directions:left | right
top-down dirs:  left | right | up | down | up_left | up_right | down_left | down_right
provider:       auto | azure | gemini | comfyui
export format:  json | xml
loop mode:      loop | once
palette mode:   auto | shared_auto | preset | custom
bundle scope:   active | one | all_enabled
engine profile: godot4_animatedsprite2d
outcome:        complete | partial_failure | failed
frame status:   ok | failed
frame errors:   provider | safety | background | empty | pixelate
project health: ready | incomplete | corrupt
```

Hyperagent can appear in provider capability metadata but is not accepted by
direct `generate_sprite` and is not runtime-ready.

## Important Bounds

- Prompt length: 1 to 2000 characters
- Animation frames: 2 to 8, further constrained by the selected preset
- FPS: 1 to 60
- Export padding: 0 to 256 pixels
- Export columns: 1 to 64 when specified
- Render target width/height: 1 to 1024 when specified
- Output scale: 1 to 16
- Color limit: 1 to 256
- Frame nudge: -4096 to 4096 on each axis
- Clip IDs and project IDs: server-returned alphanumeric, underscore, or hyphen
- Custom palette colors: `#RRGGBB`

Built-in presets are currently `idle`, `walk`, `run`, `attack`, and `jump`, but
action packs can add live presets. Use `get_capabilities` for their actual frame
ranges and defaults.

## Result Interpretation

Structured results include absolute local paths and `sprite://` URIs. Project
DTOs include revision, concrete provider, schema version, timestamps, active
clip, and frame state. They intentionally omit persisted browser-only frame
URLs.

An animation may succeed overall with `partial_failure`. Every failed frame has
a stable `error_code`, a safe message, and no usable path or URI. Disabled frame
indices remain canonical when exports omit their assets. Before export, either
regenerate enabled failed frames with a provider call or explicitly disable them
without a provider call. `export_sheet` also requires at least one enabled usable
frame in the target clip.

`set_frame_adjustment` always requires an index, but not every option is
frame-local. `horizontal_flip` changes clip metadata while rerendering the
indexed frame immediately. `reset` clears that clip-wide flip in addition to
resetting and enabling the indexed frame. Agents must disclose that wider scope
before either operation and re-read the project afterward.

`animate` resolves its target as `clip_id`, then the active clip ID, then a new
server-generated ID. Therefore omission is safe for creating only the first
clip. Direct project reads expose the active ID and total count, not every clip
ID, so a caller-selected ID cannot be proven unused through this direct MCP
contract. Disclose possible replacement before using one to add a clip.

Tool input schemas are constrained, but this server's FastMCP version may ignore
unknown top-level arguments. Build calls from the discovered schema and never
use speculative keys.
