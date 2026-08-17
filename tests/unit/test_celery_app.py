"""Celery queue topology and retry policy (TASK-007)."""

from harness.domain.processing.models import (
    PermanentProcessingError,
    ProcessingStage,
    TransientProcessingError,
)
from harness.infrastructure.queue.celery_app import (
    QUEUE_NAMES,
    HarnessTask,
    app,
    create_celery_app,
    ping,
    route_task,
)


class TestQueueTopology:
    def test_one_queue_per_pipeline_stage(self) -> None:
        assert QUEUE_NAMES == (
            "discovery",
            "normalization",
            "triage",
            "enrichment",
            "embedding",
            "indexing",
            "answer",
            "assessment",
        )

    def test_app_declares_all_queues(self) -> None:
        celery_app = create_celery_app()
        declared = {queue.name for queue in celery_app.conf.task_queues}
        assert declared == set(QUEUE_NAMES)

    def test_tasks_route_to_their_stage_queue(self) -> None:
        for stage in ProcessingStage:
            route = route_task(f"harness.tasks.{stage.value}.do_work")
            assert route == {"queue": stage.value}

    def test_unknown_names_are_not_routed(self) -> None:
        assert route_task("celery.chord_unlock") is None
        assert route_task("harness.tasks.unknown_stage.x") is None


class TestRetryPolicy:
    def test_transient_errors_are_autoretried_with_backoff(self) -> None:
        assert HarnessTask.autoretry_for == (TransientProcessingError,)
        assert HarnessTask.retry_backoff is True
        assert HarnessTask.retry_jitter is True
        assert HarnessTask.max_retries >= 1

    def test_permanent_errors_are_not_autoretried(self) -> None:
        assert not any(
            issubclass(PermanentProcessingError, exc) for exc in HarnessTask.autoretry_for
        )


class TestTasks:
    def test_ping_executes_eagerly(self) -> None:
        app.conf.task_always_eager = True
        try:
            assert ping.apply().get() == "pong"
        finally:
            app.conf.task_always_eager = False

    def test_tasks_inherit_harness_base(self) -> None:
        assert isinstance(ping, HarnessTask)
