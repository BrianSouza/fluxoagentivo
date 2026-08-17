"""Page synthesis fusing text and visual evidence (TASK-028).

Acceptance criterion from the backlog: a mixed fixture page produces a
KnowledgeUnit referencing both text and image evidence.
"""

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from harness.application.services.image_enrichment import (
    ImageEnrichmentResult,
    parse_interpretation,
)
from harness.application.services.page_synthesis import (
    ImageEvidenceInput,
    PageSynthesizer,
    TextEvidenceInput,
    UnsupportedEvidenceError,
    parse_synthesis,
    to_knowledge_unit,
)
from harness.domain.enrichment.models import ImageCategory, ImageClassification, OcrResult
from harness.domain.models.contracts import ModelResponse, TextGenerationRequest
from harness.infrastructure.prompts.registry import PromptRegistry

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def prompts() -> PromptRegistry:
    return PromptRegistry.from_directory(REPO_ROOT / "prompts")


class ScriptedTextGateway:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.requests: list[TextGenerationRequest] = []

    async def generate_text(self, request: TextGenerationRequest) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            text="", provider="scripted", model="m", structured=dict(self._payload)
        )


def interpreted_image(summary: str = "App calls the Checkout API") -> ImageEnrichmentResult:
    return ImageEnrichmentResult(
        classification=ImageClassification(
            category=ImageCategory.ARCHITECTURE_DIAGRAM,
            relevance=0.9,
            requires_visual_enrichment=True,
        ),
        ocr=OcrResult(text="Checkout", engine="stub"),
        interpretation=parse_interpretation(
            {
                "image_type": "architecture_diagram",
                "summary": summary,
                "components": [
                    {"name": "Mobile App", "type": "application", "description": ""},
                    {"name": "Checkout API", "type": "service", "description": ""},
                ],
                "relationships": [
                    {"from": "Mobile App", "to": "Checkout API", "relationship": "calls"}
                ],
                "visible_text": ["Checkout"],
                "uncertainties": [],
            }
        ),
    )


def skipped_image() -> ImageEnrichmentResult:
    return ImageEnrichmentResult(
        classification=ImageClassification(
            category=ImageCategory.DECORATIVE, relevance=0.0
        ),
        ocr=OcrResult(text="", engine="none"),
        skipped_reason="decorative",
    )


SYNTHESIS_PAYLOAD = {
    "title": "Checkout flow",
    "summary": "The mobile checkout runs in a WebView that calls the Checkout API.",
    "key_facts": ["The checkout runs inside a WebView"],
    "concepts": ["checkout", "webview"],
    "entities": ["Mobile App", "Checkout API"],
    "relationships": [
        {"from": "Mobile App", "to": "Checkout API", "relationship": "calls"}
    ],
    "evidence_ids": ["text-1", "image-1"],
}


