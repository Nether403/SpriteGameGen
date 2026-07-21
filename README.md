# AI Sprite & Game Asset Tool

A locally-run web app that turns a text prompt (and optional reference image) into a
clean, engine-ready animated sprite sheet. Azure GPT Image or Gemini (via Vertex AI /
Google Agent Platform) does the generative work; a deterministic Python pipeline handles background
removal, pixel-art quantization, sprite-sheet packing, and atlas metadata.
Side-scroller walks also provide Gemini with deterministic eight-phase pose guides,
so frames change limb geometry instead of merely restyling the same stance.

See the design spec in [`docs/superpowers/specs/`](docs/superpowers/specs/) and the
implementation plan in [`docs/superpowers/plans/`](docs/superpowers/plans/).

## Layout

```
backend/    FastAPI + deterministic image pipeline (Python 3.11+)
frontend/   React + Vite + TypeScript thin client
projects/   per-project output folders (git-ignored)
```

## Backend setup

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # then fill in the values below
pytest -q                   # run the test suite
uvicorn app.main:app --reload
```

### Environment / auth

This project authenticates to Gemini through **Vertex AI (Google Agent Platform)** using
a service-account JSON key — not a `GEMINI_API_KEY`. Set in `.env`:

| Var | Meaning |
|---|---|
| `SPRITE_ENV_FILE` | Optional absolute dotenv path. If omitted, the backend uses `backend/.env` regardless of process CWD. Relative paths inside the selected dotenv file resolve from that file's directory. |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service-account JSON key file (loaded explicitly; if unset, falls back to `gcloud` ADC) |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_CLOUD_REGION` | Vertex region (default `global`) |
| `GEMINI_MODEL_GENERATE` | Stage 1 model (default `gemini-3.1-flash-image`) |
| `GEMINI_MODEL_EDIT` | Stage 2 model (default `gemini-3.1-flash-image`) |
| `GEMINI_MODEL_TEXT` | Optional prompt-preview model (default `gemini-3.5-flash`) |
| `GEMINI_TIMEOUT_SECONDS` | Per-attempt Gemini request timeout (default `120`) |
| `GEMINI_MAX_RETRIES` | Maximum attempts for retryable Gemini failures (default `5`) |
| `GEMINI_BACKOFF_SECONDS` | Initial retry delay for non-quota failures; subsequent delays double (default `1`) |
| `GEMINI_QUOTA_BACKOFF_SECONDS` | Minimum delay after `429 RESOURCE_EXHAUSTED` before an automatic retry (default `15`) |
| `AZURE_OPENAI_ENDPOINT` | Optional Azure OpenAI resource or `/openai/v1` endpoint |
| `AZURE_OPENAI_API_KEY` | Azure API key; local secret, never commit it |
| `AZURE_OPENAI_DEPLOYMENT` | Azure deployment name, for example `gpt-image-2-2` |
| `AZURE_IMAGE_QUALITY` | `low`, `medium`, `high`, or `auto` (default `low`) |
| `AZURE_IMAGE_TIMEOUT_SECONDS` | Per-attempt Azure request timeout (default `180`) |
| `AZURE_IMAGE_MAX_RETRIES` | Maximum Azure attempts for retryable failures (default `2`) |
| `AZURE_IMAGE_MAX_CONCURRENCY` | Maximum concurrent Azure frame edits (default `3`) |
| `PROJECTS_DIR` | Output dir (default `./projects`). Relative values resolve from the selected dotenv file's directory, not the process CWD. |
| `MAX_UPLOAD_BYTES` | HTTP reference-image upload limit (default `10485760`); reported by MCP capabilities even though direct MCP generation does not accept image uploads. |

> The service-account key must stay local — it is git-ignored (`project-*.json`) and
> must never be pushed.

> **Region note:** Gemini 3.x image models (`gemini-3.1-flash-image`, `gemini-3-pro-image`)
> are served from the **`global`** endpoint, not a regional one like `us-central1` — a
> regional endpoint returns a 404 "model not found in region".

> **First run:** `rembg` downloads its ~170 MB background-removal model on first use, so
> the first generate/animate call is slow. The `onnxruntime` inference backend is a
> declared dependency (installed via `pip install -e ".[dev]"`).

## Frontend setup

```bash
cd frontend
npm install
npm run dev     # dev server on http://localhost:5173
npm run build
```

## Testing

- **Pipeline** (`backend/tests/`): pure unit tests against committed fixtures — fast,
  free, deterministic.
- **Gemini client**: tested against a mocked SDK; no real API calls in CI.
- **Frontend** (`frontend/`): `npm test` — Vitest covers API request shaping, project
  browser resume/delete behavior, Zustand hydration, `FrameStrip` regenerate/delete
  actions, and the `AnimationPlayer` loop timing math.
- **Live smoke test**: makes real Gemini calls, **manual only** (kept out of `pytest`).
  Run it from the backend venv after configuring `.env`:

  ```bash
  cd backend
  # Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
  python ../scripts/smoke_generate.py "a knight with a sword"
  ```

  It generates a base sprite, edits it into one walk frame, runs the pipeline, and
  writes the results to `scripts/smoke_out/` (git-ignored) for inspection. Use this to
  confirm the live model IDs and SDK signatures still match after any dependency bump.

- **Live model validation matrix**: probes the configured prompt, generation, and edit
  models by region; records availability, latency, optional safety-block behavior, and
  raw/processed artifacts for a scored manual quality review. It is billable, opt-in,
  outside CI, and writes to a disposable git-ignored directory. See
  [`docs/live-model-validation.md`](docs/live-model-validation.md) for the supported
  model/region table and acceptance rubric.

  ```powershell
  cd backend
  .venv\Scripts\python.exe ..\scripts\validate_live_models.py --repeats 3 --include-block-probe
  ```

