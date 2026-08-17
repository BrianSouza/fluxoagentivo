"""Deterministic fake provider (TASK-020).

The fake is what makes the pipeline runnable without a paid API, so its
determinism is a contract other tests depend on.
"""

import json

import pytest

from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    ImageInput,
    MultimodalRequest,
    RerankRequest,
    TextGenerationRequest,
)
from harness.infrastructure.models.fake import (
    FakeProvider,
    deterministic_vector,
    estimate_tokens,
)


class TestDeterminism:
    async def test_same_prompt_yields_same_text(self) -> None:
        provider = FakeProvider()
        request = TextGenerationRequest(prompt="describe the checkout flow")
        first = await provider.generate_text(request, "m")
        second = await provider.generate_text(request, "m")
        assert first.text == second.text

    async def test_different_prompts_yield_different_text(self) -> None:
        provider = FakeProvider()
        a = await provider.generate_text(TextGenerationRequest(prompt="alpha"), "m")
        b = await provider.generate_text(TextGenerationRequest(prompt="beta"), "m")
        assert a.text != b.text

    async def test_model_name_changes_the_output(self) -> None:
        provider = FakeProvider()
        request = TextGenerationRequest(prompt="same prompt")
        assert (await provider.generate_text(request, "small")).text != (
            await provider.generate_text(request, "large")
        ).text

    async def test_usage_is_reported(self) -> None:
        provider = FakeProvider()
        response = await provider.generate_text(
            TextGenerationRequest(prompt="a" * 400), "m"
        )
        assert response.usage.input_tokens >= 100
        assert response.usage.output_tokens >= 1
        assert response.provider == "fake"


class TestStructuredOutput:
    async def test_fills_a_json_schema(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "image_type": {"enum": ["architecture_diagram", "ui_screenshot"]},
                "summary": {"type": "string"},
                "confidence": {"type": "number"},
                "components": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["image_type", "summary", "confidence", "components"],
        }
        provider = FakeProvider()
        response = await provider.generate_text(
            TextGenerationRequest(prompt="classify", json_schema=schema), "m"
        )
        assert response.structured is not None
        assert set(response.structured) == {
            "image_type",
            "summary",
            "confidence",
            "components",
        }
        assert response.structured["image_type"] in ("architecture_diagram", "ui_screenshot")
        assert isinstance(response.structured["components"], list)
        # The text is the serialized structure, so callers can use either.
        assert json.loads(response.text) == response.structured

    async def test_structured_output_is_deterministic(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
        provider = FakeProvider()
        request = TextGenerationRequest(prompt="p", json_schema=schema)
        first = await provider.generate_text(request, "m")
        second = await provider.generate_text(request, "m")
        assert first.structured == second.structured


class TestEmbeddings:
    async def test_vectors_have_configured_dimension(self) -> None:
        provider = FakeProvider(embedding_dimension=8)
        response = await provider.embed(EmbeddingRequest(inputs=["a", "b"]), "m")
        assert len(response.vectors) == 2
        assert response.dimension == 8

    async def test_same_text_yields_same_vector(self) -> None:
        provider = FakeProvider(embedding_dimension=16)
        response = await provider.embed(EmbeddingRequest(inputs=["repeat", "repeat"]), "m")
        assert response.vectors[0] == response.vectors[1]

    async def test_different_text_yields_different_vector(self) -> None:
        provider = FakeProvider(embedding_dimension=16)
        response = await provider.embed(EmbeddingRequest(inputs=["alpha", "beta"]), "m")
        assert response.vectors[0] != response.vectors[1]

    def test_vectors_are_unit_length(self) -> None:
        vector = deterministic_vector("checkout", 32)
        assert sum(value * value for value in vector) == pytest.approx(1.0, abs=1e-9)

    def test_dimension_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="dimension"):
            deterministic_vector("x", 0)


class TestRerank:
    async def test_orders_by_query_overlap(self) -> None:
        provider = FakeProvider()
        response = await provider.rerank(
            RerankRequest(
                query="checkout webview",
                documents=[
                    "payroll tax rules",
                    "the checkout webview calls the api",
                    "unrelated content",
                ],
            ),
            "m",
        )
        assert response.results[0].index == 1
        assert response.results[0].score > response.results[-1].score

    async def test_top_k_limits_results(self) -> None:
        provider = FakeProvider()
        response = await provider.rerank(
            RerankRequest(query="a b", documents=["a b", "b c", "c d"], top_k=2), "m"
        )
        assert len(response.results) == 2


class TestMultimodalAndCapabilities:
    async def test_image_bytes_change_the_response(self) -> None:
        provider = FakeProvider()
        base = MultimodalRequest(prompt="describe", images=[ImageInput(data=b"one")])
        other = MultimodalRequest(prompt="describe", images=[ImageInput(data=b"two")])
        assert (await provider.generate_multimodal(base, "m")).text != (
            await provider.generate_multimodal(other, "m")
        ).text

    async def test_images_are_charged_input_tokens(self) -> None:
        provider = FakeProvider()
        response = await provider.generate_multimodal(
            MultimodalRequest(prompt="describe", images=[ImageInput(data=b"img")]), "m"
        )
        assert response.usage.input_tokens > estimate_tokens("describe")

    def test_supports_every_capability(self) -> None:
        provider = FakeProvider()
        assert all(provider.supports(capability) for capability in Capability)

    async def test_injected_failure_propagates(self) -> None:
        provider = FakeProvider(fail_with=RuntimeError("provider down"))
        with pytest.raises(RuntimeError, match="provider down"):
            await provider.generate_text(TextGenerationRequest(prompt="x"), "m")

    async def test_custom_text_factory_is_used(self) -> None:
        provider = FakeProvider(text_factory=lambda prompt: f"echo:{prompt}")
        response = await provider.generate_text(TextGenerationRequest(prompt="hi"), "m")
        assert response.text == "echo:hi"
