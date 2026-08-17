"""Cost-aware image enrichment pipeline (TASK-025 to TASK-027).

Implements the order from docs/spec/05_PARSERS_AND_MULTIMODAL.md §6:

    image -> decorative filter -> OCR -> cheap classifier
          -> relevance score -> deep interpretation only above threshold

Every step before the classifier is deterministic and free, so obviously
worthless images (spacers, icons, rules) never reach a paid model. Deep
interpretation — the expensive call — happens only when the cheap pass
says it would add information.
"""

import io
import json
from dataclasses import dataclass
from typing import Any

from PIL import Image

from harness.domain.enrichment.cache import image_cache_key
from harness.domain.enrichment.models import (
    DiagramComponent,
    DiagramInterpretation,
    DiagramRelationship,
    ImageCategory,
    ImageClassification,
    OcrResult,
)
from harness.domain.enrichment.ports import EnrichmentCache, OcrEngine
from harness.domain.models.contracts import (
    ImageInput,
    ModelTask,
    MultimodalRequest,
)
from harness.domain.prompts.models import PromptTemplate

# An image smaller than this in either dimension carries no readable
# knowledge; it is a bullet, icon or spacer.
MIN_MEANINGFUL_EDGE = 64
# Extreme aspect ratios are horizontal rules and separators.
MAX_MEANINGFUL_ASPECT = 12.0
# A near-uniform image has nothing to interpret.
MIN_COLOR_VARIETY = 4


@dataclass(slots=True)
class ImageEnrichmentResult:
    classification: ImageClassification
    ocr: OcrResult
    interpretation: DiagramInterpretation | None = None
    cached: bool = False
    skipped_reason: str | None = None

    @property
    def enriched(self) -> bool:
        return self.interpretation is not None


def is_decorative(image: bytes) -> tuple[bool, str]:
    """Deterministic pre-filter; returns (decorative, reason)."""
    try:
        with Image.open(io.BytesIO(image)) as handle:
            width, height = handle.width, handle.height
            colors = handle.convert("RGB").getcolors(maxcolors=MIN_COLOR_VARIETY)
    except Exception:
        # Unreadable bytes are not decorative — they are a parse problem,
        # and hiding them here would make the artifact disappear silently.
        return False, ""

    if min(width, height) < MIN_MEANINGFUL_EDGE:
        return True, f"image is {width}x{height}, below the meaningful size threshold"
    longest, shortest = max(width, height), min(width, height)
    if shortest and longest / shortest > MAX_MEANINGFUL_ASPECT:
        return True, f"aspect ratio {longest / shortest:.1f}:1 indicates a rule or separator"
    if colors is not None and len(colors) < MIN_COLOR_VARIETY:
        return True, "image is near-uniform in colour"
    return False, ""


class ImageEnrichmentPipeline:
    def __init__(
        self,
        gateway: Any,
        *,
        classification_prompt: PromptTemplate,
        diagram_prompt: PromptTemplate,
        ocr_engine: OcrEngine,
        deep_enrichment_threshold: float = 0.70,
        cache: EnrichmentCache | None = None,
        model_profile: str = "image_deep",
    ) -> None:
        self._gateway = gateway
        self._classification_prompt = classification_prompt
        self._diagram_prompt = diagram_prompt
        self._ocr = ocr_engine
        self._threshold = deep_enrichment_threshold
        self._cache = cache
        self._model_profile = model_profile

    async def run(
        self,
        image: bytes,
        *,
        page_title: str = "",
        nearby_text: str = "",
        image_metadata: dict[str, Any] | None = None,
    ) -> ImageEnrichmentResult:
        decorative, reason = is_decorative(image)
        if decorative:
            return ImageEnrichmentResult(
                classification=ImageClassification(
                    category=ImageCategory.DECORATIVE, relevance=0.0, reason=reason
                ),
                ocr=OcrResult(text="", engine=self._ocr.name),
                skipped_reason=reason,
            )

        ocr = self._ocr.extract_text(image)
        classification = await self._classify(
            image,
            page_title=page_title,
            nearby_text=nearby_text,
            ocr_text=ocr.text,
            image_metadata=image_metadata or {},
        )

        if classification.is_decorative:
            return ImageEnrichmentResult(
                classification=classification,
                ocr=ocr,
                skipped_reason="classified as decorative",
            )
        if not classification.requires_visual_enrichment:
            return ImageEnrichmentResult(
                classification=classification,
                ocr=ocr,
                skipped_reason="classifier reported no added value from deep enrichment",
            )
        if classification.relevance < self._threshold:
            return ImageEnrichmentResult(
                classification=classification,
                ocr=ocr,
                skipped_reason=(
                    f"relevance {classification.relevance:.2f} below deep enrichment "
                    f"threshold {self._threshold:.2f}"
                ),
            )

        cache_key = image_cache_key(
            image,
            prompt_version=self._diagram_prompt.version,
            model_profile=self._model_profile,
        )
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return ImageEnrichmentResult(
                    classification=classification,
                    ocr=ocr,
                    interpretation=parse_interpretation(cached),
                    cached=True,
                )

        interpretation = await self._interpret(
            image, page_title=page_title, nearby_text=nearby_text, ocr_text=ocr.text
        )
        if self._cache is not None:
            self._cache.set(cache_key, serialize_interpretation(interpretation))
        return ImageEnrichmentResult(
            classification=classification, ocr=ocr, interpretation=interpretation
        )

    async def _classify(
        self,
        image: bytes,
        *,
        page_title: str,
        nearby_text: str,
        ocr_text: str,
        image_metadata: dict[str, Any],
    ) -> ImageClassification:
        prompt = self._classification_prompt
        request = MultimodalRequest(
            prompt=prompt.render(
                page_title=page_title or "(untitled)",
                nearby_text=nearby_text or "(none)",
                ocr_text=ocr_text or "(none)",
                image_metadata=json.dumps(image_metadata, sort_keys=True),
            ),
            images=[ImageInput(data=image)],
            task=ModelTask.CLASSIFICATION,
            system=prompt.system,
            json_schema=prompt.json_schema,
            prompt_version=prompt.reference,
        )
        response = await self._gateway.generate_multimodal(request)
        return parse_classification(response.structured or {})

    async def _interpret(
        self, image: bytes, *, page_title: str, nearby_text: str, ocr_text: str
    ) -> DiagramInterpretation:
        prompt = self._diagram_prompt
        request = MultimodalRequest(
            prompt=prompt.render(
                page_title=page_title or "(untitled)",
                nearby_text=nearby_text or "(none)",
                ocr_text=ocr_text or "(none)",
            ),
            images=[ImageInput(data=image)],
            task=ModelTask.DIAGRAM_INTERPRETATION,
            system=prompt.system,
            json_schema=prompt.json_schema,
            prompt_version=prompt.reference,
        )
        response = await self._gateway.generate_multimodal(request)
        return parse_interpretation(response.structured or {})


