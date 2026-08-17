"""Contract tests for the HTTP model adapters (TASK-021, TASK-022).

Every adapter is exercised against a mock transport: no network, no API
key, no cost. Assertions cover both the request we send and the response
we parse, since a wrong request shape fails silently in production.
"""

import json
from typing import Any

import httpx
import pytest

from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    ImageInput,
    MultimodalRequest,
    RerankRequest,
    StructuredOutputError,
    TextGenerationRequest,
    UnsupportedCapabilityError,
)
from harness.domain.processing.models import (
    PermanentProcessingError,
    TransientProcessingError,
)
from harness.infrastructure.models.anthropic import AnthropicProvider
from harness.infrastructure.models.ollama import OllamaProvider
from harness.infrastructure.models.openai_compat import OpenAICompatibleProvider


class Recorder:
    """Captures outgoing requests and replays scripted responses."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self._responses.pop(0) if self._responses else httpx.Response(200, json={})

        return httpx.MockTransport(handle)

    def body(self, index: int = 0) -> dict[str, Any]:
        payload: dict[str, Any] = json.loads(self.requests[index].content)
        return payload


class TestOllama:
    async def test_generate_text_parses_response_and_usage(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={
                        "response": "the checkout uses a webview",
                        "prompt_eval_count": 42,
                        "eval_count": 7,
                    },
                )
            ]
        )
        provider = OllamaProvider.from_base_url(
            "http://ollama:11434", transport=recorder.transport()
        )
        async with httpx.AsyncClient():
            response = await provider.generate_text(
                TextGenerationRequest(prompt="explain checkout", temperature=0.0), "llama3"
            )

        assert response.text == "the checkout uses a webview"
        assert response.provider == "ollama"
        assert response.usage.input_tokens == 42
        assert response.usage.output_tokens == 7
        body = recorder.body()
        assert body["model"] == "llama3"
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0.0

    async def test_multimodal_sends_base64_images(self) -> None:
        recorder = Recorder([httpx.Response(200, json={"response": "a diagram"})])
        provider = OllamaProvider.from_base_url(transport=recorder.transport())
        await provider.generate_multimodal(
            MultimodalRequest(prompt="describe", images=[ImageInput(data=b"PNGDATA")]), "llava"
        )
        assert recorder.body()["images"] == ["UE5HREFUQQ=="]

    async def test_embeddings_are_parsed(self) -> None:
        recorder = Recorder(
            [httpx.Response(200, json={"embeddings": [[0.1, 0.2]], "prompt_eval_count": 3})]
        )
        provider = OllamaProvider.from_base_url(transport=recorder.transport())
        response = await provider.embed(EmbeddingRequest(inputs=["text"]), "nomic")
        assert response.vectors == [[0.1, 0.2]]
        assert response.dimension == 2

    async def test_json_schema_is_forwarded_as_format(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        recorder = Recorder([httpx.Response(200, json={"response": "{}"})])
        provider = OllamaProvider.from_base_url(transport=recorder.transport())
        await provider.generate_text(
            TextGenerationRequest(prompt="p", json_schema=schema), "llama3"
        )
        assert recorder.body()["format"] == schema

    async def test_rerank_is_unsupported(self) -> None:
        provider = OllamaProvider.from_base_url(transport=Recorder([]).transport())
        assert not provider.supports(Capability.RERANK)
        with pytest.raises(UnsupportedCapabilityError):
            await provider.rerank(RerankRequest(query="q", documents=["d"]), "m")

    async def test_server_error_is_transient_and_retried(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(503, json={"error": "loading"}),
                httpx.Response(200, json={"response": "ok"}),
            ]
        )
        provider = OllamaProvider(
            httpx.AsyncClient(base_url="http://ollama:11434", transport=recorder.transport()),
            max_attempts=2,
        )
        # base_delay comes from with_retry's default; two attempts keep it short.
        response = await provider.generate_text(TextGenerationRequest(prompt="p"), "m")
        assert response.text == "ok"
        assert len(recorder.requests) == 2


class TestOpenAICompatible:
    async def test_chat_completion_is_parsed(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={
                        "choices": [{"message": {"content": "an answer"}}],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "prompt_tokens_details": {"cached_tokens": 40},
                        },
                    },
                )
            ]
        )
        provider = OpenAICompatibleProvider.from_api_key(
            "sk-test", transport=recorder.transport()
        )
        response = await provider.generate_text(
            TextGenerationRequest(prompt="question", max_output_tokens=256), "gpt-x"
        )
        assert response.text == "an answer"
        assert response.usage.input_tokens == 100
        assert response.usage.cached_input_tokens == 40
        body = recorder.body()
        assert body["model"] == "gpt-x"
        assert body["max_completion_tokens"] == 256
        assert recorder.requests[0].headers["authorization"] == "Bearer sk-test"

    async def test_images_are_sent_as_data_urls(self) -> None:
        recorder = Recorder(
            [httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})]
        )
        provider = OpenAICompatibleProvider.from_api_key("k", transport=recorder.transport())
        await provider.generate_multimodal(
            MultimodalRequest(
                prompt="describe",
                images=[ImageInput(data=b"PNGDATA", media_type="image/png")],
            ),
            "gpt-x",
        )
        content = recorder.body()["messages"][-1]["content"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")

    async def test_structured_output_is_requested_and_parsed(self) -> None:
        schema = {"type": "object", "properties": {"label": {"type": "string"}}}
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={"choices": [{"message": {"content": '{"label": "diagram"}'}}]},
                )
            ]
        )
        provider = OpenAICompatibleProvider.from_api_key("k", transport=recorder.transport())
        response = await provider.generate_text(
            TextGenerationRequest(prompt="classify", json_schema=schema), "gpt-x"
        )
        assert response.structured == {"label": "diagram"}
        assert recorder.body()["response_format"]["json_schema"]["schema"] == schema

    async def test_invalid_structured_output_raises(self) -> None:
        recorder = Recorder(
            [httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})]
        )
        provider = OpenAICompatibleProvider.from_api_key("k", transport=recorder.transport())
        with pytest.raises(StructuredOutputError):
            await provider.generate_text(
                TextGenerationRequest(prompt="p", json_schema={"type": "object"}), "gpt-x"
            )

    async def test_embeddings_are_ordered_by_index(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={
                        "data": [
                            {"index": 1, "embedding": [0.3]},
                            {"index": 0, "embedding": [0.1]},
                        ],
                        "usage": {"prompt_tokens": 5},
                    },
                )
            ]
        )
        provider = OpenAICompatibleProvider.from_api_key("k", transport=recorder.transport())
        response = await provider.embed(EmbeddingRequest(inputs=["a", "b"]), "embed-x")
        assert response.vectors == [[0.1], [0.3]]

    async def test_rate_limit_is_transient(self) -> None:
        recorder = Recorder([httpx.Response(429, json={"error": "slow down"})])
        provider = OpenAICompatibleProvider(
            httpx.AsyncClient(base_url="https://api.test/v1", transport=recorder.transport()),
            max_attempts=1,
        )
        with pytest.raises(TransientProcessingError):
            await provider.generate_text(TextGenerationRequest(prompt="p"), "m")

    async def test_bad_key_is_permanent(self) -> None:
        recorder = Recorder([httpx.Response(401, json={"error": "bad key"})])
        provider = OpenAICompatibleProvider(
            httpx.AsyncClient(base_url="https://api.test/v1", transport=recorder.transport()),
            max_attempts=3,
        )
        with pytest.raises(PermanentProcessingError):
            await provider.generate_text(TextGenerationRequest(prompt="p"), "m")
        assert len(recorder.requests) == 1  # never retried


class TestAnthropic:
    async def test_messages_response_is_parsed(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={
                        "content": [{"type": "text", "text": "an answer"}],
                        "usage": {
                            "input_tokens": 80,
                            "output_tokens": 12,
                            "cache_read_input_tokens": 30,
                        },
                    },
                )
            ]
        )
        provider = AnthropicProvider.from_api_key("key", transport=recorder.transport())
        response = await provider.generate_text(
            TextGenerationRequest(prompt="question", max_output_tokens=1000), "claude-x"
        )
        assert response.text == "an answer"
        assert response.usage.input_tokens == 80
        assert response.usage.cached_input_tokens == 30
        body = recorder.body()
        assert body["max_tokens"] == 1000
        assert recorder.requests[0].headers["x-api-key"] == "key"
        assert "anthropic-version" in recorder.requests[0].headers

    async def test_max_tokens_is_always_sent(self) -> None:
        # The Messages API rejects requests without max_tokens.
        recorder = Recorder([httpx.Response(200, json={"content": []})])
        provider = AnthropicProvider.from_api_key("k", transport=recorder.transport())
        await provider.generate_text(TextGenerationRequest(prompt="p"), "claude-x")
        assert recorder.body()["max_tokens"] > 0

    async def test_images_precede_text_in_content(self) -> None:
        recorder = Recorder([httpx.Response(200, json={"content": []})])
        provider = AnthropicProvider.from_api_key("k", transport=recorder.transport())
        await provider.generate_multimodal(
            MultimodalRequest(prompt="describe", images=[ImageInput(data=b"PNG")]), "claude-x"
        )
        content = recorder.body()["messages"][0]["content"]
        assert content[0]["type"] == "image"
        assert content[-1]["type"] == "text"

    async def test_schema_is_instructed_and_fenced_json_is_parsed(self) -> None:
        recorder = Recorder(
            [
                httpx.Response(
                    200,
                    json={
                        "content": [
                            {"type": "text", "text": '```json\n{"label": "chart"}\n```'}
                        ]
                    },
                )
            ]
        )
        provider = AnthropicProvider.from_api_key("k", transport=recorder.transport())
        response = await provider.generate_text(
            TextGenerationRequest(prompt="classify", json_schema={"type": "object"}),
            "claude-x",
        )
        assert response.structured == {"label": "chart"}
        assert "JSON schema" in recorder.body()["system"]

    async def test_embeddings_are_unsupported(self) -> None:
        provider = AnthropicProvider.from_api_key("k", transport=Recorder([]).transport())
        assert not provider.supports(Capability.EMBEDDING)
        with pytest.raises(UnsupportedCapabilityError):
            await provider.embed(EmbeddingRequest(inputs=["a"]), "m")
