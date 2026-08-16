"""Routing gateway: routing, escalation and cost telemetry (TASK-023, TASK-024)."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from harness.config.settings import Settings
from harness.domain.models.contracts import (
    Capability,
    EmbeddingRequest,
    ImageInput,
    ModelResponse,
    ModelTask,
    MultimodalRequest,
    RerankRequest,
    StructuredOutputError,
    TextGenerationRequest,
    UnsupportedCapabilityError,
)
from harness.domain.models.routing import ModelProfile, RoutingPolicy
from harness.domain.models.telemetry import ModelCallStatus, ModelPricing
from harness.infrastructure.db.repositories.model_calls import (
    InMemoryModelCallSink,
    to_record,
)
from harness.infrastructure.models.factory import build_gateway
from harness.infrastructure.models.fake import FakeProvider
from harness.infrastructure.models.gateway import RoutingModelGateway

NOW = datetime(2026, 8, 16, tzinfo=UTC)


class TextOnlyProvider(FakeProvider):
    """A provider that cannot embed — exercises capability routing."""

    name = "text_only"

    def supports(self, capability: Capability) -> bool:
        return capability in (Capability.TEXT, Capability.MULTIMODAL)


def build(
    *,
    profiles: dict[str, ModelProfile],
    routes: dict[ModelTask, str],
    providers: dict[str, object] | None = None,
    sink: InMemoryModelCallSink | None = None,
) -> tuple[RoutingModelGateway, InMemoryModelCallSink]:
    sink = sink or InMemoryModelCallSink()
    gateway = RoutingModelGateway(
        providers=providers or {"fake": FakeProvider(embedding_dimension=8)},  # type: ignore[arg-type]
        policy=RoutingPolicy(profiles=profiles, routes=routes),
        sink=sink,
        now=lambda: NOW,
    )
    return gateway, sink


class TestRouting:
    async def test_task_is_routed_to_its_profile_model(self) -> None:
        gateway, sink = build(
            profiles={
                "cheap": ModelProfile("cheap", "fake", "small-model"),
                "synth": ModelProfile("synth", "fake", "large-model"),
            },
            routes={
                ModelTask.CLASSIFICATION: "cheap",
                ModelTask.PAGE_SYNTHESIS: "synth",
            },
        )
        await gateway.generate_text(
            TextGenerationRequest(prompt="p", task=ModelTask.CLASSIFICATION)
        )
        await gateway.generate_text(
            TextGenerationRequest(prompt="p", task=ModelTask.PAGE_SYNTHESIS)
        )
        assert [call.model for call in sink.calls] == ["small-model", "large-model"]

    async def test_profile_defaults_are_applied(self) -> None:
        provider = FakeProvider()
        captured: list[TextGenerationRequest] = []
        original = provider.generate_text

        async def spy(request: TextGenerationRequest, model: str) -> ModelResponse:
            captured.append(request)
            return await original(request, model)

        provider.generate_text = spy  # type: ignore[method-assign]
        gateway, _ = build(
            profiles={
                "cheap": ModelProfile(
                    "cheap", "fake", "m", temperature=0.0, max_output_tokens=512
                )
            },
            routes={ModelTask.CLASSIFICATION: "cheap"},
            providers={"fake": provider},
        )
        await gateway.generate_text(TextGenerationRequest(prompt="p"))
        assert captured[0].temperature == 0.0
        assert captured[0].max_output_tokens == 512

    async def test_explicit_request_values_win_over_profile_defaults(self) -> None:
        provider = FakeProvider()
        captured: list[TextGenerationRequest] = []
        original = provider.generate_text

        async def spy(request: TextGenerationRequest, model: str) -> ModelResponse:
            captured.append(request)
            return await original(request, model)

        provider.generate_text = spy  # type: ignore[method-assign]
        gateway, _ = build(
            profiles={"cheap": ModelProfile("cheap", "fake", "m", temperature=0.0)},
            routes={ModelTask.CLASSIFICATION: "cheap"},
            providers={"fake": provider},
        )
        await gateway.generate_text(TextGenerationRequest(prompt="p", temperature=0.9))
        assert captured[0].temperature == 0.9

    async def test_capability_routing_skips_a_provider_that_cannot_serve(self) -> None:
        gateway, sink = build(
            profiles={
                "text": ModelProfile("text", "text_only", "t", escalates_to="embed"),
                "embed": ModelProfile("embed", "fake", "e"),
            },
            routes={ModelTask.EMBEDDING: "text"},
            providers={
                "text_only": TextOnlyProvider(),
                "fake": FakeProvider(embedding_dimension=4),
            },
        )
        response = await gateway.embed(EmbeddingRequest(inputs=["a"]))
        assert response.model == "e"
        assert sink.calls[0].provider == "fake"

    async def test_unsupported_capability_raises(self) -> None:
        gateway, _ = build(
            profiles={"text": ModelProfile("text", "text_only", "t")},
            routes={ModelTask.EMBEDDING: "text"},
            providers={"text_only": TextOnlyProvider()},
        )
        with pytest.raises(UnsupportedCapabilityError):
            await gateway.embed(EmbeddingRequest(inputs=["a"]))

    def test_profile_referencing_unconfigured_provider_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unconfigured providers"):
            RoutingModelGateway(
                providers={"fake": FakeProvider()},
                policy=RoutingPolicy(profiles={"p": ModelProfile("p", "ghost", "m")}),
            )


class TestEscalation:
    async def test_rejected_response_escalates_to_the_next_profile(self) -> None:
        gateway, sink = build(
            profiles={
                "cheap": ModelProfile("cheap", "fake", "small", escalates_to="strong"),
                "strong": ModelProfile("strong", "fake", "large"),
            },
            routes={ModelTask.CLASSIFICATION: "cheap"},
        )
        seen: list[str] = []

        def validator(response: ModelResponse) -> bool:
            seen.append(response.model)
            return response.model == "large"

        response = await gateway.generate_text(
            TextGenerationRequest(prompt="p"), validator=validator
        )
        assert response.model == "large"
        assert seen == ["small", "large"]
        # Both attempts are billed and recorded, not just the winner.
        assert [call.model for call in sink.calls] == ["small", "large"]

    async def test_terminal_profile_raises_when_rejected(self) -> None:
        gateway, _ = build(
            profiles={"only": ModelProfile("only", "fake", "m")},
            routes={ModelTask.CLASSIFICATION: "only"},
        )
        with pytest.raises(StructuredOutputError, match="rejected by validator"):
            await gateway.generate_text(
                TextGenerationRequest(prompt="p"), validator=lambda _: False
            )

    async def test_local_only_profile_does_not_escalate_off_box(self) -> None:
        gateway, _ = build(
            profiles={
                "local": ModelProfile(
                    "local", "fake", "tiny", escalates_to="cloud", local_only=True
                ),
                "cloud": ModelProfile("cloud", "fake", "big"),
            },
            routes={ModelTask.CLASSIFICATION: "local"},
        )
        with pytest.raises(StructuredOutputError):
            await gateway.generate_text(
                TextGenerationRequest(prompt="sensitive"), validator=lambda _: False
            )


class TestTelemetry:
    async def test_records_cost_usage_and_attribution(self) -> None:
        artifact_id = uuid4()
        gateway, sink = build(
            profiles={
                "cheap": ModelProfile(
                    "cheap",
                    "fake",
                    "m",
                    pricing=ModelPricing(input_per_million=1.0, output_per_million=2.0),
                )
            },
            routes={ModelTask.CLASSIFICATION: "cheap"},
        )
        await gateway.generate_text(
            TextGenerationRequest(prompt="a" * 4000, prompt_version="1.2.0"),
            artifact_id=artifact_id,
        )
        (call,) = sink.calls
        assert call.status is ModelCallStatus.SUCCEEDED
        assert call.task is ModelTask.CLASSIFICATION
        assert call.profile == "cheap"
        assert call.prompt_version == "1.2.0"
        assert call.artifact_id == artifact_id
        assert call.usage.input_tokens > 0
        assert call.estimated_cost > 0
        assert call.created_at == NOW

    async def test_failed_calls_are_recorded_too(self) -> None:
        gateway, sink = build(
            profiles={"cheap": ModelProfile("cheap", "boom", "m")},
            routes={ModelTask.CLASSIFICATION: "cheap"},
            providers={"boom": FakeProvider(fail_with=RuntimeError("upstream down"))},
        )
        with pytest.raises(RuntimeError, match="upstream down"):
            await gateway.generate_text(TextGenerationRequest(prompt="p"))
        (call,) = sink.calls
        assert call.status is ModelCallStatus.FAILED
        assert call.error_message is not None and "upstream down" in call.error_message

    async def test_embedding_and_rerank_are_recorded(self) -> None:
        gateway, sink = build(
            profiles={"p": ModelProfile("p", "fake", "m")},
            routes={ModelTask.EMBEDDING: "p", ModelTask.RERANK: "p"},
        )
        await gateway.embed(EmbeddingRequest(inputs=["a"]))
        await gateway.rerank(RerankRequest(query="q", documents=["d"]))
        assert [call.task for call in sink.calls] == [ModelTask.EMBEDDING, ModelTask.RERANK]

    async def test_multimodal_is_routed_and_recorded(self) -> None:
        gateway, sink = build(
            profiles={"vision": ModelProfile("vision", "fake", "vision-model")},
            routes={ModelTask.IMAGE_DESCRIPTION: "vision"},
        )
        await gateway.generate_multimodal(
            MultimodalRequest(prompt="describe", images=[ImageInput(data=b"png")])
        )
        assert sink.calls[0].model == "vision-model"

    def test_call_maps_onto_the_model_calls_table(self) -> None:
        sink = InMemoryModelCallSink()
        from harness.domain.models.telemetry import ModelCall

        sink.record(
            ModelCall(
                task=ModelTask.CLASSIFICATION,
                provider="fake",
                model="m",
                status=ModelCallStatus.SUCCEEDED,
                created_at=NOW,
                estimated_cost=0.25,
                profile="cheap",
            )
        )
        record = to_record(sink.calls[0])
        assert record.task == "classification"
        assert record.status == "succeeded"
        assert record.estimated_cost == 0.25
        assert record.metadata_["profile"] == "cheap"
        assert sink.total_cost == 0.25


class TestFactory:
    def test_default_configuration_builds_an_offline_gateway(self) -> None:
        # The shipped defaults must work with no API keys at all.
        gateway = build_gateway(Settings())
        assert isinstance(gateway, RoutingModelGateway)

    async def test_default_gateway_answers_without_any_paid_api(self) -> None:
        sink = InMemoryModelCallSink()
        gateway = build_gateway(Settings(), sink=sink)
        response = await gateway.generate_text(
            TextGenerationRequest(prompt="how does checkout work?")
        )
        assert response.provider == "fake"
        assert sink.calls[0].profile == "cheap_classifier"
