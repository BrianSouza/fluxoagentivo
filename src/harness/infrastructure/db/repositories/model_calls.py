"""Persist model call telemetry to the model_calls table (TASK-024)."""

from sqlalchemy.orm import Session

from harness.domain.models.telemetry import ModelCall
from harness.infrastructure.db.models import ModelCallRecord


class SqlModelCallSink:
    """Satisfies harness.domain.models.ports.ModelCallSink."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, call: ModelCall) -> None:
        self._session.add(to_record(call))
        self._session.flush()


class InMemoryModelCallSink:
    """Collects calls in memory for tests and local runs."""

    def __init__(self) -> None:
        self.calls: list[ModelCall] = []

    def record(self, call: ModelCall) -> None:
        self.calls.append(call)

    @property
    def total_cost(self) -> float:
        return sum(call.estimated_cost for call in self.calls)


def to_record(call: ModelCall) -> ModelCallRecord:
    metadata = dict(call.metadata)
    metadata.setdefault("profile", call.profile)
    metadata.setdefault("cached_input_tokens", call.usage.cached_input_tokens)
    if call.error_message:
        metadata.setdefault("error", call.error_message)
    return ModelCallRecord(
        task=call.task.value,
        provider=call.provider,
        model=call.model,
        artifact_id=call.artifact_id,
        evidence_id=call.evidence_id,
        prompt_version=call.prompt_version,
        input_tokens=call.usage.input_tokens,
        output_tokens=call.usage.output_tokens,
        latency_ms=call.latency_ms,
        estimated_cost=call.estimated_cost,
        status=call.status.value,
        created_at=call.created_at,
        metadata_=metadata,
    )
