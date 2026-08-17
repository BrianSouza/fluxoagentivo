"""Incremental source synchronization (docs/spec/04_CONNECTORS.md §3).

Sequence: discover using connector-native version metadata, compare the
external version against what is already known, fetch only what changed,
and leave everything else untouched. Previous versions are preserved
because a new version produces a new ingest key rather than overwriting.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import (
    PermanentProcessingError,
    derive_ingest_key,
)
from harness.domain.sources.models import DiscoveredArtifact
from harness.domain.sources.ports import SourceConnector

KnownVersionLookup = Callable[[str], str | None]
ArtifactHandler = Callable[[DiscoveredArtifact, FetchedArtifact], Awaitable[None]]


@dataclass(slots=True)
class SyncSummary:
    discovered: int = 0
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return self.fetched


def ingest_key_for(source_system: str, artifact: DiscoveredArtifact, checksum: str) -> str:
    return derive_ingest_key(source_system, artifact.source_uri, artifact.version, checksum)


class SourceSyncService:
    """Drives one incremental synchronization pass over a connector."""

    def __init__(
        self,
        connector: SourceConnector,
        *,
        known_version: KnownVersionLookup,
        handle: ArtifactHandler,
    ) -> None:
        self._connector = connector
        self._known_version = known_version
        self._handle = handle

    async def run(self, cursor: str | None = None) -> SyncSummary:
        summary = SyncSummary()
        async for artifact in self._connector.discover(cursor):
            summary.discovered += 1
            if not self._has_changed(artifact):
                summary.skipped += 1
                continue
            try:
                fetched = await self._connector.fetch(artifact)
                await self._handle(artifact, fetched)
            except PermanentProcessingError as exc:
                # Permanent failures are recorded and the pass continues;
                # transient ones propagate so the queue can retry the job.
                summary.failed += 1
                summary.errors.append(f"{artifact.external_id}: {exc}")
                continue
            summary.fetched += 1
        return summary

    def _has_changed(self, artifact: DiscoveredArtifact) -> bool:
        known = self._known_version(artifact.external_id)
        if known is None:
            return True
        return known != (artifact.version or "")
