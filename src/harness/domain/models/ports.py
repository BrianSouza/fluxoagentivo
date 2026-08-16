"""Ports implemented by model adapters and telemetry sinks."""

from typing import Protocol

from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelResponse,
    MultimodalRequest,
    RerankRequest,
    RerankResponse,
    TextGenerationRequest,
)
from harness.domain.models.telemetry import ModelCall


class ModelGateway(Protocol):
    """Capability interface from docs/spec/08_MODEL_GATEWAY.md §2."""

    async def generate_text(self, request: TextGenerationRequest) -> ModelResponse: ...

    async def generate_multimodal(self, request: MultimodalRequest) -> ModelResponse: ...

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...

    async def rerank(self, request: RerankRequest) -> RerankResponse: ...


class ModelProvider(Protocol):
    """What a concrete adapter implements.

    A provider declares the capabilities it supports; the gateway never
    routes a request to a provider that cannot serve it.
    """

    name: str

    def supports(self, capability: Capability) -> bool: ...

    async def generate_text(
        self, request: TextGenerationRequest, model: str
    ) -> ModelResponse: ...

    async def generate_multimodal(
        self, request: MultimodalRequest, model: str
    ) -> ModelResponse: ...

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse: ...

    async def rerank(self, request: RerankRequest, model: str) -> RerankResponse: ...


class ModelCallSink(Protocol):
    """Receives one record per model call for cost/quality telemetry."""

    def record(self, call: ModelCall) -> None: ...
