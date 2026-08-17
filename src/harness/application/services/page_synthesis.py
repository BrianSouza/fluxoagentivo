"""Page synthesis fusing text and visual evidence (TASK-028).

Per docs/spec/05_PARSERS_AND_MULTIMODAL.md §7 the synthesizer receives
high-value text, high-value image interpretations, page hierarchy and
source metadata, and produces page-level knowledge. It MUST NOT replace
child evidence: the KnowledgeUnit references evidence, it does not absorb
it.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from harness.application.services.image_enrichment import ImageEnrichmentResult
from harness.domain.enrichment.models import DiagramRelationship, PageSynthesis
from harness.domain.knowledge.models import KnowledgeUnit
from harness.domain.models.contracts import ModelTask, TextGenerationRequest
from harness.domain.prompts.models import PromptTemplate

MAX_EVIDENCE_CHARS = 1200


@dataclass(slots=True)
class TextEvidenceInput:
    evidence_id: str
    content: str
    heading: str | None = None


@dataclass(slots=True)
class ImageEvidenceInput:
    evidence_id: str
    result: ImageEnrichmentResult
    location: dict[str, Any] = field(default_factory=dict)

    @property
    def is_usable(self) -> bool:
        """Only interpreted, non-decorative images inform synthesis."""
        return self.result.enriched and not self.result.classification.is_decorative


class UnsupportedEvidenceError(ValueError):
    """Raised when synthesis cites evidence that was never supplied."""


class PageSynthesizer:
    def __init__(
        self,
        gateway: Any,
        *,
        prompt: PromptTemplate,
        max_evidence_chars: int = MAX_EVIDENCE_CHARS,
    ) -> None:
        self._gateway = gateway
        self._prompt = prompt
        self._max_evidence_chars = max_evidence_chars

    async def synthesize(
        self,
        *,
        page_title: str,
        text_evidence: list[TextEvidenceInput],
        image_evidence: list[ImageEvidenceInput],
        hierarchy: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PageSynthesis:
        usable_images = [item for item in image_evidence if item.is_usable]
        if not text_evidence and not usable_images:
            raise UnsupportedEvidenceError("page synthesis requires at least one evidence item")

        supplied = {item.evidence_id for item in text_evidence} | {
            item.evidence_id for item in usable_images
        }

        request = TextGenerationRequest(
            prompt=self._prompt.render(
                page_title=page_title or "(untitled)",
                hierarchy=" > ".join(hierarchy or []) or "(root)",
                metadata=json.dumps(metadata or {}, sort_keys=True),
                text_evidence=self._render_text(text_evidence),
                image_evidence=self._render_images(usable_images),
            ),
            task=ModelTask.PAGE_SYNTHESIS,
            system=self._prompt.system,
            json_schema=self._prompt.json_schema,
            prompt_version=self._prompt.reference,
        )
        response = await self._gateway.generate_text(request)
        synthesis = parse_synthesis(
            response.structured or {}, fallback_title=page_title, supplied=supplied
        )
        return synthesis

    def _render_text(self, items: list[TextEvidenceInput]) -> str:
        if not items:
            return "(none)"
        lines: list[str] = []
        for item in items:
            body = item.content.strip()[: self._max_evidence_chars]
            heading = f" ({item.heading})" if item.heading else ""
            lines.append(f"[{item.evidence_id}]{heading} {body}")
        return "\n\n".join(lines)

    def _render_images(self, items: list[ImageEvidenceInput]) -> str:
        if not items:
            return "(none)"
        lines: list[str] = []
        for item in items:
            interpretation = item.result.interpretation
            assert interpretation is not None  # guaranteed by is_usable
            components = ", ".join(c.name for c in interpretation.components) or "(none)"
            lines.append(
                f"[{item.evidence_id}] type={interpretation.image_type.value} "
                f"summary={interpretation.summary} components={components}"
            )
        return "\n\n".join(lines)


def parse_synthesis(
    payload: dict[str, Any], *, fallback_title: str, supplied: set[str]
) -> PageSynthesis:
    cited = [str(item) for item in payload.get("evidence_ids", [])]
    # Drop citations the model invented; keeping them would make the unit
    # unciteable at answer time.
    verified = [item for item in cited if item in supplied]
    if not verified:
        # Nothing verifiable came back: fall back to everything supplied,
        # so the unit stays anchored to real evidence.
        verified = sorted(supplied)

    relationships = [
        DiagramRelationship(
            source=str(item.get("from", "")),
            target=str(item.get("to", "")),
            relationship=str(item.get("relationship", "related_to")),
            confidence=(
                float(item["confidence"]) if item.get("confidence") is not None else None
            ),
        )
        for item in payload.get("relationships", [])
        if isinstance(item, dict) and item.get("from") and item.get("to")
    ]

    return PageSynthesis(
        title=str(payload.get("title") or fallback_title or "(untitled)"),
        summary=str(payload.get("summary", "")),
        key_facts=[str(item) for item in payload.get("key_facts", [])],
        concepts=[str(item) for item in payload.get("concepts", [])],
        entities=[str(item) for item in payload.get("entities", [])],
        relationships=relationships,
        evidence_ids=verified,
        metadata={"unverified_citations": [c for c in cited if c not in supplied]},
    )


def to_knowledge_unit(
    synthesis: PageSynthesis,
    *,
    evidence_ids: dict[str, UUID],
    unit_id: UUID | None = None,
    now: datetime | None = None,
) -> KnowledgeUnit:
    """Build the persisted KnowledgeUnit from a synthesis.

    `evidence_ids` maps the string ids used in prompts to real Evidence
    UUIDs, so the unit points at rows rather than prompt-local labels.
    """
    timestamp = now or datetime.now(UTC)
    resolved = [evidence_ids[item] for item in synthesis.evidence_ids if item in evidence_ids]
    if not resolved:
        raise UnsupportedEvidenceError(
            "no synthesis evidence id could be resolved to a stored Evidence row"
        )
    return KnowledgeUnit(
        id=unit_id or uuid4(),
        title=synthesis.title,
        summary=synthesis.summary or synthesis.title,
        version=1,
        status="active",
        created_at=timestamp,
        updated_at=timestamp,
        evidence_ids=resolved,
        metadata={
            "key_facts": synthesis.key_facts,
            "concepts": synthesis.concepts,
            "entities": synthesis.entities,
            "relationships": [
                {"from": r.source, "to": r.target, "relationship": r.relationship}
                for r in synthesis.relationships
            ],
        },
    )
