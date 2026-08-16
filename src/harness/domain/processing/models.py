"""ProcessingRun entity and error taxonomy.

Every externally triggered operation is tracked by a ProcessingRun with a
unique idempotency key (docs/spec/01_ARCHITECTURE.md, sections 5 and 8;
table in 02_DATABASE_SCHEMA.md, section 3). All failures create an
auditable record.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class ProcessingStage(StrEnum):
    """Pipeline stages, mirroring the queue names in 01_ARCHITECTURE.md."""

    DISCOVERY = "discovery"
    NORMALIZATION = "normalization"
    TRIAGE = "triage"
    ENRICHMENT = "enrichment"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    ANSWER = "answer"
    ASSESSMENT = "assessment"


class ProcessingStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TransientProcessingError(Exception):
    """Retryable failure: HTTP 429/5xx, network timeout, temporary provider outage."""


class PermanentProcessingError(Exception):
    """Non-retryable failure: bad credentials, unsupported format, corrupted artifact."""


def derive_ingest_key(
    source_system: str,
    source_uri: str,
    source_version: str | None,
    checksum: str,
) -> str:
    """Idempotency key per 01_ARCHITECTURE.md section 5."""
    material = "\n".join((source_system, source_uri, source_version or "", checksum))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(slots=True)
class ProcessingRun:
    id: UUID
    stage: ProcessingStage
    status: ProcessingStatus
    idempotency_key: str
    artifact_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.idempotency_key:
            raise ValueError("idempotency_key must not be empty")

    @property
    def is_finished(self) -> bool:
        return self.status in (ProcessingStatus.SUCCEEDED, ProcessingStatus.FAILED)
