"""Evidence entities (docs/spec/02_DATABASE_SCHEMA.md, section 1).

Evidence is a traceable unit of extracted content tied to an artifact part.
Enrichments are derived interpretations produced by configured model
capabilities, always recording provider/model/prompt provenance.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from harness.domain.common.values import (
    validate_confidence,
    validate_non_negative,
    validate_sha256,
)


@dataclass(slots=True)
class Evidence:
    id: UUID
    artifact_id: UUID
    artifact_part_id: UUID
    modality: str
    content: str
    content_hash: str
    extraction_method: str
    created_at: datetime
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_sha256(self.content_hash, field="content_hash")
        validate_confidence(self.confidence, field="confidence")
        if not self.content:
            raise ValueError("content must not be empty")
        if not self.extraction_method:
            raise ValueError("extraction_method must not be empty")


@dataclass(slots=True)
class Enrichment:
    id: UUID
    evidence_id: UUID
    enrichment_type: str
    content: dict[str, Any]
    created_at: datetime
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        validate_confidence(self.confidence, field="confidence")
        validate_non_negative(self.input_tokens, field="input_tokens")
        validate_non_negative(self.output_tokens, field="output_tokens")
