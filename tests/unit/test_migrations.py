"""Offline (SQL-emitting) execution of Alembic migrations.

Runs `upgrade --sql` without a database, proving migrations are executable
and emit the DDL required by docs/spec/02_DATABASE_SCHEMA.md.
"""

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def offline_sql() -> str:
    buffer = io.StringIO()
    config = Config(str(REPO_ROOT / "alembic.ini"), output_buffer=buffer)
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(config, "head", sql=True)
    return buffer.getvalue()


def test_pgvector_extension_is_enabled(offline_sql: str) -> None:
    assert "CREATE EXTENSION IF NOT EXISTS vector" in offline_sql


def test_all_spec_tables_are_created(offline_sql: str) -> None:
    for table in (
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
    ):
        assert f"CREATE TABLE {table} (" in offline_sql, table


def test_chunks_has_vector_column_and_fts_index(offline_sql: str) -> None:
    assert "embedding VECTOR(" in offline_sql
    assert "ix_chunks_content_fts" in offline_sql
    assert "to_tsvector('english', content)" in offline_sql


def test_migrations_reach_head_revision(offline_sql: str) -> None:
    assert "INSERT INTO alembic_version (version_num) VALUES ('0001')" in offline_sql
    assert "UPDATE alembic_version SET version_num='0002'" in offline_sql
