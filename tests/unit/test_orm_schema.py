"""The ORM metadata must match the tables in docs/spec/02_DATABASE_SCHEMA.md."""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import harness.infrastructure.db.models  # noqa: F401  (registers mappings)
from harness.config.settings import get_settings
from harness.infrastructure.db.base import Base

EXPECTED_TABLES = {
    "sources",
    "artifacts",
    "artifact_parts",
    "evidence",
    "enrichments",
    "knowledge_units",
    "knowledge_unit_evidence",
    "relationships",
    "chunks",
    "processing_runs",
    "model_calls",
    "artifact_duplicates",
}


def _postgres_ddl(table_name: str) -> str:
    dialect = postgresql.dialect()  # type: ignore[no-untyped-call]
    return str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=dialect))


def test_all_spec_tables_are_mapped() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_artifacts_unique_constraint_matches_spec() -> None:
    assert "UNIQUE (source_id, external_id, version, checksum_sha256)" in _postgres_ddl(
        "artifacts"
    )


def test_chunks_embedding_uses_configured_dimension() -> None:
    assert f"VECTOR({get_settings().embedding_dimension})" in _postgres_ddl("chunks")


def test_processing_runs_idempotency_key_is_unique() -> None:
    table = Base.metadata.tables["processing_runs"]
    assert table.columns["idempotency_key"].unique


def test_metadata_columns_are_jsonb_with_default(
) -> None:
    for table_name in ("artifacts", "artifact_parts", "evidence", "knowledge_units"):
        column = Base.metadata.tables[table_name].columns["metadata"]
        assert column.server_default is not None, table_name
        assert type(column.type).__name__ == "JSONB", table_name
