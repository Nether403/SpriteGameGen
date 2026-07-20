# AI Sprite & Game Asset Tool

A locally-run web app that turns a text prompt (and optional reference image) into a
clean, engine-ready animated sprite sheet. Gemini (via Vertex AI / Google Agent
Platform) does the generative work; a deterministic Python pipeline handles background
removal, pixel-art quantization, sprite-sheet packing, and atlas metadata.

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
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service-account JSON key file |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID |
| `GOOGLE_CLOUD_REGION` | Vertex region (default `us-central1`) |
| `GEMINI_MODEL_GENERATE` | Stage 1 model (default `gemini-3.1-flash-image`) |
| `GEMINI_MODEL_EDIT` | Stage 2 model (default `gemini-3.1-flash-image`) |
| `PROJECTS_DIR` | Output dir (default `./projects`) |

> The service-account key must stay local — it is git-ignored (`project-*.json`) and
> must never be pushed.

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
- **Frontend** (`frontend/`): `npm test` — Vitest covers API request shaping, the
  `FrameStrip` regenerate/delete actions, and the `AnimationPlayer` loop timing math.
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

## Using the app

With both the backend (`uvicorn`) and frontend (`npm run dev`) running, open
http://localhost:5173 and work through the three steps:

1. **Generate** — describe the sprite, pick pixel/hi-res, optionally attach a reference.
2. **Animate** — choose an action preset and frame count, generate the cycle, preview the
   loop, and regenerate or delete any frames that came out inconsistent.
3. **Export** — pick JSON/XML atlas format, grid columns, and padding, then download the
   packed sheet + atlas.
