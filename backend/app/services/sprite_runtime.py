"""Framework-neutral storage and provider wiring for synchronous adapters."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import threading
from typing import Callable

from PIL import Image

from app.models import ImageProviderName
from app.services.provider_selection import ProviderRegistry
from app.services.sprite_service import OperationControl, SpriteService
from app.storage.project_store import ProjectStore


Remover = Callable[[Image.Image], Image.Image]


@dataclass(frozen=True)
class SpriteRuntime:
    """Construct provider-bound services without coupling adapters to FastAPI."""

    store: ProjectStore
    providers: ProviderRegistry
    remover: Remover | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    operation_timeout_seconds: float = 900.0
    creative_operation_max_concurrency: int = 2
    _creative_semaphore: threading.BoundedSemaphore = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "_creative_semaphore",
            threading.BoundedSemaphore(
                max(1, int(self.creative_operation_max_concurrency))
            ),
        )

    def run_creative(
        self,
        operation: Callable[[], object],
        control: OperationControl,
    ) -> object:
        """Run under the process runtime's gate until work actually stops."""

        acquired = False
        try:
            while not acquired:
                control.check_cancelled()
                acquired = self._creative_semaphore.acquire(timeout=0.05)
            control.check_cancelled()
            return operation()
        finally:
            if acquired:
                self._creative_semaphore.release()

    def storage_service(self) -> SpriteService:
        return SpriteService(store=self.store)

    def prompt_service(self) -> SpriteService:
        return SpriteService(
            store=self.store,
            prompt_enhancer=self.providers.prompt_enhancer,
            remover=self.remover,
        )

    def service_for_provider(self, requested: ImageProviderName) -> SpriteService:
        resolved = self.providers.resolve(requested)
        return SpriteService(
            store=self.store,
            image_provider=resolved.provider,
            prompt_enhancer=self.providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=self.remover,
        )

    def service_for_project(self, project_id: str) -> SpriteService:
        project = self.store.read_manifest(project_id)
        resolved = self.providers.resolve_stored(project.image_provider)
        return SpriteService(
            store=self.store,
            image_provider=resolved.provider,
            prompt_enhancer=self.providers.prompt_enhancer,
            provider_name=resolved.name,
            remover=self.remover,
        )