def _coerce_category(value: Any) -> ImageCategory:
    try:
        return ImageCategory(str(value))
    except ValueError:
        return ImageCategory.UNKNOWN


def parse_classification(payload: dict[str, Any]) -> ImageClassification:
    categories = payload.get("categories") or []
    category = _coerce_category(categories[0]) if categories else ImageCategory.UNKNOWN
    relevance = float(payload.get("relevance", 0.0) or 0.0)
    return ImageClassification(
        category=category,
        relevance=min(max(relevance, 0.0), 1.0),
        requires_visual_enrichment=bool(payload.get("requires_visual_enrichment", False)),
        reason=str(payload.get("reason", "")),
    )


def parse_interpretation(payload: dict[str, Any]) -> DiagramInterpretation:
    components = [
        DiagramComponent(
            name=str(item.get("name", "")),
            type=str(item.get("type", "unknown")),
            description=str(item.get("description", "")),
        )
        for item in payload.get("components", [])
        if isinstance(item, dict) and item.get("name")
    ]
    known = {component.name for component in components}
    relationships: list[DiagramRelationship] = []
    dropped: list[str] = []
    for item in payload.get("relationships", []):
        if not isinstance(item, dict):
            continue
        source, target = str(item.get("from", "")), str(item.get("to", ""))
        if source not in known or target not in known:
            # The model named something it never identified; record it as
            # an uncertainty instead of asserting it (spec §5).
            dropped.append(f"unverifiable relationship {source!r} -> {target!r}")
            continue
        confidence = item.get("confidence")
        relationships.append(
            DiagramRelationship(
                source=source,
                target=target,
                relationship=str(item.get("relationship", "related_to")),
                confidence=float(confidence) if confidence is not None else None,
            )
        )

    uncertainties = [str(item) for item in payload.get("uncertainties", [])]
    return DiagramInterpretation(
        image_type=_coerce_category(payload.get("image_type")),
        summary=str(payload.get("summary", "")),
        components=components,
        relationships=relationships,
        visible_text=[str(item) for item in payload.get("visible_text", [])],
        business_context=str(payload.get("business_context", "")),
        technical_context=str(payload.get("technical_context", "")),
        uncertainties=uncertainties + dropped,
    )


def serialize_interpretation(interpretation: DiagramInterpretation) -> dict[str, Any]:
    return {
        "image_type": interpretation.image_type.value,
        "summary": interpretation.summary,
        "components": [
            {"name": c.name, "type": c.type, "description": c.description}
            for c in interpretation.components
        ],
        "relationships": [
            {
                "from": r.source,
                "to": r.target,
                "relationship": r.relationship,
                "confidence": r.confidence,
            }
            for r in interpretation.relationships
        ],
        "visible_text": list(interpretation.visible_text),
        "business_context": interpretation.business_context,
        "technical_context": interpretation.technical_context,
        "uncertainties": list(interpretation.uncertainties),
    }
