"""SQLAlchemy-backed ProcessingRunRepository."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness.domain.processing.models import (
    ProcessingRun,
    ProcessingStage,
    ProcessingStatus,
)
from harness.infrastructure.db.models import ProcessingRunRecord


class SqlProcessingRunRepository:
    """Satisfies harness.domain.processing.ports.ProcessingRunRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: ProcessingRun) -> None:
        self._session.add(_to_record(run))
        self._session.flush()

    def get(self, run_id: UUID) -> ProcessingRun | None:
        record = self._session.get(ProcessingRunRecord, run_id)
        return None if record is None else _to_domain(record)

    def get_by_idempotency_key(self, key: str) -> ProcessingRun | None:
        record = self._session.scalars(
            select(ProcessingRunRecord).where(ProcessingRunRecord.idempotency_key == key)
        ).first()
        return None if record is None else _to_domain(record)

    def update(self, run: ProcessingRun) -> None:
        record = self._session.get(ProcessingRunRecord, run.id)
        if record is None:
            raise LookupError(f"processing run {run.id} not found")
        record.stage = run.stage.value
        record.status = run.status.value
        record.artifact_id = run.artifact_id
        record.started_at = run.started_at
        record.finished_at = run.finished_at
        record.error_code = run.error_code
        record.error_message = run.error_message
        record.metrics = dict(run.metrics)
        self._session.flush()


def _to_record(run: ProcessingRun) -> ProcessingRunRecord:
    return ProcessingRunRecord(
        id=run.id,
        artifact_id=run.artifact_id,
        stage=run.stage.value,
        status=run.status.value,
        idempotency_key=run.idempotency_key,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error_code=run.error_code,
        error_message=run.error_message,
        metrics=dict(run.metrics),
    )


def _to_domain(record: ProcessingRunRecord) -> ProcessingRun:
    return ProcessingRun(
        id=record.id,
        stage=ProcessingStage(record.stage),
        status=ProcessingStatus(record.status),
        idempotency_key=record.idempotency_key,
        artifact_id=record.artifact_id,
        started_at=record.started_at,
        finished_at=record.finished_at,
        error_code=record.error_code,
        error_message=record.error_message,
        metrics=dict(record.metrics),
    )
