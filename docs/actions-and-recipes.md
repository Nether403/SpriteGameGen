# Action Packs, Recipes, and CLI

Action-pack V1 files are strict JSON data. SpriteGameGen reads only immediate
regular `.json` files from `ACTION_PACKS_DIR`; it does not recurse, follow
symlinks, import modules, execute code, or access pack-supplied paths/URLs.
Files are size-bounded, duplicate keys and unknown fields are rejected, and
built-in IDs are reserved. One invalid pack does not remove unrelated valid
packs.

Generated clips retain the action reference, version, canonical digest, and a
complete snapshot so regeneration survives source-pack changes or removal.

Recipe V1 is strict, credential-free JSON. It records generation context,
render settings, clips, and exports, but never endpoints, credentials,
environment dumps, or arbitrary paths. The runner preflights the entire recipe
before its first provider call. Batch state is locked and atomically replaced;
completed entries are skipped and interrupted `running` entries become
`indeterminate` rather than risking duplicate billing.

```powershell
cd backend
uv run sprite doctor
uv run sprite actions list
uv run sprite recipe validate ..\examples\recipes\knight.v1.json
uv run sprite recipe capture <project-id> --output recipe.json
uv run sprite recipe run recipe.json
uv run sprite batch batch-state.json recipe.json
```

Machine-readable results use stdout. Safe progress and errors use stderr.
