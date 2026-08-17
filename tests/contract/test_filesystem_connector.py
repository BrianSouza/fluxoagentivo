"""Filesystem connector contract tests (TASK-013)."""

from pathlib import Path

import pytest

from harness.application.services.sync import SourceSyncService
from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import PermanentProcessingError
from harness.domain.sources.models import ArtifactType, DiscoveredArtifact
from harness.infrastructure.connectors.filesystem import FilesystemConnector


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "nested").mkdir(parents=True)
    (tmp_path / "docs" / "guide.md").write_text("# Guide")
    (tmp_path / "docs" / "nested" / "spec.pdf").write_bytes(b"%PDF-1.7 fake")
    (tmp_path / "diagram.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "ignored.bin").write_bytes(b"binary")
    (tmp_path / "docs" / "ignored.zip").write_bytes(b"zip")
    return tmp_path


async def collect(connector: FilesystemConnector, cursor: str | None = None) -> list[
    DiscoveredArtifact
]:
    return [item async for item in connector.discover(cursor)]


class TestConnection:
    async def test_ok_for_existing_directory(self, tree: Path) -> None:
        result = await FilesystemConnector(tree).test_connection()
        assert result.ok

    async def test_fails_for_missing_root(self, tmp_path: Path) -> None:
        result = await FilesystemConnector(tmp_path / "nope").test_connection()
        assert not result.ok
        assert "does not exist" in result.message

    async def test_fails_when_root_is_a_file(self, tree: Path) -> None:
        result = await FilesystemConnector(tree / "notes.txt").test_connection()
        assert not result.ok


class TestDiscovery:
    async def test_recurses_and_filters_extensions(self, tree: Path) -> None:
        discovered = await collect(FilesystemConnector(tree))
        ids = {a.external_id for a in discovered}
        assert ids == {
            "diagram.png",
            "docs/guide.md",
            "docs/nested/spec.pdf",
            "notes.txt",
        }
        assert all(a.artifact_type == ArtifactType.FILE for a in discovered)

    async def test_external_ids_are_deterministic_relative_paths(self, tree: Path) -> None:
        first = await collect(FilesystemConnector(tree))
        second = await collect(FilesystemConnector(tree))
        assert [a.external_id for a in first] == [a.external_id for a in second]
        # POSIX-style, root-relative: stable across machines.
        assert "docs/nested/spec.pdf" in {a.external_id for a in first}

    async def test_custom_extension_filter(self, tree: Path) -> None:
        discovered = await collect(FilesystemConnector(tree, extensions=["md", ".PDF"]))
        assert {a.external_id for a in discovered} == {
            "docs/guide.md",
            "docs/nested/spec.pdf",
        }

    async def test_cursor_resumes_after_last_id(self, tree: Path) -> None:
        discovered = await collect(FilesystemConnector(tree), "docs/guide.md")
        assert [a.external_id for a in discovered] == [
            "docs/nested/spec.pdf",
            "notes.txt",
        ]

    async def test_metadata_and_mime_are_populated(self, tree: Path) -> None:
        discovered = await collect(FilesystemConnector(tree))
        pdf = next(a for a in discovered if a.external_id.endswith(".pdf"))
        assert pdf.mime_type == "application/pdf"
        assert pdf.size_bytes == len(b"%PDF-1.7 fake")
        assert pdf.modified_at is not None


class TestFetch:
    async def test_returns_file_bytes(self, tree: Path) -> None:
        connector = FilesystemConnector(tree)
        discovered = await collect(connector)
        guide = next(a for a in discovered if a.external_id == "docs/guide.md")
        fetched = await connector.fetch(guide)
        assert isinstance(fetched, FetchedArtifact)
        assert fetched.content == b"# Guide"
        assert fetched.filename == "guide.md"

    async def test_missing_file_is_permanent_failure(self, tree: Path) -> None:
        connector = FilesystemConnector(tree)
        ghost = DiscoveredArtifact(
            external_id="gone.txt",
            source_uri=(tree / "gone.txt").as_uri(),
            artifact_type=ArtifactType.FILE,
        )
        with pytest.raises(PermanentProcessingError):
            await connector.fetch(ghost)
        with pytest.raises(PermanentProcessingError):
            await connector.get_version(ghost)


class TestIncrementalSync:
    async def test_unchanged_files_are_skipped_and_edits_are_refetched(
        self, tree: Path
    ) -> None:
        connector = FilesystemConnector(tree)
        known: dict[str, str] = {}
        fetched_ids: list[str] = []

        async def handle(
            discovered: DiscoveredArtifact, fetched: FetchedArtifact
        ) -> None:
            known[discovered.external_id] = discovered.version or ""
            fetched_ids.append(discovered.external_id)

        service = SourceSyncService(connector, known_version=known.get, handle=handle)

        first = await service.run()
        assert first.fetched == 4
        assert first.skipped == 0

        fetched_ids.clear()
        second = await service.run()
        assert second.fetched == 0
        assert second.skipped == 4
        assert fetched_ids == []

        # Change one file: size differs, so the derived version changes.
        (tree / "notes.txt").write_text("notes, extended")
        third = await service.run()
        assert third.fetched == 1
        assert third.skipped == 3
        assert fetched_ids == ["notes.txt"]

    async def test_permanent_failures_are_recorded_without_aborting(
        self, tree: Path
    ) -> None:
        connector = FilesystemConnector(tree)

        async def handle(
            discovered: DiscoveredArtifact, fetched: FetchedArtifact
        ) -> None:
            if discovered.external_id == "notes.txt":
                raise PermanentProcessingError("unsupported")

        service = SourceSyncService(connector, known_version=lambda _: None, handle=handle)
        summary = await service.run()
        assert summary.discovered == 4
        assert summary.fetched == 3
        assert summary.failed == 1
        assert summary.errors == ["notes.txt: unsupported"]
