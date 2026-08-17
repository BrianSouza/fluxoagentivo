"""Cost-aware image enrichment pipeline (TASK-025 to TASK-027).

The prompt fixtures required by spec 09 §6 — happy path, ambiguous,
insufficient evidence and malformed output — are exercised here through
the scripted gateway.
"""

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from harness.application.services.image_enrichment import (
    ImageEnrichmentPipeline,
    is_decorative,
    parse_classification,
    parse_interpretation,
    serialize_interpretation,
)
from harness.domain.enrichment.cache import InMemoryEnrichmentCache, image_cache_key
from harness.domain.enrichment.models import ImageCategory
from harness.domain.models.contracts import ModelResponse, MultimodalRequest
from harness.infrastructure.ocr.engines import CallableOcrEngine, NullOcrEngine
from harness.infrastructure.prompts.registry import PromptRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.from_directory(REPO_ROOT / "prompts")


def png(size: tuple[int, int] = (400, 300), noisy: bool = True) -> bytes:
    image = Image.new("RGB", size, (240, 240, 240))
    if noisy:
        for x in range(0, size[0], 7):
            for y in range(0, size[1], 5):
                image.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class ScriptedGateway:
    """Returns queued structured payloads and records the requests seen."""

    def __init__(self, payloads: list[dict[str, Any] | Exception]) -> None:
        self._payloads = payloads
        self.requests: list[MultimodalRequest] = []

    async def generate_multimodal(self, request: MultimodalRequest) -> ModelResponse:
        self.requests.append(request)
        payload = self._payloads.pop(0) if self._payloads else {}
        if isinstance(payload, Exception):
            raise payload
        return ModelResponse(
            text="", provider="scripted", model="m", structured=dict(payload)
        )


HAPPY_CLASSIFICATION = {
    "relevance": 0.95,
    "categories": ["architecture_diagram"],
    "requires_visual_enrichment": True,
    "reason": "diagram of the checkout services",
}
AMBIGUOUS_CLASSIFICATION = {
    "relevance": 0.35,
    "categories": ["unknown"],
    "requires_visual_enrichment": True,
    "reason": "cannot tell what this depicts",
}
HAPPY_INTERPRETATION = {
    "image_type": "architecture_diagram",
    "summary": "Mobile app calls the Checkout API through a WebView",
    "components": [
        {"name": "Mobile App", "type": "application", "description": "iOS/Android client"},
        {"name": "Checkout API", "type": "service", "description": "Backend service"},
    ],
    "relationships": [
        {"from": "Mobile App", "to": "Checkout API", "relationship": "calls", "confidence": 0.9}
    ],
    "visible_text": ["Checkout"],
    "business_context": "Purchase flow",
    "technical_context": "WebView bridge",
    "uncertainties": [],
}


def build(
    prompts: PromptRegistry,
    payloads: list[dict[str, Any] | Exception],
    *,
    ocr: Any = None,
    threshold: float = 0.70,
    cache: InMemoryEnrichmentCache | None = None,
) -> tuple[ImageEnrichmentPipeline, ScriptedGateway]:
    gateway = ScriptedGateway(payloads)
    pipeline = ImageEnrichmentPipeline(
        gateway,
        classification_prompt=prompts.get("image_classification"),
        diagram_prompt=prompts.get("diagram_interpretation"),
        ocr_engine=ocr or NullOcrEngine(),
        deep_enrichment_threshold=threshold,
        cache=cache,
    )
    return pipeline, gateway


class TestDecorativeFilter:
    def test_tiny_images_are_decorative(self) -> None:
        decorative, reason = is_decorative(png(size=(16, 16), noisy=False))
        assert decorative and "below the meaningful size" in reason

    def test_horizontal_rules_are_decorative(self) -> None:
        decorative, reason = is_decorative(png(size=(900, 70), noisy=False))
        assert decorative and "rule or separator" in reason

    def test_uniform_images_are_decorative(self) -> None:
        decorative, reason = is_decorative(png(size=(400, 300), noisy=False))
        assert decorative and "near-uniform" in reason

    def test_real_diagrams_are_not_decorative(self) -> None:
        decorative, _ = is_decorative(png())
        assert not decorative

    def test_unreadable_bytes_are_not_silently_dropped(self) -> None:
        # A parse problem must not masquerade as "decorative".
        decorative, _ = is_decorative(b"not an image")
        assert not decorative

    async def test_decorative_images_never_reach_the_model(
        self, prompts: PromptRegistry
    ) -> None:
        pipeline, gateway = build(prompts, [])
        result = await pipeline.run(png(size=(12, 12), noisy=False))
        assert result.classification.category is ImageCategory.DECORATIVE
        assert not result.enriched
        assert gateway.requests == []  # no paid call at all


