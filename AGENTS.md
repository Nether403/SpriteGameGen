# Repository guidance

- When auditing an MCP-backed product, distinguish tools exported directly by the MCP
  server from tools available internally to remote agents. Absence from `tools/list`
  does not prove that the product lacks that capability.

## Cursor Cloud specific instructions

Two services: `backend/` (FastAPI, managed by `uv`) and `frontend/` (React + Vite).
The update script keeps deps fresh via `uv sync` (backend) and `npm ci` (frontend); `uv`
installs to `~/.local/bin` (already on `PATH` via `~/.bashrc`).

- Backend runs credential-free: startup, storage, project reads, export/pack pipeline,
  and the MCP contract do not need cloud keys. Only the creative image providers
  (Gemini/Vertex, Azure OpenAI, ComfyUI) require config in `backend/.env`; without them
  `/ready` reports providers unavailable and `generate`/`animate` return provider errors
  by design — this is expected, not a setup failure.
- Run both from their own dirs (see `README.md`): backend `uv run uvicorn app.main:app
  --reload` on :8000, frontend `npm run dev` on :5173. Vite proxies API paths to :8000,
  so open the app at http://localhost:5173.
- Standard checks live in `README.md`/`CONTRIBUTING.md`: backend `uv run pytest`,
  `uv run python ../scripts/doctor.py`, `uv run python ../scripts/smoke_mcp.py`;
  frontend `npm test` and `npm run build`. Backend tests must stay deterministic and must
  not make paid provider calls (mock providers, as existing tests do).
- Provider rate limits (when real keys are configured): Azure ~10 images/min, Vertex/Gemini
  ~2 images/min. Pace live generate/animate runs accordingly (animate makes one image call
  per frame), especially on Vertex.
- To exercise the credential-free creative core end-to-end without paid APIs, follow the
  test pattern: `create_app(remover=<fake>)` with `get_gemini_client` overridden by a fake
  provider (see `backend/tests/test_export_multi.py`), then generate/animate/export. This
  writes real frames a running server can then pack/export (sheet, atlas, frames ZIP,
  Godot bundle).
