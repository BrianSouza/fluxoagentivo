"""Model call telemetry and cost attribution (spec §9, 12_OBSERVABILITY_COST.md).

Every model call is recorded with enough context to attribute cost to a
task, artifact, profile and prompt version — including calls that failed,
because failures cost money and quality signal alike.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from harness.domain.common.values import validate_non_negative
from harness.domain.models.contracts import ModelTask, Usage


class ModelCallStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ModelPricing:
    """Cost per million tokens, as published by providers."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0
    cached_input_per_million: float | None = None

    def estimate(self, usage: Usage) -> float:
        cached_rate = (
            self.input_per_million
            if self.cached_input_per_million is None
            else self.cached_input_per_million
        )
        fresh_input = max(usage.input_tokens - usage.cached_input_tokens, 0)
        return (
            fresh_input * self.input_per_million
            + usage.cached_input_tokens * cached_rate
            + usage.output_tokens * self.output_per_million
        ) / 1_000_000


@dataclass(slots=True)
class ModelCall:
    task: ModelTask
    provider: str
    model: str
    status: ModelCallStatus
    created_at: datetime
    usage: Usage = Usage()
    latency_ms: int = 0
    estimated_cost: float = 0.0
    profile: str | None = None
    prompt_version: str | None = None
    artifact_id: UUID | None = None
    evidence_id: UUID | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_non_negative(self.latency_ms, field="latency_ms")
        if self.estimated_cost < 0:
            raise ValueError(f"estimated_cost must not be negative, got {self.estimated_cost!r}")
