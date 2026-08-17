"""Artifact entities (docs/spec/02_DATABASE_SCHEMA.md, section 1).

An Artifact is an original item captured from a source system (page, file,
attachment, image...). ArtifactParts are its deterministic decomposition
(sections, slides, embedded images...), forming a tree via parent_part_id.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from harness.domain.common.values import (
    validate_non_negative,
    validate_sha256,
)


@dataclass(slots=True)
class Artifact:
    id: UUID
    source_id: UUID
    external_id: str
    artifact_type: str
    source_uri: str
    checksum_sha256: str
    discovered_at: datetime
    parent_artifact_id: UUID | None = None
    title: str | None = None
    version: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_sha256(self.checksum_sha256, field="checksum_sha256")
        validate_non_negative(self.size_bytes, field="size_bytes")
        if not self.external_id:
            raise ValueError("external_id must not be empty")
        if not self.source_uri:
            raise ValueError("source_uri must not be empty")


@dataclass(slots=True)
class ArtifactPart:
    id: UUID
    artifact_id: UUID
    part_type: str
    ordinal: int
    parent_part_id: UUID | None = None
    location: dict[str, Any] = field(default_factory=dict)
    text_content: str | None = None
    binary_object_key: str | None = None
    checksum_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_non_negative(self.ordinal, field="ordinal")
        if self.checksum_sha256 is not None:
            validate_sha256(self.checksum_sha256, field="checksum_sha256")
