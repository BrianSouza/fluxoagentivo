"""Anthropic adapter (TASK-022, spec §3).

Targets the Messages API. Structured output is requested by instructing
the model with the JSON schema and validating the reply, since the
Messages API expresses schemas through tools rather than a response
format field.
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

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
DEFAULT_API_VERSION = "2023-06-01"
DEFAULT_MAX_OUTPUT_TOKENS = 4096

_STRUCTURED_INSTRUCTION = (
    "Reply with a single JSON object that validates against this JSON schema. "
    "Return only the JSON, with no prose and no code fences.\nSchema: {schema}"
)


class AnthropicProvider:
    """Satisfies harness.domain.models.ports.ModelProvider."""

    name = "anthropic"

    def __init__(self, client: httpx.AsyncClient, *, max_attempts: int = 3) -> None:
        self._client = client
        self._max_attempts = max_attempts

    @classmethod
    def from_api_key(
        cls,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        api_version: str = DEFAULT_API_VERSION,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 120.0,
    ) -> "AnthropicProvider":
        client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"x-api-key": api_key, "anthropic-version": api_version},
            timeout=timeout,
            transport=transport,
        )
        return cls(client)

    def supports(self, capability: Capability) -> bool:
        # No embeddings or reranking endpoint; the gateway routes those
        # capabilities to a provider that offers them.
        return capability in (Capability.TEXT, Capability.MULTIMODAL)

    async def generate_text(
        self, request: TextGenerationRequest, model: str
    ) -> ModelResponse:
        content: list[dict[str, Any]] = [{"type": "text", "text": request.prompt}]
        return await self._messages(
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
        content: list[dict[str, Any]] = []
        for image in request.images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": image.media_type,
                        "data": base64.b64encode(image.data).decode("ascii"),
                    },
                }
            )
        content.append({"type": "text", "text": request.prompt})
        return await self._messages(
            model=model,
            content=content,
            system=request.system,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            json_schema=request.json_schema,
        )

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse:
        raise UnsupportedCapabilityError("anthropic exposes no embeddings endpoint")

    async def rerank(self, request: RerankRequest, model: str) -> RerankResponse:
        raise UnsupportedCapabilityError("anthropic exposes no reranking endpoint")

    async def _messages(
        self,
        *,
        model: str,
        content: list[dict[str, Any]],
        system: str | None,
        temperature: float | None,
        max_output_tokens: int | None,
        json_schema: dict[str, Any] | None,
    ) -> ModelResponse:
        system_prompts: list[str] = [system] if system else []
        if json_schema is not None:
            system_prompts.append(
                _STRUCTURED_INSTRUCTION.format(schema=json.dumps(json_schema, sort_keys=True))
            )

        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
            "messages": [{"role": "user", "content": content}],
        }
        if system_prompts:
            payload["system"] = "\n\n".join(system_prompts)
        if temperature is not None:
            payload["temperature"] = temperature

        data = await self._post_json("/messages", payload)
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        usage = data.get("usage", {})

        structured: dict[str, Any] | None = None
        if json_schema is not None:
            structured = _parse_structured(text)

        return ModelResponse(
            text=text,
            provider=self.name,
            model=model,
            structured=structured,
            usage=Usage(
                input_tokens=int(usage.get("input_tokens", 0)),
                output_tokens=int(usage.get("output_tokens", 0)),
                cached_input_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            ),
        )

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        async def call() -> httpx.Response:
            response = await self._client.post(path, json=payload)
            return raise_for_status(response)

        response = await with_retry(call, max_attempts=self._max_attempts)
        data: dict[str, Any] = response.json()
        return data


def _parse_structured(text: str) -> dict[str, Any]:
    """Parse JSON, tolerating a fenced code block around it."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise StructuredOutputError("anthropic returned output that is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise StructuredOutputError("anthropic returned JSON that is not an object")
    return parsed
