"""PostgreSQL search indexes (TASK-029, TASK-030).

Thin translation layers over SQLAlchemy, following the same pattern as
SqlProcessingRunRepository and SqlModelCallSink: correctness rests on
mypy and code review rather than exhaustive tests, since exercising real
PostgreSQL full-text search and pgvector distance operators requires a
live database this project's hermetic test suite does not start.
"""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from harness.domain.retrieval.models import EmbeddedChunk, SearchFilters
from harness.domain.retrieval.ports import LexicalHit, RelatedHit, VectorHit
from harness.infrastructure.db.models import (
    ArtifactRecord,
    ChunkRecord,
    EvidenceRecord,
    RelationshipRecord,
)


def _apply_filters(
    stmt: Select[tuple[object, ...]], filters: SearchFilters
) -> Select[tuple[object, ...]]:
    if filters.source_ids:
        stmt = stmt.where(ArtifactRecord.source_id.in_(filters.source_ids))
    if filters.artifact_types:
        stmt = stmt.where(ArtifactRecord.artifact_type.in_(filters.artifact_types))
    return stmt


class PostgresLexicalSearchIndex:
    """Satisfies harness.domain.retrieval.ports.LexicalSearchIndex (TASK-029)."""

    def __init__(self, session: Session, *, language: str = "english") -> None:
        self._session = session
        self._language = language

    def search(self, query: str, filters: SearchFilters, limit: int) -> list[LexicalHit]:
        tsquery = func.plainto_tsquery(self._language, query)
        tsvector = func.to_tsvector(self._language, ChunkRecord.content)
        rank = func.ts_rank(tsvector, tsquery).label("rank")
        stmt = (
            select(ChunkRecord, EvidenceRecord, ArtifactRecord, rank)
            .join(EvidenceRecord, ChunkRecord.evidence_id == EvidenceRecord.id)
            .join(ArtifactRecord, EvidenceRecord.artifact_id == ArtifactRecord.id)
            .where(tsvector.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(limit)
        )
        stmt = _apply_filters(stmt, filters)
        rows: Sequence[tuple[ChunkRecord, EvidenceRecord, ArtifactRecord, float]] = (
            self._session.execute(stmt).all()  # type: ignore[assignment]
        )
        return [
            LexicalHit(
                chunk_id=chunk.id,
                evidence_id=evidence.id,
                artifact_id=artifact.id,
                content=chunk.content,
                rank=float(rank_value),
                source_id=artifact.source_id,
            )
            for chunk, evidence, artifact, rank_value in rows
        ]


class PostgresVectorSearchIndex:
    """Satisfies harness.domain.retrieval.ports.VectorSearchIndex (TASK-030)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def search(
        self, embedding: list[float], filters: SearchFilters, limit: int
    ) -> list[VectorHit]:
        distance = ChunkRecord.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(ChunkRecord, EvidenceRecord, ArtifactRecord, distance)
            .join(EvidenceRecord, ChunkRecord.evidence_id == EvidenceRecord.id)
            .join(ArtifactRecord, EvidenceRecord.artifact_id == ArtifactRecord.id)
            .where(ChunkRecord.embedding.is_not(None))
            .order_by(distance)
            .limit(limit)
        )
        stmt = _apply_filters(stmt, filters)
        rows: Sequence[tuple[ChunkRecord, EvidenceRecord, ArtifactRecord, float]] = (
            self._session.execute(stmt).all()  # type: ignore[assignment]
        )
        return [
            VectorHit(
                chunk_id=chunk.id,
                evidence_id=evidence.id,
                artifact_id=artifact.id,
                content=chunk.content,
                similarity=max(0.0, 1.0 - float(distance_value)),
                source_id=artifact.source_id,
            )
            for chunk, evidence, artifact, distance_value in rows
        ]


class ChunkEmbeddingWriter:
    """Persists vectors computed by EmbeddingIndexer (TASK-030)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def write(self, embeddings: list[EmbeddedChunk]) -> None:
        for item in embeddings:
            record = self._session.get(ChunkRecord, item.chunk_id)
            if record is None:
                raise LookupError(f"chunk {item.chunk_id} not found")
            record.embedding = item.embedding
        self._session.flush()


class SqlRelationshipExpander:
    """Satisfies RelationshipExpander using the relationships table (stage 6)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def expand(self, seed_evidence_ids: list[UUID], limit: int) -> list[RelatedHit]:
        if not seed_evidence_ids:
            return []
        stmt = (
            select(ChunkRecord, EvidenceRecord, ArtifactRecord)
            .join(RelationshipRecord, RelationshipRecord.object_id == EvidenceRecord.id)
            .join(ChunkRecord, ChunkRecord.evidence_id == EvidenceRecord.id)
            .join(ArtifactRecord, EvidenceRecord.artifact_id == ArtifactRecord.id)
            .where(
                RelationshipRecord.subject_id.in_(seed_evidence_ids),
                RelationshipRecord.subject_type == "evidence",
                RelationshipRecord.object_type == "evidence",
            )
            .limit(limit)
        )
        rows = self._session.execute(stmt).all()
        return [
            RelatedHit(
                chunk_id=chunk.id,
                evidence_id=evidence.id,
                artifact_id=artifact.id,
                content=chunk.content,
                source_id=artifact.source_id,
            )
            for chunk, evidence, artifact in rows
        ]
