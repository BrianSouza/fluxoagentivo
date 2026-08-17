"""SourceSyncService change detection, independent of any connector."""

from collections.abc import AsyncIterator

import pytest

from harness.application.services.sync import (
    SourceSyncService,
    SyncSummary,
    ingest_key_for,
)
from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import TransientProcessingError
from harness.domain.sources.models import (
    ArtifactType,
    ConnectionResult,
    DiscoveredArtifact,
)


def artifact(external_id: str, version: str) -> DiscoveredArtifact:
    return DiscoveredArtifact(
        external_id=external_id,
        source_uri=f"https://wiki/{external_id}",
        artifact_type=ArtifactType.PAGE,
        version=version,
    )


class StubConnector:
    def __init__(self, artifacts: list[DiscoveredArtifact]) -> None:
        self._artifacts = artifacts
        self.fetched: list[str] = []
        self.fail_transient_on: str | None = None

    async def test_connection(self) -> ConnectionResult:
        return ConnectionResult(ok=True)

    async def discover(self, cursor: str | None) -> AsyncIterator[DiscoveredArtifact]:
        for item in self._artifacts:
            yield item

    async def fetch(self, art: DiscoveredArtifact) -> FetchedArtifact:
        if self.fail_transient_on == art.external_id:
            raise TransientProcessingError("provider unavailable")
        self.fetched.append(art.external_id)
        return FetchedArtifact(
            external_id=art.external_id,
            source_uri=art.source_uri,
            filename=f"{art.external_id}.html",
            content=b"<p>body</p>",
            version=art.version,
        )

    async def get_version(self, art: DiscoveredArtifact) -> str:
        return art.version or ""


async def noop(discovered: DiscoveredArtifact, fetched: FetchedArtifact) -> None:
    return None


async def test_first_sync_fetches_everything() -> None:
    connector = StubConnector([artifact("1", "1"), artifact("2", "1")])
    service = SourceSyncService(connector, known_version=lambda _: None, handle=noop)
    summary = await service.run()
    assert (summary.discovered, summary.fetched, summary.skipped) == (2, 2, 0)


async def test_known_and_unchanged_is_skipped() -> None:
    connector = StubConnector([artifact("1", "3")])
    service = SourceSyncService(connector, known_version=lambda _: "3", handle=noop)
    summary = await service.run()
    assert summary.skipped == 1
    assert connector.fetched == []


async def test_version_change_triggers_refetch() -> None:
    connector = StubConnector([artifact("1", "4")])
    service = SourceSyncService(connector, known_version=lambda _: "3", handle=noop)
    summary = await service.run()
    assert summary.fetched == 1
    assert connector.fetched == ["1"]


async def test_transient_failures_propagate_for_queue_retry() -> None:
    connector = StubConnector([artifact("1", "1")])
    connector.fail_transient_on = "1"
    service = SourceSyncService(connector, known_version=lambda _: None, handle=noop)
    with pytest.raises(TransientProcessingError):
        await service.run()


def test_changed_is_an_alias_for_fetched() -> None:
    assert SyncSummary(fetched=7).changed == 7


def test_ingest_key_is_stable_per_version() -> None:
    art = artifact("1", "2")
    checksum = "ab" * 32
    assert ingest_key_for("confluence", art, checksum) == ingest_key_for(
        "confluence", art, checksum
    )
    assert ingest_key_for("confluence", art, checksum) != ingest_key_for(
        "confluence", artifact("1", "3"), checksum
    )
