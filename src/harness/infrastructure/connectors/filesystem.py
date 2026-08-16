"""Local filesystem connector (TASK-013, docs/spec/04_CONNECTORS.md §5).

Recursively discovers configured extensions under a root directory.
External IDs are the POSIX-style path relative to the root, so the same
tree yields the same IDs on any machine — a requirement for idempotent
re-ingestion.

Versions are derived from mtime and size, which is enough to detect
changes without reading file contents during discovery.
"""

import mimetypes
from collections.abc import AsyncIterator, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.processing.models import PermanentProcessingError
from harness.domain.sources.models import (
    ArtifactType,
    ConnectionResult,
    DiscoveredArtifact,
)

DEFAULT_EXTENSIONS: tuple[str, ...] = (
    ".pdf",
    ".docx",
    ".pptx",
    ".html",
    ".htm",
    ".md",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)


def _normalize_extensions(extensions: Iterable[str]) -> frozenset[str]:
    return frozenset(
        ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions
    )


class FilesystemConnector:
    """Satisfies harness.domain.sources.ports.SourceConnector."""

    def __init__(
        self,
        root: Path,
        *,
        extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    ) -> None:
        self._root = Path(root)
        self._extensions = _normalize_extensions(extensions)

    async def test_connection(self) -> ConnectionResult:
        if not self._root.exists():
            return ConnectionResult(ok=False, message=f"root does not exist: {self._root}")
        if not self._root.is_dir():
            return ConnectionResult(ok=False, message=f"root is not a directory: {self._root}")
        return ConnectionResult(
            ok=True,
            message="ok",
            detail={"root": str(self._root), "extensions": sorted(self._extensions)},
        )

    async def discover(self, cursor: str | None = None) -> AsyncIterator[DiscoveredArtifact]:
        """Yield artifacts in deterministic (sorted) order.

        The cursor is the last external_id returned by a previous run;
        discovery resumes strictly after it.
        """
        for path in sorted(self._root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self._extensions:
                continue
            external_id = path.relative_to(self._root).as_posix()
            if cursor is not None and external_id <= cursor:
                continue
            stat = path.stat()
            yield DiscoveredArtifact(
                external_id=external_id,
                source_uri=path.as_uri(),
                artifact_type=ArtifactType.FILE,
                title=path.name,
                version=self._version_of(stat.st_mtime_ns, stat.st_size),
                mime_type=mimetypes.guess_type(path.name)[0],
                size_bytes=stat.st_size,
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                metadata={"relative_path": external_id},
            )

    async def fetch(self, artifact: DiscoveredArtifact) -> FetchedArtifact:
        path = self._root / artifact.external_id
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise PermanentProcessingError(f"file disappeared: {artifact.external_id}") from exc
        return FetchedArtifact(
            external_id=artifact.external_id,
            source_uri=artifact.source_uri,
            filename=path.name,
            content=content,
            mime_type=artifact.mime_type,
            version=artifact.version,
            metadata=dict(artifact.metadata),
        )

    async def get_version(self, artifact: DiscoveredArtifact) -> str:
        path = self._root / artifact.external_id
        try:
            stat = path.stat()
        except FileNotFoundError as exc:
            raise PermanentProcessingError(f"file disappeared: {artifact.external_id}") from exc
        return self._version_of(stat.st_mtime_ns, stat.st_size)

    @staticmethod
    def _version_of(mtime_ns: int, size: int) -> str:
        return f"{mtime_ns}-{size}"
