"""ProcessingRun domain rules and idempotent tracker behavior (TASK-006)."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from harness.application.services.processing_runs import ProcessingRunTracker
from harness.domain.processing.models import (
    ProcessingRun,
    ProcessingStage,
    ProcessingStatus,
    derive_ingest_key,
)


class InMemoryProcessingRunRepository:
    """Satisfies harness.domain.processing.ports.ProcessingRunRepository."""

    def __init__(self) -> None:
        self.runs: dict[UUID, ProcessingRun] = {}

    def add(self, run: ProcessingRun) -> None:
        if any(r.idempotency_key == run.idempotency_key for r in self.runs.values()):
            raise ValueError(f"duplicate idempotency key {run.idempotency_key!r}")
        self.runs[run.id] = run

    def get(self, run_id: UUID) -> ProcessingRun | None:
        return self.runs.get(run_id)

    def get_by_idempotency_key(self, key: str) -> ProcessingRun | None:
        return next((r for r in self.runs.values() if r.idempotency_key == key), None)

    def update(self, run: ProcessingRun) -> None:
        if run.id not in self.runs:
            raise LookupError(str(run.id))
        self.runs[run.id] = run


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def repository() -> InMemoryProcessingRunRepository:
    return InMemoryProcessingRunRepository()


@pytest.fixture
def tracker(repository: InMemoryProcessingRunRepository) -> ProcessingRunTracker:
    return ProcessingRunTracker(repository, now=lambda: NOW)


class TestDeriveIngestKey:
    def test_is_deterministic(self) -> None:
        a = derive_ingest_key("confluence", "https://w/p1", "3", "ab" * 32)
        b = derive_ingest_key("confluence", "https://w/p1", "3", "ab" * 32)
        assert a == b
        assert len(a) == 64

    def test_changes_with_any_component(self) -> None:
        base = derive_ingest_key("confluence", "https://w/p1", "3", "ab" * 32)
        assert derive_ingest_key("git", "https://w/p1", "3", "ab" * 32) != base
        assert derive_ingest_key("confluence", "https://w/p2", "3", "ab" * 32) != base
        assert derive_ingest_key("confluence", "https://w/p1", "4", "ab" * 32) != base
        assert derive_ingest_key("confluence", "https://w/p1", "3", "cd" * 32) != base

    def test_missing_version_is_supported(self) -> None:
        assert derive_ingest_key("fs", "file:///a", None, "ab" * 32)


class TestTrackerStart:
    def test_creates_running_run(self, tracker: ProcessingRunTracker) -> None:
        result = tracker.start(ProcessingStage.DISCOVERY, "key-1", artifact_id=uuid4())
        assert result.created
        assert result.should_execute
        assert result.run.status is ProcessingStatus.RUNNING
        assert result.run.started_at == NOW

    def test_same_key_returns_existing_run_without_duplicating(
        self, tracker: ProcessingRunTracker, repository: InMemoryProcessingRunRepository
    ) -> None:
        first = tracker.start(ProcessingStage.DISCOVERY, "key-1")
        second = tracker.start(ProcessingStage.DISCOVERY, "key-1")
        assert not second.created
        assert not second.should_execute
        assert second.run.id == first.run.id
        assert len(repository.runs) == 1

    def test_succeeded_run_is_not_reexecuted(self, tracker: ProcessingRunTracker) -> None:
        first = tracker.start(ProcessingStage.NORMALIZATION, "key-1")
        tracker.complete(first.run.id)
        again = tracker.start(ProcessingStage.NORMALIZATION, "key-1")
        assert not again.should_execute
        assert again.run.status is ProcessingStatus.SUCCEEDED


class TestTrackerLifecycle:
    def test_complete_records_finish_and_metrics(self, tracker: ProcessingRunTracker) -> None:
        run = tracker.start(ProcessingStage.TRIAGE, "key-1").run
        completed = tracker.complete(run.id, metrics={"items": 10})
        assert completed.status is ProcessingStatus.SUCCEEDED
        assert completed.finished_at == NOW
        assert completed.metrics == {"items": 10}

    def test_fail_records_auditable_error(self, tracker: ProcessingRunTracker) -> None:
        run = tracker.start(ProcessingStage.ENRICHMENT, "key-1").run
        failed = tracker.fail(
            run.id, error_code="unsupported_format", error_message="legacy .doc"
        )
        assert failed.status is ProcessingStatus.FAILED
        assert failed.error_code == "unsupported_format"
        assert failed.is_finished

    def test_start_new_attempt_resets_failed_run(self, tracker: ProcessingRunTracker) -> None:
        run = tracker.start(ProcessingStage.EMBEDDING, "key-1").run
        tracker.fail(run.id, error_code="timeout", error_message="provider timeout")
        retry = tracker.start_new_attempt(ProcessingStage.EMBEDDING, "key-1")
        assert retry.should_execute
        assert retry.run.id == run.id
        assert retry.run.status is ProcessingStatus.RUNNING
        assert retry.run.error_code is None

    def test_start_new_attempt_on_fresh_key_behaves_like_start(
        self, tracker: ProcessingRunTracker
    ) -> None:
        result = tracker.start_new_attempt(ProcessingStage.INDEXING, "fresh")
        assert result.created
        assert result.run.status is ProcessingStatus.RUNNING

    def test_complete_unknown_run_raises(self, tracker: ProcessingRunTracker) -> None:
        with pytest.raises(LookupError):
            tracker.complete(uuid4())


def test_empty_idempotency_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        ProcessingRun(
            id=uuid4(),
            stage=ProcessingStage.DISCOVERY,
            status=ProcessingStatus.RUNNING,
            idempotency_key="",
        )