## Using the app

With both the backend (`uvicorn`) and frontend (`npm run dev`) running, open
http://localhost:5173. The saved-project browser loads local projects first; open a
healthy project to restore its prompt, sprite, animation frames, and export workflow.
Then work through the three steps:

1. **Generate** — describe the sprite, pick pixel/hi-res and a game camera, then choose
   an allowed direction. Prompt enhancement is optional: request a visible preview,
   edit it, and explicitly accept it before generation. Choose Auto, Azure, or Gemini;
   Auto prefers Azure when configured. Hyperagent is shown as Experimental but remains
   disabled until its agent-mediated image path is validated. You can also attach a reference.
2. **Animate** — choose an action preset, direction, and frame count, generate the cycle,
   preview the loop, and regenerate or delete any frames that came out inconsistent.
   Side-scrollers allow left/right; top-down/2.5D projects allow all eight directions.
3. **Export** — pick JSON/XML atlas format, grid columns, and padding, then download the
   packed sheet + atlas.

## Local MCP server

The backend installs `sprite-mcp`, a local stdio MCP server backed by the same
synchronous `SpriteService`, `ProviderRegistry`, and project store as FastAPI. Startup is
storage-only safe: initialization, capability discovery, project reads, and resource reads
do not require cloud credentials. A creative tool fails with a safe tool error if its
required provider is not configured.

After installing the backend, register it in an MCP client using the console script:

```json
{
  "mcpServers": {
    "sprite-game": {
      "command": "D:\\SpriteGameGen\\backend\\.venv\\Scripts\\sprite-mcp.exe",
      "env": {
        "SPRITE_ENV_FILE": "D:\\SpriteGameGen\\backend\\.env",
        "PROJECTS_DIR": "D:\\SpriteGameGen\\projects"
      }
    }
  }
}
```

`SPRITE_ENV_FILE` must be absolute. `PROJECTS_DIR` should also be absolute in an MCP
client configuration so behavior is explicit even when the client launches the server
from a foreign working directory.

### Direct MCP contract

The exact direct tool inventory is:

| Tool | Provider/billing effect | Local overwrite effect |
|---|---|---|
| `get_capabilities` | None | None |
| `list_projects` | None | None |
| `get_project` | None | None |
| `enhance_prompt` | Gemini text call; may incur provider billing | None |
| `generate_sprite` | One image-generation call through `auto`, `azure`, or `gemini`; may incur provider billing | Creates a new project; does not overwrite an existing project |
| `animate` | Multiple image-edit calls through the provider stored on the project; may incur provider billing | Replaces prior animation frames and animation metadata |
| `regenerate_frame` | One image-edit call through the provider stored on the project; may incur provider billing | Replaces the selected frame |
| `export_sheet` | No provider call or provider billing | Replaces the matching local sprite sheet and atlas outputs |

`auto` prefers Azure when configured and otherwise uses Gemini, but only during initial
generation. The resolved concrete provider is persisted. `animate` and
`regenerate_frame` always use that stored provider and return an error if it is no longer
configured; they never silently switch providers.

`get_capabilities` reports application version `0.1.0`, provider availability, action
presets, camera/direction combinations, and all prompt, upload, decoded-image, export,
sheet, and frame-error limits. FastMCP 1.28.1 does not expose a public FastMCP constructor
argument for the application version, so the application version is reported here rather
than in the MCP initialization server-version field.

Project outputs are MCP-specific DTOs. They include revision, concrete provider,
operation outcome, frame status/errors, absolute local paths, and `sprite://` resource
URIs, but never expose the persisted/browser-only `Frame.url` field. The server publishes
two read-only resource templates:

```text
sprite://projects/{project_id}/manifest
sprite://projects/{project_id}/assets/{filename}
```

Both resolve through the canonical `PROJECTS_DIR` store and reject unsafe IDs, filenames,
symlink escapes, and traversal. The server does not accept arbitrary filesystem paths or
reference-image paths.

FastMCP 1.28.1 generates useful input schemas from `Annotated`/Pydantic constraints, but
its public tool decorator does not provide a strict-extra option. Unknown top-level tool
arguments are therefore ignored by the SDK's generated argument model. This limitation is
covered by a contract test; the server does not patch private SDK internals.

### Capability boundaries

The eight tools above are the complete set exported directly by this MCP server. The web
application also has HTTP-only operations such as reference-image upload and frame delete,
and `SpriteService` contains internal operations used by those routes. Their absence from
MCP `tools/list` means they are not direct MCP tools, not that the product lacks those
capabilities.

Hyperagent remains an experimental remote-agent capability. It appears in provider
capability metadata as unavailable, but it is not accepted by direct MCP generation and is
not an exported tool. Its authenticated, agent-mediated image path still requires separate
validation; do not infer remote-agent capability from the direct server's tool inventory.

Run the credential-free protocol smoke test from the repository root:

```powershell
backend\.venv\Scripts\python.exe scripts\smoke_mcp.py
```

The smoke script launches the installed `sprite-mcp` console entrypoint from a temporary
foreign CWD with absolute temporary `SPRITE_ENV_FILE` and `PROJECTS_DIR` values, removes
cloud credentials, initializes stdio, asserts the exact tool inventory, calls
`get_capabilities`, and prints only its parent-process success line.
