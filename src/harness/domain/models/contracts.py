"""Request/response types for the Model Gateway (spec §2).

These are vendor-neutral by construction: nothing here names a provider,
and adapters translate to and from their own wire formats.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from harness.domain.common.values import validate_non_negative


class Capability(StrEnum):
    TEXT = "text"
    MULTIMODAL = "multimodal"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class ModelTask(StrEnum):
    """Logical tasks routed to profiles (spec §5)."""

    CLASSIFICATION = "classification"
    IMAGE_DESCRIPTION = "image_description"
    DIAGRAM_INTERPRETATION = "diagram_interpretation"
    PAGE_SYNTHESIS = "page_synthesis"
    ANSWER_GENERATION = "answer_generation"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass(frozen=True, slots=True)
class ImageInput:
    data: bytes
    media_type: str = "image/png"


@dataclass(slots=True)
class TextGenerationRequest:
    prompt: str
    task: ModelTask = ModelTask.CLASSIFICATION
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    json_schema: dict[str, Any] | None = None
    prompt_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt:
            raise ValueError("prompt must not be empty")


@dataclass(slots=True)
class MultimodalRequest:
    prompt: str
    images: list[ImageInput]
    task: ModelTask = ModelTask.IMAGE_DESCRIPTION
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    json_schema: dict[str, Any] | None = None
    prompt_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt:
            raise ValueError("prompt must not be empty")
        if not self.images:
            raise ValueError("a multimodal request must carry at least one image")


@dataclass(slots=True)
class EmbeddingRequest:
    inputs: list[str]
    task: ModelTask = ModelTask.EMBEDDING
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.inputs:
            raise ValueError("embedding request must carry at least one input")


@dataclass(slots=True)
class RerankRequest:
    query: str
    documents: list[str]
    top_k: int | None = None
    task: ModelTask = ModelTask.RERANK
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.query:
            raise ValueError("rerank query must not be empty")
        if not self.documents:
            raise ValueError("rerank request must carry at least one document")


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0

    def __post_init__(self) -> None:
        validate_non_negative(self.input_tokens, field="input_tokens")
        validate_non_negative(self.output_tokens, field="output_tokens")
        validate_non_negative(self.cached_input_tokens, field="cached_input_tokens")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(slots=True)
class ModelResponse:
    text: str
    provider: str
    model: str
    usage: Usage = Usage()
    latency_ms: int = 0
    structured: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    provider: str
    model: str
    usage: Usage = Usage()
    latency_ms: int = 0

    @property
    def dimension(self) -> int:
        return len(self.vectors[0]) if self.vectors else 0


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


@dataclass(slots=True)
class RerankResponse:
    results: list[RerankResult]
    provider: str
    model: str
    usage: Usage = Usage()
    latency_ms: int = 0


class ModelError(Exception):
    """Base class for gateway failures."""


class UnsupportedCapabilityError(ModelError):
    """Raised when no configured provider offers the requested capability."""


class StructuredOutputError(ModelError):
    """Raised when a provider returns output that is not valid for the schema."""
