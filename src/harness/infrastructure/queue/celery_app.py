"""Celery application with one queue per pipeline stage (TASK-007).

Queues follow docs/spec/01_ARCHITECTURE.md section 7; retry policy follows
section 8: transient failures (HTTP 429/5xx, timeouts, temporary provider
outages) are retried with exponential backoff, permanent failures are not.

Tasks are named `harness.tasks.<stage>.<name>` and routed to the `<stage>`
queue automatically. Worker processes execute the same application services
as the API.
"""

from __future__ import annotations

from celery import Celery, Task
from kombu import Queue

from harness.config.settings import Settings, get_settings
from harness.domain.processing.models import ProcessingStage, TransientProcessingError

TASK_NAME_PREFIX = "harness.tasks."

QUEUE_NAMES: tuple[str, ...] = tuple(stage.value for stage in ProcessingStage)


class HarnessTask(Task):  # type: ignore[type-arg]
    """Base task applying the spec retry policy.

    Raise TransientProcessingError for retryable failures; anything else
    (including PermanentProcessingError) fails immediately and is recorded
    by the ProcessingRun of the stage.
    """

    autoretry_for = (TransientProcessingError,)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    max_retries = get_settings().celery_task_max_retries


def route_task(
    name: str,
    *args: object,
    **kwargs: object,
) -> dict[str, str] | None:
    if not name.startswith(TASK_NAME_PREFIX):
        return None
    stage = name.removeprefix(TASK_NAME_PREFIX).split(".", 1)[0]
    if stage in QUEUE_NAMES:
        return {"queue": stage}
    return None


def create_celery_app(settings: Settings | None = None) -> Celery[HarnessTask]:
    settings = settings or get_settings()
    celery_app = Celery("harness", task_cls=HarnessTask)
    celery_app.conf.update(
        broker_url=settings.redis_url,
        result_backend=settings.redis_url,
        task_queues=tuple(Queue(name) for name in QUEUE_NAMES),
        task_routes=(route_task,),
        task_default_queue=ProcessingStage.DISCOVERY.value,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        timezone="UTC",
        enable_utc=True,
    )
    return celery_app


app = create_celery_app()


@app.task(name="harness.tasks.discovery.ping")
def ping() -> str:
    """Wiring smoke-test task; replaced by real discovery tasks later."""
    return "pong"
