# Character Bundles and Godot

`sprite-character-bundle` V1 is a deterministic ZIP containing
`character.bundle.json`, `SHA256SUMS`, and normalized
`frames/<clip-id>/<index>.png` assets. The manifest records stable clip/action
identity, direction, durations, loop mode/range, pivot, baseline, source project
revision, and per-frame checksums. It excludes prompts, credentials, endpoints,
environment values, and absolute paths.

The default pivot is bottom-center `(0.5, 1.0)`. Frame indices remain their
canonical clip indices when disabled frames are omitted. `active`/`one` scope
validates only its selected clip; `all_enabled` validates every enabled clip
before writing.

The `godot4_animatedsprite2d` profile adds:

- `character_sprite_frames.tres`
- `character_animated_sprite_2d.tscn`
- `import_character_bundle.gd`

Extract the bundle into a Godot 4.7 project, allow textures to import, then open
the generated scene or run the editor script once to rescan sources. Keep pixel
textures unfiltered for crisp nearest-neighbor output. Godot support must not be
claimed by a release until the pinned headless import/load smoke passes.