class TestMixedPageSynthesis:
    async def test_mixed_page_cites_both_text_and_image_evidence(
        self, prompts: PromptRegistry
    ) -> None:
        gateway = ScriptedTextGateway(SYNTHESIS_PAYLOAD)
        synthesizer = PageSynthesizer(gateway, prompt=prompts.get("page_synthesis"))

        synthesis = await synthesizer.synthesize(
            page_title="Checkout flow",
            text_evidence=[
                TextEvidenceInput("text-1", "The checkout opens a WebView.", "Overview")
            ],
            image_evidence=[ImageEvidenceInput("image-1", interpreted_image())],
            hierarchy=["Engineering", "Mobile"],
        )

        assert set(synthesis.evidence_ids) == {"text-1", "image-1"}
        assert synthesis.title == "Checkout flow"
        assert synthesis.key_facts

    async def test_knowledge_unit_references_both_modalities(
        self, prompts: PromptRegistry
    ) -> None:
        gateway = ScriptedTextGateway(SYNTHESIS_PAYLOAD)
        synthesizer = PageSynthesizer(gateway, prompt=prompts.get("page_synthesis"))
        synthesis = await synthesizer.synthesize(
            page_title="Checkout flow",
            text_evidence=[TextEvidenceInput("text-1", "The checkout opens a WebView.")],
            image_evidence=[ImageEvidenceInput("image-1", interpreted_image())],
        )

        text_uuid, image_uuid = uuid4(), uuid4()
        unit = to_knowledge_unit(
            synthesis, evidence_ids={"text-1": text_uuid, "image-1": image_uuid}
        )

        assert unit.evidence_ids == [text_uuid, image_uuid]
        assert unit.version == 1
        assert unit.metadata["entities"] == ["Mobile App", "Checkout API"]

    async def test_prompt_receives_both_evidence_blocks(
        self, prompts: PromptRegistry
    ) -> None:
        gateway = ScriptedTextGateway(SYNTHESIS_PAYLOAD)
        synthesizer = PageSynthesizer(gateway, prompt=prompts.get("page_synthesis"))
        await synthesizer.synthesize(
            page_title="Checkout flow",
            text_evidence=[TextEvidenceInput("text-1", "WebView detail")],
            image_evidence=[ImageEvidenceInput("image-1", interpreted_image())],
        )
        prompt = gateway.requests[0].prompt
        assert "[text-1]" in prompt
        assert "[image-1]" in prompt
        assert "architecture_diagram" in prompt

    async def test_uninterpreted_images_are_excluded(
        self, prompts: PromptRegistry
    ) -> None:
        gateway = ScriptedTextGateway(dict(SYNTHESIS_PAYLOAD, evidence_ids=["text-1"]))
        synthesizer = PageSynthesizer(gateway, prompt=prompts.get("page_synthesis"))
        await synthesizer.synthesize(
            page_title="p",
            text_evidence=[TextEvidenceInput("text-1", "body")],
            image_evidence=[ImageEvidenceInput("image-1", skipped_image())],
        )
        assert "[image-1]" not in gateway.requests[0].prompt


class TestEvidenceIntegrity:
    def test_invented_citations_are_dropped(self) -> None:
        synthesis = parse_synthesis(
            dict(SYNTHESIS_PAYLOAD, evidence_ids=["text-1", "ghost-9"]),
            fallback_title="t",
            supplied={"text-1"},
        )
        assert synthesis.evidence_ids == ["text-1"]
        assert synthesis.metadata["unverified_citations"] == ["ghost-9"]

    def test_no_verifiable_citation_falls_back_to_supplied_evidence(self) -> None:
        synthesis = parse_synthesis(
            dict(SYNTHESIS_PAYLOAD, evidence_ids=["ghost"]),
            fallback_title="t",
            supplied={"text-1", "image-1"},
        )
        assert synthesis.evidence_ids == ["image-1", "text-1"]

    def test_synthesis_without_any_evidence_is_rejected(self) -> None:
        from harness.domain.enrichment.models import PageSynthesis

        with pytest.raises(ValueError, match="at least one evidence id"):
            PageSynthesis(title="t", summary="s", evidence_ids=[])

    async def test_page_with_no_usable_evidence_raises(
        self, prompts: PromptRegistry
    ) -> None:
        synthesizer = PageSynthesizer(
            ScriptedTextGateway(SYNTHESIS_PAYLOAD), prompt=prompts.get("page_synthesis")
        )
        with pytest.raises(UnsupportedEvidenceError, match="at least one evidence item"):
            await synthesizer.synthesize(
                page_title="p",
                text_evidence=[],
                image_evidence=[ImageEvidenceInput("image-1", skipped_image())],
            )

    def test_unresolvable_evidence_ids_raise(self) -> None:
        synthesis = parse_synthesis(
            SYNTHESIS_PAYLOAD, fallback_title="t", supplied={"text-1", "image-1"}
        )
        with pytest.raises(UnsupportedEvidenceError, match="could not|no synthesis"):
            to_knowledge_unit(synthesis, evidence_ids={})

    def test_missing_title_falls_back_to_the_page_title(self) -> None:
        synthesis = parse_synthesis(
            {"evidence_ids": ["text-1"]}, fallback_title="Fallback", supplied={"text-1"}
        )
        assert synthesis.title == "Fallback"
