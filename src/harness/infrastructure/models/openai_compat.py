"""OpenAI-compatible adapter (TASK-022, spec §3).

Targets the /v1/chat/completions and /v1/embeddings shape, which is served
by OpenAI itself and by many self-hosted runtimes (vLLM, LM Studio,
llama.cpp server, OpenRouter). One adapter therefore covers both a cloud
provider and a local OpenAI-compatible endpoint.
"""

import base64
import json
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
    StructuredOutputError,
    TextGenerationRequest,
    UnsupportedCapabilityError,
    Usage,
)
from harness.infrastructure.connectors.errors import raise_for_status, with_retry

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatibleProvider:
    """Satisfies harness.domain.models.ports.ModelProvider."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        name: str = "openai",
        max_attempts: int = 3,
    ) -> None:
        self._client = client
        self.name = name
        self._max_attempts = max_attempts

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        name: str = "openai",
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
    ) -> "OpenAICompatibleProvider":
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )
        return cls(client, name=name)

    def supports(self, capability: Capability) -> bool:
        return capability in (Capability.TEXT, Capability.MULTIMODAL, Capability.EMBEDDING)

    async def generate_text(
        self, request: TextGenerationRequest, model: str
    ) -> ModelResponse:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        return await self._chat(
            model=model,
            content=content,
            system=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            json_schema=request.json_schema,
        )

    async def generate_multimodal(
        self, request: MultimodalRequest, model: str
    ) -> ModelResponse:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        for image in request.images:
            encoded = base64.b64encode(image.data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.media_type};base64,{encoded}"},
                }
            )
        return await self._chat(
            model=model,
            content=content,
            system=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            json_schema=request.json_schema,
        )

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse:
        data = await self._post_json(
            "/embeddings", {"model": model, "input": request.inputs}
        )
        items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
        usage = data.get("usage", {})
        return EmbeddingResponse(
            vectors=[[float(v) for v in item["embedding"]] for item in items],
            provider=self.name,
            model=model,
            usage=Usage(input_tokens=int(usage.get("prompt_tokens", 0))),
        )

    async def rerank(self, request: RerankRequest, model: str) -> RerankResponse:
        raise UnsupportedCapabilityError(
            f"{self.name} exposes no OpenAI-compatible reranking endpoint"
        )

    async def _chat(
        self,
        *,
        model: str,
        content: list[dict[str, Any]],
        system: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        json_schema: dict[str, Any] | None,
    ) -> ModelResponse:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})

        payload: dict[str, Any] = {"model": model, "messages": messages}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_completion_tokens"] = max_output_tokens
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "structured_output", "schema": json_schema},
            }

        data = await self._post_json("/chat/completions", payload)
        choices = data.get("choices", [])
        text = str(choices[0]["message"]["content"]) if choices else ""
        usage = data.get("usage", {})
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)

        structured: dict[str, Any] | None = None
        if json_schema is not None:
            structured = _parse_structured(text, provider=self.name)

        return ModelResponse(
            text=text,
            provider=self.name,
            model=model,
            structured=structured,
            usage=Usage(
                input_tokens=int(usage.get("prompt_tokens", 0)),
                output_tokens=int(usage.get("completion_tokens", 0)),
                cached_input_tokens=int(cached or 0),
            ),
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def call() -> httpx.Response:
            response = await self._client.post(path, json=payload)
            return raise_for_status(response)

        response = await with_retry(call, max_attempts=self._max_attempts)
        data: dict[str, Any] = response.json()
        return data


def _parse_structured(text: str, *, provider: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError(
            f"{provider} returned output that is not valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise StructuredOutputError(f"{provider} returned JSON that is not an object")
    return parsed
