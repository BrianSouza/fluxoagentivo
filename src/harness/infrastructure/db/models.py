"""SQLAlchemy ORM models matching docs/spec/02_DATABASE_SCHEMA.md.

Assessment tables (spec section 5) are defined by the assessment engine epic
and are added when that epic is implemented.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CHAR, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from harness.config.settings import get_settings
from harness.infrastructure.db.base import Base

_JSONB_EMPTY = text("'{}'::jsonb")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50))
    config_ref: Mapped[str | None] = mapped_column(String(500))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class ArtifactRecord(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", "version", "checksum_sha256"),
        Index("ix_artifacts_source_id", "source_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(String(1000))
    parent_artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    artifact_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(Text)
    source_uri: Mapped[str] = mapped_column(Text)
    version: Mapped[str | None] = mapped_column(String(500))
    checksum_sha256: Mapped[str] = mapped_column(CHAR(64))
    mime_type: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    modified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class ArtifactPartRecord(Base):
    __tablename__ = "artifact_parts"
    __table_args__ = (Index("ix_artifact_parts_artifact_id", "artifact_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id"))
    parent_part_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifact_parts.id")
    )
    part_type: Mapped[str] = mapped_column(String(50))
    ordinal: Mapped[int] = mapped_column(Integer)
    location: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=_JSONB_EMPTY
    )
    text_content: Mapped[str | None] = mapped_column(Text)
    binary_object_key: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(CHAR(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class EvidenceRecord(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_artifact_id", "artifact_id"),
        Index("ix_evidence_artifact_part_id", "artifact_part_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("artifacts.id"))
    artifact_part_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifact_parts.id")
    )
    modality: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(CHAR(64))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    extraction_method: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class EnrichmentRecord(Base):
    __tablename__ = "enrichments"
    __table_args__ = (Index("ix_enrichments_evidence_id", "evidence_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id"))
    enrichment_type: Mapped[str] = mapped_column(String(100))
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String(100))
    model: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(18, 8))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class KnowledgeUnitRecord(Base):
    __tablename__ = "knowledge_units"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30))
    valid_from: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class KnowledgeUnitEvidenceRecord(Base):
    __tablename__ = "knowledge_unit_evidence"
    __table_args__ = (PrimaryKeyConstraint("knowledge_unit_id", "evidence_id"),)

    knowledge_unit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("knowledge_units.id")
    )
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id"))


class RelationshipRecord(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        Index("ix_relationships_subject", "subject_type", "subject_id"),
        Index("ix_relationships_object", "object_type", "object_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    subject_type: Mapped[str] = mapped_column(String(50))
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    predicate: Mapped[str] = mapped_column(String(100))
    object_type: Mapped[str] = mapped_column(String(50))
    object_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id")
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class ChunkRecord(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_evidence_id", "evidence_id"),
        Index(
            "ix_chunks_content_fts",
            text("to_tsvector('english', content)"),
            postgresql_using="gin",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[Any | None] = mapped_column(Vector(get_settings().embedding_dimension))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class ProcessingRunRecord(Base):
    __tablename__ = "processing_runs"
    __table_args__ = (Index("ix_processing_runs_artifact_id", "artifact_id"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    stage: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    idempotency_key: Mapped[str] = mapped_column(String(500), unique=True)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class ModelCallRecord(Base):
    __tablename__ = "model_calls"
    __table_args__ = (Index("ix_model_calls_task", "task"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    evidence_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("evidence.id")
    )
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(18, 8))
    status: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default=_JSONB_EMPTY
    )


class ArtifactDuplicateRecord(Base):
    __tablename__ = "artifact_duplicates"

    artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id"), primary_key=True
    )
    canonical_artifact_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.id")
    )
    method: Mapped[str] = mapped_column(String(50))
    similarity: Mapped[float | None] = mapped_column(Numeric(6, 5))
