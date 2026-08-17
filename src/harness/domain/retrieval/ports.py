"""Search index ports.

Sync, like the other database-backed ports (ProcessingRunRepository,
ModelCallSink): retrieval reads happen over the same synchronous
SQLAlchemy session as everything else. HybridRetrievalService is async
only because it also calls the (async) Model Gateway for embeddings and
reranking.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from harness.domain.retrieval.models import SearchFilters


@dataclass(frozen=True, slots=True)
class LexicalHit:
    chunk_id: UUID
    evidence_id: UUID
    artifact_id: UUID
    content: str
    rank: float
    source_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class VectorHit:
    chunk_id: UUID
    evidence_id: UUID
    artifact_id: UUID
    content: str
    similarity: float
    source_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    metadata: dict[str, Any] | None = None


class LexicalSearchIndex(Protocol):
    """TASK-029: PostgreSQL full-text retrieval over chunks.content."""

    def search(self, query: str, filters: SearchFilters, limit: int) -> list[LexicalHit]: ...


class VectorSearchIndex(Protocol):
    """TASK-030: pgvector retrieval over chunks.embedding."""

    def search(
        self, embedding: list[float], filters: SearchFilters, limit: int
    ) -> list[VectorHit]: ...


@dataclass(frozen=True, slots=True)
class RelatedHit:
    chunk_id: UUID
    evidence_id: UUID
    artifact_id: UUID
    content: str
    source_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class RelationshipExpander(Protocol):
    """Stage 6: pull in evidence connected to top candidates by a Relationship."""

    def expand(self, seed_evidence_ids: list[UUID], limit: int) -> list[RelatedHit]: ...


class CanonicalArtifactLookup(Protocol):
    """Resolves an artifact to its canonical duplicate-group representative.

    Returns the artifact's own id when it is canonical or unknown, never
    None — every artifact is the canonical member of at least its own
    group of one.
    """

    def canonical_for(self, artifact_id: UUID) -> UUID: ...


class SourceAuthorityLookup(Protocol):
    """Configurable per source type/instance (spec §9)."""

    def authority_for(self, source_id: UUID | None) -> float: ...
