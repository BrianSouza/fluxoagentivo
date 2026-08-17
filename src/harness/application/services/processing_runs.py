"""Idempotent processing-run tracking (TASK-006).

The tracker is the single entry point pipeline stages use to record work.
Starting a run with an idempotency key that already succeeded (or is still
running) returns the existing run instead of creating a duplicate, which is
what makes re-delivered jobs and re-synced sources safe.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from harness.domain.processing.models import (
    ProcessingRun,
    ProcessingStage,
    ProcessingStatus,
)
from harness.domain.processing.ports import ProcessingRunRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class StartResult:
    run: ProcessingRun
    created: bool

    @property
    def should_execute(self) -> bool:
        """Work must run only for runs this call created.

        An existing SUCCEEDED run means the work is already done; an existing
        RUNNING run means another worker owns it; an existing FAILED run is
        only re-executed through start_new_attempt.
        """
        return self.created


class ProcessingRunTracker:
    def __init__(
        self,
        repository: ProcessingRunRepository,
        *,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._repository = repository
        self._now = now

    def start(
        self,
        stage: ProcessingStage,
        idempotency_key: str,
        *,
        artifact_id: UUID | None = None,
    ) -> StartResult:
        existing = self._repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            return StartResult(run=existing, created=False)
        run = ProcessingRun(
            id=uuid4(),
            stage=stage,
            status=ProcessingStatus.RUNNING,
            idempotency_key=idempotency_key,
            artifact_id=artifact_id,
            started_at=self._now(),
        )
        self._repository.add(run)
        return StartResult(run=run, created=True)

    def start_new_attempt(
        self,
        stage: ProcessingStage,
        idempotency_key: str,
        *,
        artifact_id: UUID | None = None,
    ) -> StartResult:
        """Re-execute a previously failed run by resetting it to RUNNING."""
        existing = self._repository.get_by_idempotency_key(idempotency_key)
        if existing is None or existing.status is not ProcessingStatus.FAILED:
            return self.start(stage, idempotency_key, artifact_id=artifact_id)
        existing.status = ProcessingStatus.RUNNING
        existing.started_at = self._now()
        existing.finished_at = None
        existing.error_code = None
        existing.error_message = None
        self._repository.update(existing)
        return StartResult(run=existing, created=True)

    def complete(self, run_id: UUID, *, metrics: dict[str, Any] | None = None) -> ProcessingRun:
        run = self._require(run_id)
        run.status = ProcessingStatus.SUCCEEDED
        run.finished_at = self._now()
        if metrics:
            run.metrics.update(metrics)
        self._repository.update(run)
        return run

    def fail(
        self,
        run_id: UUID,
        *,
        error_code: str,
        error_message: str,
        metrics: dict[str, Any] | None = None,
    ) -> ProcessingRun:
        run = self._require(run_id)
        run.status = ProcessingStatus.FAILED
        run.finished_at = self._now()
        run.error_code = error_code
        run.error_message = error_message
        if metrics:
            run.metrics.update(metrics)
        self._repository.update(run)
        return run

    def _require(self, run_id: UUID) -> ProcessingRun:
        run = self._repository.get(run_id)
        if run is None:
            raise LookupError(f"processing run {run_id} not found")
        return run
