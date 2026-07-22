# Contributing to SpriteGameGen

Thank you for helping improve SpriteGameGen. Contributions should be focused,
tested, and safe to run locally and in CI.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Security vulnerabilities must be reported through the private process in
[SECURITY.md](SECURITY.md), not through a public issue.

## Before You Start

- Search existing issues and pull requests before opening a duplicate.
- Open an issue before a large change so its scope and approach can be agreed.
- Keep unrelated refactors and generated output out of the change.
- Do not commit local projects, generated images, build output, or credentials.

## Backend Development

The backend requires Python 3.11 or newer and uses `uv` with the committed
lockfile.

```bash
cd backend
uv sync --locked --extra dev
uv run pytest
uv run uvicorn app.main:app --reload
```

Run `uv lock --check` after dependency-related work. If dependencies were
intentionally changed, update the lockfile in the same pull request and explain
the reason.

Backend tests must be deterministic and must not make paid provider calls.
Mock Azure OpenAI, Gemini, and other external services in automated tests.

## Frontend Development

The frontend uses Node.js, npm, React, TypeScript, Vite, and Vitest.

```bash
cd frontend
npm ci
npm test
npm run build
npm run dev
```

Use `npm ci` for a clean install from the committed lockfile. Keep API contract
changes synchronized with the backend and cover user-visible behavior with
tests where practical.

## Credential and Provider Safety

- Never commit `backend/.env`, service-account JSON files, API keys, access
  tokens, private endpoints, or copied request headers.
- Use `backend/.env.example` only as a template. Put real values in a local
  `backend/.env` or another local file selected with `SPRITE_ENV_FILE`.
- Treat `GOOGLE_APPLICATION_CREDENTIALS` files and `AZURE_OPENAI_API_KEY` as
  secrets. Redact them from logs, screenshots, fixtures, issue reports, and
  pull requests.
- Use synthetic prompts and assets that are safe to share in tests and issue
  reproductions.
- Live smoke tests and model validation are opt-in, can incur provider charges,
  and must never be added to the default test suite or CI without prior
  agreement.
- If a secret is exposed, revoke or rotate it immediately and report the
  incident using the private process in `SECURITY.md`.

## Pull Requests

Before submitting a pull request:

1. Run `uv run pytest` from `backend` for backend changes.
2. Run `npm test` and `npm run build` from `frontend` for frontend changes.
3. Update documentation and `CHANGELOG.md` when behavior changes.
4. Review the diff for secrets, generated assets, and unrelated edits.
5. Describe the change, its user impact, and the verification performed.

Not every command applies to documentation-only changes. State which checks
were not run and why.

Contributions are submitted under the Apache License 2.0 in this repository.
