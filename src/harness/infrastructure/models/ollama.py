"""Ollama adapter for local inference (TASK-021, spec §8).

Local models cost nothing and keep sensitive content on-box, so this is
the default provider for the private_local profile. No domain code
references Ollama — only configuration names it.
"""

import base64
from typing import Any

import httpx

from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelResponse,
    MultimodalRequest,
    RerankRequest,
    RerankResponse,
    TextGenerationRequest,
    UnsupportedCapabilityError,
    Usage,
)
from harness.infrastructure.connectors.errors import raise_for_status, with_retry

DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaProvider:
    """Satisfies harness.domain.models.ports.ModelProvider."""

    name = "ollama"

    def __init__(self, client: httpx.AsyncClient, *, max_attempts: int = 3) -> None:
        self._client = client
        self._max_attempts = max_attempts

    @classmethod
    def from_base_url(
        cls,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
    ) -> "OllamaProvider":
        return cls(
            httpx.AsyncClient(
                base_url=base_url.rstrip("/"), timeout=timeout, transport=transport
            )
        )

    def supports(self, capability: Capability) -> bool:
        # Ollama serves generation and embeddings; reranking has no
        # native endpoint, so the gateway must route it elsewhere.
        return capability in (Capability.TEXT, Capability.MULTIMODAL, Capability.EMBEDDING)

    async def generate_text(
        self, request: TextGenerationRequest, model: str
    ) -> ModelResponse:
        payload = self._generate_payload(
            model=model,
            prompt=request.prompt,
            system=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            json_schema=request.json_schema,
        )
        return await self._generate(payload, model)

    async def generate_multimodal(
        self, request: MultimodalRequest, model: str
    ) -> ModelResponse:
        payload = self._generate_payload(
            model=model,
            prompt=request.prompt,
            system=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            json_schema=request.json_schema,
        )
        payload["images"] = [
            base64.b64encode(image.data).decode("ascii") for image in request.images
        ]
        return await self._generate(payload, model)

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse:
        data = await self._post_json(
            "/api/embed", {"model": model, "input": request.inputs}
        )
        vectors = [[float(value) for value in vector] for vector in data.get("embeddings", [])]
        return EmbeddingResponse(
            vectors=vectors,
            provider=self.name,
            model=model,
            usage=Usage(input_tokens=int(data.get("prompt_eval_count", 0))),
        )

    async def rerank(self, request: RerankRequest, model: str) -> RerankResponse:
        raise UnsupportedCapabilityError("ollama has no native reranking endpoint")

    @staticmethod
    def _generate_payload(
        *,
        model: str,
        prompt: str,
        system: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        json_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_output_tokens is not None:
            options["num_predict"] = max_output_tokens
        payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        if json_schema is not None:
            payload["format"] = json_schema
        return payload

    async def _generate(self, payload: dict[str, Any], model: str) -> ModelResponse:
        data = await self._post_json("/api/generate", payload)
        text = str(data.get("response", ""))
        return ModelResponse(
            text=text,
            provider=self.name,
            model=model,
            usage=Usage(
                input_tokens=int(data.get("prompt_eval_count", 0)),
                output_tokens=int(data.get("eval_count", 0)),
            ),
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def call() -> httpx.Response:
            response = await self._client.post(path, json=payload)
            return raise_for_status(response)

        response = await with_retry(call, max_attempts=self._max_attempts)
        data: dict[str, Any] = response.json()
        return data
