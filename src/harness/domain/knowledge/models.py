"""Knowledge entities (docs/spec/02_DATABASE_SCHEMA.md, section 1).

A KnowledgeUnit is a versioned, evidence-backed unit of knowledge. It never
exists without supporting evidence references. Relationships form a typed
graph between entities, optionally justified by evidence.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from harness.domain.common.values import validate_confidence


@dataclass(slots=True)
class KnowledgeUnit:
    id: UUID
    title: str
    summary: str
    version: int
    status: str
    created_at: datetime
    updated_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    evidence_ids: list[UUID] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"version must be >= 1, got {self.version!r}")
        if not self.title:
            raise ValueError("title must not be empty")
        if not self.summary:
            raise ValueError("summary must not be empty")


@dataclass(slots=True)
class Relationship:
    id: UUID
    subject_type: str
    subject_id: UUID
    predicate: str
    object_type: str
    object_id: UUID
    created_at: datetime
    confidence: float | None = None
    evidence_id: UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_confidence(self.confidence, field="confidence")
        if not self.predicate:
            raise ValueError("predicate must not be empty")
