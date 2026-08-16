"""Deterministic fake provider (TASK-020).

Makes the whole pipeline runnable and testable without any paid API, which
docs/spec/17_REPO_AND_ENGINEERING.md §5 requires. Output is derived from a
hash of the input, so the same request always yields the same response —
tests can assert on exact values without recording fixtures.

It is a test/dev double, not a model: it produces structurally valid
output, never meaningful analysis.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable
from typing import Any

from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    EmbeddingResponse,
    ImageInput,
    ModelResponse,
    MultimodalRequest,
    RerankRequest,
    RerankResponse,
    RerankResult,
    TextGenerationRequest,
    Usage,
)

DEFAULT_EMBEDDING_DIMENSION = 1536
_WORD = re.compile(r"\w+", re.UNICODE)


def _digest(*parts: str | bytes) -> bytes:
    hasher = hashlib.sha256()
    for part in parts:
        hasher.update(part.encode("utf-8") if isinstance(part, str) else part)
        hasher.update(b"\x00")
    return hasher.digest()


def estimate_tokens(text: str) -> int:
    """Rough token estimate; deterministic and good enough for accounting."""
    return max(1, len(text) // 4)


def deterministic_vector(text: str, dimension: int) -> list[float]:
    """A unit-length vector derived from the text.

    Same text produces the same vector, and different texts produce
    different ones — enough for exercising indexing and similarity paths.
    """
    if dimension < 1:
        raise ValueError("dimension must be >= 1")
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        block = _digest(text, str(counter))
        for index in range(0, len(block), 2):
            if len(values) == dimension:
                break
            raw = int.from_bytes(block[index : index + 2], "big")
            values.append(raw / 65535.0 * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _fill_schema(schema: dict[str, Any], seed: bytes) -> Any:
    """Build a minimal instance satisfying a simple JSON schema."""
    # `enum` is checked first: an enum schema often omits `type`, and
    # defaulting it to "object" would silently produce {} instead of a
    # valid choice.
    if "enum" in schema:
        options = list(schema["enum"])
        return options[seed[0] % len(options)] if options else None
    schema_type = schema.get("type", "object")
    if schema_type == "object":
        properties: dict[str, Any] = schema.get("properties", {})
        required = schema.get("required", list(properties))
        return {
            key: _fill_schema(properties.get(key, {"type": "string"}), _digest(seed, key))
            for key in required
        }
    if schema_type == "array":
        item_schema = schema.get("items", {"type": "string"})
        return [_fill_schema(item_schema, _digest(seed, "0"))]
    if schema_type == "integer":
        return int.from_bytes(seed[:2], "big") % 100
    if schema_type == "number":
        return round(int.from_bytes(seed[:2], "big") / 65535.0, 4)
    if schema_type == "boolean":
        return seed[0] % 2 == 0
    return f"fake-{seed[:4].hex()}"


class FakeProvider:
    """Satisfies harness.domain.models.ports.ModelProvider."""

    name = "fake"

    def __init__(
        self,
        *,
        embedding_dimension: int = DEFAULT_EMBEDDING_DIMENSION,
        text_factory: Callable[[str], str] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self._dimension = embedding_dimension
        self._text_factory = text_factory
        self._fail_with = fail_with
        self.calls: list[str] = []

    def supports(self, capability: Capability) -> bool:
        return capability in (
            Capability.TEXT,
            Capability.MULTIMODAL,
            Capability.EMBEDDING,
            Capability.RERANK,
        )

    async def generate_text(
        self, request: TextGenerationRequest, model: str
    ) -> ModelResponse:
        self._maybe_fail()
        self.calls.append(f"text:{model}")
        return self._respond(
            model=model,
            prompt=request.prompt,
            system=request.system,
            json_schema=request.json_schema,
            images=(),
        )

    async def generate_multimodal(
        self, request: MultimodalRequest, model: str
    ) -> ModelResponse:
        self._maybe_fail()
        self.calls.append(f"multimodal:{model}")
        return self._respond(
            model=model,
            prompt=request.prompt,
            system=request.system,
            json_schema=request.json_schema,
            images=tuple(request.images),
        )

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse:
        self._maybe_fail()
        self.calls.append(f"embed:{model}")
        vectors = [deterministic_vector(text, self._dimension) for text in request.inputs]
        return EmbeddingResponse(
            vectors=vectors,
            provider=self.name,
            model=model,
            usage=Usage(input_tokens=sum(estimate_tokens(t) for t in request.inputs)),
        )

    async def rerank(self, request: RerankRequest, model: str) -> RerankResponse:
        self._maybe_fail()
        self.calls.append(f"rerank:{model}")
        query_terms = set(_WORD.findall(request.query.lower()))
        scored: list[RerankResult] = []
        for index, document in enumerate(request.documents):
            terms = set(_WORD.findall(document.lower()))
            overlap = len(query_terms & terms) / (len(query_terms | terms) or 1)
            scored.append(RerankResult(index=index, score=overlap))
        scored.sort(key=lambda result: (-result.score, result.index))
        if request.top_k is not None:
            scored = scored[: request.top_k]
        return RerankResponse(
            results=scored,
            provider=self.name,
            model=model,
            usage=Usage(input_tokens=estimate_tokens(request.query)),
        )

    def _respond(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None,
        json_schema: dict[str, Any] | None,
        images: tuple[ImageInput, ...],
    ) -> ModelResponse:
        seed = _digest(prompt, system or "", model, *(image.data for image in images))
        structured: dict[str, Any] | None = None
        if json_schema is not None:
            filled = _fill_schema(json_schema, seed)
            structured = filled if isinstance(filled, dict) else {"value": filled}
            text = json.dumps(structured, sort_keys=True)
        elif self._text_factory is not None:
            text = self._text_factory(prompt)
        else:
            text = f"fake response {seed[:6].hex()}"
        return ModelResponse(
            text=text,
            provider=self.name,
            model=model,
            structured=structured,
            usage=Usage(
                input_tokens=estimate_tokens(prompt) + 85 * len(images),
                output_tokens=estimate_tokens(text),
            ),
        )

    def _maybe_fail(self) -> None:
        if self._fail_with is not None:
            raise self._fail_with
