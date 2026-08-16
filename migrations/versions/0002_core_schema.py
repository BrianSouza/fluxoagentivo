"""Core schema: artifacts, evidence, knowledge, search, processing, dedup.

Tables follow docs/spec/02_DATABASE_SCHEMA.md. Assessment tables are added
by the assessment engine epic. The embedding column dimension comes from
Settings (EMBEDDING_DIMENSION) and must match the embedding model in use.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import CHAR, JSONB, TIMESTAMP, UUID

from harness.config.settings import get_settings

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONB_EMPTY = sa.text("'{}'::jsonb")


def _jsonb(name: str = "metadata") -> sa.Column[dict[str, object]]:
    return sa.Column(name, JSONB, nullable=False, server_default=_JSONB_EMPTY)


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("config_ref", sa.String(500)),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", UUID(as_uuid=True), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(1000), nullable=False),
        sa.Column("parent_artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id")),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("source_uri", sa.Text, nullable=False),
        sa.Column("version", sa.String(500)),
        sa.Column("checksum_sha256", CHAR(64), nullable=False),
        sa.Column("mime_type", sa.String(200)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("created_at", TIMESTAMP(timezone=True)),
        sa.Column("modified_at", TIMESTAMP(timezone=True)),
        sa.Column("discovered_at", TIMESTAMP(timezone=True), nullable=False),
        _jsonb(),
        sa.UniqueConstraint("source_id", "external_id", "version", "checksum_sha256"),
    )
    op.create_index("ix_artifacts_source_id", "artifacts", ["source_id"])

    op.create_table(
        "artifact_parts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=False
        ),
        sa.Column("parent_part_id", UUID(as_uuid=True), sa.ForeignKey("artifact_parts.id")),
        sa.Column("part_type", sa.String(50), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("location", JSONB, nullable=False, server_default=_JSONB_EMPTY),
        sa.Column("text_content", sa.Text),
        sa.Column("binary_object_key", sa.Text),
        sa.Column("checksum_sha256", CHAR(64)),
        _jsonb(),
    )
    op.create_index("ix_artifact_parts_artifact_id", "artifact_parts", ["artifact_id"])

    op.create_table(
        "evidence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), nullable=False
        ),
        sa.Column(
            "artifact_part_id",
            UUID(as_uuid=True),
            sa.ForeignKey("artifact_parts.id"),
            nullable=False,
        ),
        sa.Column("modality", sa.String(30), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", CHAR(64), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("extraction_method", sa.String(100), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        _jsonb(),
    )
    op.create_index("ix_evidence_artifact_id", "evidence", ["artifact_id"])
    op.create_index("ix_evidence_artifact_part_id", "evidence", ["artifact_part_id"])

    op.create_table(
        "enrichments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("enrichment_type", sa.String(100), nullable=False),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("model", sa.String(200)),
        sa.Column("prompt_version", sa.String(100)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("estimated_cost", sa.Numeric(18, 8)),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_enrichments_evidence_id", "enrichments", ["evidence_id"])

    op.create_table(
        "knowledge_units",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("valid_from", TIMESTAMP(timezone=True)),
        sa.Column("valid_to", TIMESTAMP(timezone=True)),
        _jsonb(),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", TIMESTAMP(timezone=True), nullable=False),
    )

    op.create_table(
        "knowledge_unit_evidence",
        sa.Column("knowledge_unit_id", UUID(as_uuid=True), sa.ForeignKey("knowledge_units.id")),
        sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id")),
        sa.PrimaryKeyConstraint("knowledge_unit_id", "evidence_id"),
    )

    op.create_table(
        "relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("subject_type", sa.String(50), nullable=False),
        sa.Column("subject_id", UUID(as_uuid=True), nullable=False),
        sa.Column("predicate", sa.String(100), nullable=False),
        sa.Column("object_type", sa.String(50), nullable=False),
        sa.Column("object_id", UUID(as_uuid=True), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4)),
        sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id")),
        _jsonb(),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_relationships_subject", "relationships", ["subject_type", "subject_id"])
    op.create_index("ix_relationships_object", "relationships", ["object_type", "object_id"])

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("token_estimate", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(get_settings().embedding_dimension)),
        _jsonb(),
    )
    op.create_index("ix_chunks_evidence_id", "chunks", ["evidence_id"])
    op.create_index(
        "ix_chunks_content_fts",
        "chunks",
        [sa.text("to_tsvector('english', content)")],
        postgresql_using="gin",
    )

    op.create_table(
        "processing_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id")),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(500), nullable=False, unique=True),
        sa.Column("started_at", TIMESTAMP(timezone=True)),
        sa.Column("finished_at", TIMESTAMP(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text),
        _jsonb("metrics"),
    )
    op.create_index("ix_processing_runs_artifact_id", "processing_runs", ["artifact_id"])

    op.create_table(
        "model_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id")),
        sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id")),
        sa.Column("prompt_version", sa.String(100)),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("estimated_cost", sa.Numeric(18, 8)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", TIMESTAMP(timezone=True), nullable=False),
        _jsonb(),
    )
    op.create_index("ix_model_calls_task", "model_calls", ["task"])

    op.create_table(
        "artifact_duplicates",
        sa.Column(
            "artifact_id", UUID(as_uuid=True), sa.ForeignKey("artifacts.id"), primary_key=True
        ),
        sa.Column(
            "canonical_artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("artifacts.id"),
            nullable=False,
        ),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("similarity", sa.Numeric(6, 5)),
    )


def downgrade() -> None:
    for table in (
        "artifact_duplicates",
        "model_calls",
        "processing_runs",
        "chunks",
        "relationships",
        "knowledge_unit_evidence",
        "knowledge_units",
        "enrichments",
        "evidence",
        "artifact_parts",
        "artifacts",
        "sources",
    ):
        op.drop_table(table)
