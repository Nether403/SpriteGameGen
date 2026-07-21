"""FastAPI application factory + wiring.

``create_app`` builds the app so tests can construct isolated instances and
override dependencies. The deterministic ``remover`` (rembg or a fake) is stored
on ``app.state`` so the generate route can inject it into the pipeline.
"""
from __future__ import annotations

from typing import Callable

from fastapi import Depends, FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from app.config import ProviderReadiness, get_settings
from app.deps import get_provider_availability, get_store
from app.routes import animate, assets, export, generate, projects, prompts
from app.storage.project_store import ProjectStore

# Dev frontend origin (Vite).
_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

Remover = Callable[[Image.Image], Image.Image]

# Upload cap lives on app.state so the request path never triggers full auth-
# settings validation just to reject an oversized file.
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB


def create_app(
    *, remover: Remover | None = None, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
) -> FastAPI:
    app = FastAPI(title="Sprite Game Asset Tool")
    # None => background.remove falls back to its lazy default rembg session.
    app.state.remover = remover
    app.state.max_upload_bytes = max_upload_bytes

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(generate.router)
    app.include_router(animate.router)
    app.include_router(export.router)
    app.include_router(projects.router)
    app.include_router(prompts.router)
    app.include_router(assets.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready(
        response: Response,
        store: ProjectStore = Depends(get_store),
        providers: dict[str, ProviderReadiness] = Depends(get_provider_availability),
    ):
        storage_ready = store.root.is_dir()
        if not storage_ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "ready" if storage_ready else "not_ready",
            "storage": {
                "ready": storage_ready,
                "projects_dir": str(store.root),
            },
            "providers": providers,
        }

    return app


# Module-level app for `uvicorn app.main:app`.
app = create_app(max_upload_bytes=get_settings().max_upload_bytes)
