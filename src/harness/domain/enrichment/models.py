"""Enrichment result types (docs/spec/05_PARSERS_AND_MULTIMODAL.md §4-§5).

Enrichment must never claim invisible details as facts (§5), so every
structure carries explicit uncertainty and confidence alongside its
findings — a confident-sounding summary with no uncertainty recorded is
exactly the failure mode the spec warns about.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from harness.domain.common.values import validate_confidence


class ImageCategory(StrEnum):
    """Minimum category set from spec §4."""

    ARCHITECTURE_DIAGRAM = "architecture_diagram"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    FLOWCHART = "flowchart"
    INFRASTRUCTURE_LANDSCAPE = "infrastructure_landscape"
    UI_SCREENSHOT = "ui_screenshot"
    GAMEPLAY_SCREENSHOT = "gameplay_screenshot"
    CHART = "chart"
    TABLE = "table"
    PHOTOGRAPH = "photograph"
    DECORATIVE = "decorative"
    UNKNOWN = "unknown"

    @property
    def is_diagram(self) -> bool:
        return self in _DIAGRAM_CATEGORIES


_DIAGRAM_CATEGORIES = frozenset(
    {
        ImageCategory.ARCHITECTURE_DIAGRAM,
        ImageCategory.SEQUENCE_DIAGRAM,
        ImageCategory.FLOWCHART,
        ImageCategory.INFRASTRUCTURE_LANDSCAPE,
    }
)


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    confidence: float | None = None
    engine: str = "none"

    def __post_init__(self) -> None:
        validate_confidence(self.confidence, field="confidence")

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass(slots=True)
class ImageClassification:
    """Output of the cheap classification route (09_PROMPTS.md §1)."""

    category: ImageCategory
    relevance: float
    requires_visual_enrichment: bool = False
    reason: str = ""

    def __post_init__(self) -> None:
        validate_confidence(self.relevance, field="relevance")

    @property
    def is_decorative(self) -> bool:
        return self.category is ImageCategory.DECORATIVE


@dataclass(frozen=True, slots=True)
class DiagramComponent:
    name: str
    type: str = "unknown"
    description: str = ""


@dataclass(frozen=True, slots=True)
class DiagramRelationship:
    source: str
    target: str
    relationship: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        validate_confidence(self.confidence, field="confidence")


@dataclass(slots=True)
class DiagramInterpretation:
    """Schema-constrained multimodal enrichment (spec §5)."""

    image_type: ImageCategory
    summary: str
    components: list[DiagramComponent] = field(default_factory=list)
    relationships: list[DiagramRelationship] = field(default_factory=list)
    visible_text: list[str] = field(default_factory=list)
    business_context: str = ""
    technical_context: str = ""
    uncertainties: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        known = {component.name for component in self.components}
        unknown = {
            endpoint
            for relationship in self.relationships
            for endpoint in (relationship.source, relationship.target)
            if endpoint not in known
        }
        if unknown:
            # A relationship naming a component that was never identified
            # is the model asserting something it did not see.
            raise ValueError(
                f"relationships reference undeclared components: {sorted(unknown)}"
            )


@dataclass(slots=True)
class PageSynthesis:
    """Fused page-level knowledge (spec §7, 09_PROMPTS.md §3)."""

    title: str
    summary: str
    key_facts: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    relationships: list[DiagramRelationship] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_ids:
            # Synthesis without evidence references is unciteable, which
            # the spec treats as a failure regardless of fluency.
            raise ValueError("page synthesis must reference at least one evidence id")
