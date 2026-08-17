"""Persistence port for processing runs, implemented by infrastructure."""

from typing import Protocol
from uuid import UUID

from harness.domain.processing.models import ProcessingRun


class ProcessingRunRepository(Protocol):
    def add(self, run: ProcessingRun) -> None: ...

    def get(self, run_id: UUID) -> ProcessingRun | None: ...

    def get_by_idempotency_key(self, key: str) -> ProcessingRun | None: ...

    def update(self, run: ProcessingRun) -> None: ...
