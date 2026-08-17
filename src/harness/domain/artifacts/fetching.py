"""Value object produced by connectors and consumed by parsers.

Mirrors the FetchedArtifact referenced by the connector and parser
interfaces (docs/spec/04_CONNECTORS.md, 05_PARSERS_AND_MULTIMODAL.md).
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class FetchedArtifact:
    external_id: str
    source_uri: str
    filename: str
    content: bytes
    mime_type: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.external_id:
            raise ValueError("external_id must not be empty")
        if not self.filename:
            raise ValueError("filename must not be empty")
