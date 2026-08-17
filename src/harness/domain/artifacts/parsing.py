"""Deterministic parsing contracts (docs/spec/05_PARSERS_AND_MULTIMODAL.md).

Parsers decompose a FetchedArtifact into ordered ParsedParts (pages,
sections, slides, paragraphs, images...). Parsing is deterministic — no
LLM is involved at this stage.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

from harness.domain.artifacts.fetching import FetchedArtifact
from harness.domain.common.values import validate_non_negative, validate_sha256


class PartType:
    """Common part_type values; parsers may add more."""

    PAGE = "page"
    SECTION = "section"
    SLIDE = "slide"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    IMAGE = "image"
    IMAGE_REF = "image_ref"


@dataclass(slots=True)
class ParsedPart:
    part_type: str
    ordinal: int
    text_content: str | None = None
    binary_content: bytes | None = None
    checksum_sha256: str | None = None
    location: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_non_negative(self.ordinal, field="ordinal")
        if self.checksum_sha256 is not None:
            validate_sha256(self.checksum_sha256, field="checksum_sha256")
        if self.text_content is None and self.binary_content is None:
            raise ValueError("a parsed part must carry text_content or binary_content")


@dataclass(slots=True)
class ParsedDocument:
    parts: list[ParsedPart]
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text_parts(self) -> list[ParsedPart]:
        return [part for part in self.parts if part.text_content is not None]

    @property
    def image_parts(self) -> list[ParsedPart]:
        return [
            part
            for part in self.parts
            if part.part_type in (PartType.IMAGE, PartType.IMAGE_REF)
        ]


class DocumentParser(Protocol):
    def supports(self, mime_type: str, filename: str) -> bool: ...

    async def parse(self, artifact: FetchedArtifact) -> ParsedDocument: ...
