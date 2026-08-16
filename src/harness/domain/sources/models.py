"""Connector value objects (docs/spec/04_CONNECTORS.md).

A DiscoveredArtifact is the cheap descriptor a connector can produce
without downloading content: enough to decide whether the artifact changed
and therefore whether it must be fetched at all (spec section 3).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ArtifactType:
    """Common artifact_type values produced by connectors."""

    PAGE = "page"
    ATTACHMENT = "attachment"
    FILE = "file"


@dataclass(slots=True)
class ConnectionResult:
    ok: bool
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveredArtifact:
    external_id: str
    source_uri: str
    artifact_type: str
    title: str | None = None
    version: str | None = None
    parent_external_id: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.external_id:
            raise ValueError("external_id must not be empty")
        if not self.source_uri:
            raise ValueError("source_uri must not be empty")