class TestCostAwareRouting:
    async def test_happy_path_classifies_then_interprets(
        self, prompts: PromptRegistry
    ) -> None:
        pipeline, gateway = build(prompts, [HAPPY_CLASSIFICATION, HAPPY_INTERPRETATION])
        result = await pipeline.run(png(), page_title="Checkout flow")
        assert result.classification.category is ImageCategory.ARCHITECTURE_DIAGRAM
        assert result.enriched
        assert result.interpretation is not None
        assert len(gateway.requests) == 2
        assert [r.task.value for r in gateway.requests] == [
            "classification",
            "diagram_interpretation",
        ]

    async def test_ambiguous_image_below_threshold_is_not_deeply_enriched(
        self, prompts: PromptRegistry
    ) -> None:
        pipeline, gateway = build(prompts, [AMBIGUOUS_CLASSIFICATION])
        result = await pipeline.run(png())
        assert not result.enriched
        assert result.skipped_reason is not None
        assert "below deep enrichment threshold" in result.skipped_reason
        assert len(gateway.requests) == 1  # classification only

    async def test_classifier_saying_no_value_skips_interpretation(
        self, prompts: PromptRegistry
    ) -> None:
        payload = dict(HAPPY_CLASSIFICATION, requires_visual_enrichment=False)
        pipeline, gateway = build(prompts, [payload])
        result = await pipeline.run(png())
        assert not result.enriched
        assert len(gateway.requests) == 1

    async def test_classifier_marking_decorative_stops_the_pipeline(
        self, prompts: PromptRegistry
    ) -> None:
        payload = {
            "relevance": 0.1,
            "categories": ["decorative"],
            "requires_visual_enrichment": False,
            "reason": "company logo",
        }
        pipeline, _ = build(prompts, [payload])
        result = await pipeline.run(png())
        assert result.classification.is_decorative
        assert result.skipped_reason == "classified as decorative"

    async def test_threshold_comes_from_configuration(
        self, prompts: PromptRegistry
    ) -> None:
        pipeline, gateway = build(
            prompts, [AMBIGUOUS_CLASSIFICATION, HAPPY_INTERPRETATION], threshold=0.3
        )
        result = await pipeline.run(png())
        assert result.enriched
        assert len(gateway.requests) == 2


class TestOcr:
    async def test_ocr_text_is_passed_into_the_prompts(
        self, prompts: PromptRegistry
    ) -> None:
        ocr = CallableOcrEngine(lambda _: "Checkout API", name="stub")
        pipeline, gateway = build(
            prompts, [HAPPY_CLASSIFICATION, HAPPY_INTERPRETATION], ocr=ocr
        )
        result = await pipeline.run(png())
        assert result.ocr.text == "Checkout API"
        assert "Checkout API" in gateway.requests[0].prompt
        assert "Checkout API" in gateway.requests[1].prompt

    async def test_null_engine_yields_no_text(self, prompts: PromptRegistry) -> None:
        pipeline, _ = build(prompts, [HAPPY_CLASSIFICATION, HAPPY_INTERPRETATION])
        result = await pipeline.run(png())
        assert not result.ocr.has_text
        assert result.ocr.engine == "none"


class TestCaching:
    async def test_identical_image_reuses_the_interpretation(
        self, prompts: PromptRegistry
    ) -> None:
        cache = InMemoryEnrichmentCache()
        image = png()

        pipeline, gateway = build(
            prompts, [HAPPY_CLASSIFICATION, HAPPY_INTERPRETATION], cache=cache
        )
        first = await pipeline.run(image)
        assert first.enriched and not first.cached

        pipeline2, gateway2 = build(prompts, [HAPPY_CLASSIFICATION], cache=cache)
        second = await pipeline2.run(image)
        assert second.cached
        assert second.interpretation is not None
        assert second.interpretation.summary == first.interpretation.summary  # type: ignore[union-attr]
        # Only the cheap classification ran the second time.
        assert len(gateway2.requests) == 1

    def test_cache_key_changes_with_prompt_version_and_profile(self) -> None:
        image = b"bytes"
        base = image_cache_key(image, prompt_version="1.0.0", model_profile="image_deep")
        assert base != image_cache_key(
            image, prompt_version="1.1.0", model_profile="image_deep"
        )
        assert base != image_cache_key(
            image, prompt_version="1.0.0", model_profile="synthesis"
        )
        assert base == image_cache_key(
            image, prompt_version="1.0.0", model_profile="image_deep"
        )


class TestParsingAndSafety:
    def test_malformed_output_degrades_to_unknown(self) -> None:
        classification = parse_classification({})
        assert classification.category is ImageCategory.UNKNOWN
        assert classification.relevance == 0.0

    def test_unrecognized_category_becomes_unknown(self) -> None:
        classification = parse_classification({"categories": ["martian_glyph"]})
        assert classification.category is ImageCategory.UNKNOWN

    def test_relevance_is_clamped(self) -> None:
        assert parse_classification({"relevance": 5.0}).relevance == 1.0
        assert parse_classification({"relevance": -2.0}).relevance == 0.0

    def test_relationships_naming_unknown_components_are_demoted(self) -> None:
        # The model asserting a component it never identified must not
        # become a fact; it becomes an uncertainty.
        payload = dict(
            HAPPY_INTERPRETATION,
            relationships=[
                {"from": "Mobile App", "to": "Ghost Service", "relationship": "calls"}
            ],
        )
        interpretation = parse_interpretation(payload)
        assert interpretation.relationships == []
        assert any("unverifiable" in item for item in interpretation.uncertainties)

    def test_insufficient_evidence_output_is_accepted_with_uncertainties(self) -> None:
        payload = {
            "image_type": "unknown",
            "summary": "The image is too low-resolution to interpret",
            "components": [],
            "relationships": [],
            "visible_text": [],
            "uncertainties": ["resolution too low to read labels"],
        }
        interpretation = parse_interpretation(payload)
        assert interpretation.image_type is ImageCategory.UNKNOWN
        assert interpretation.uncertainties

    def test_serialization_round_trips(self) -> None:
        original = parse_interpretation(HAPPY_INTERPRETATION)
        restored = parse_interpretation(serialize_interpretation(original))
        assert restored == original

    async def test_model_failure_propagates(self, prompts: PromptRegistry) -> None:
        pipeline, _ = build(prompts, [RuntimeError("vision model down")])
        with pytest.raises(RuntimeError, match="vision model down"):
            await pipeline.run(png())
