"""Triage service (TASK-018, docs/spec/06_DEDUP_TRIAGE.md §1).

Decides whether an artifact carries useful knowledge and whether expensive
AI enrichment is justified. It never deletes source artifacts — the
outcome is a decision record attached to the artifact.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from harness.config.settings import Settings, get_settings
from harness.domain.artifacts.parsing import ParsedDocument
from harness.domain.triage.relevance import (
    RelevanceScore,
    RelevanceWeights,
    derive_components,
    score_relevance,
)
from harness.domain.triage.signals import DeterministicSignals, compute_signals


class TriageDecision(StrEnum):
    INDEX_AND_ENRICH = "index_and_enrich"
    INDEX_ONLY = "index_only"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class TriagePolicy:
    """Thresholds are configuration, never constants in business code."""

    weights: RelevanceWeights = RelevanceWeights()
    index_threshold: float = 0.25
    deep_enrichment_threshold: float = 0.70
    min_text_length: int = 40

    def __post_init__(self) -> None:
        if not 0.0 <= self.index_threshold <= self.deep_enrichment_threshold <= 1.0:
            raise ValueError(
                "expected 0 <= index_threshold <= deep_enrichment_threshold <= 1, "
                f"got {self.index_threshold!r} and {self.deep_enrichment_threshold!r}"
            )


def policy_from_settings(settings: Settings | None = None) -> TriagePolicy:
    """Build the policy from configuration (YAML policy file / env vars)."""
    settings = settings or get_settings()
    return TriagePolicy(
        weights=settings.relevance_weights.to_domain(),
        index_threshold=settings.processing.triage_index_threshold,
        deep_enrichment_threshold=settings.processing.image_deep_enrichment_threshold,
    )


@dataclass(frozen=True, slots=True)
class TriageResult:
    decision: TriageDecision
    score: RelevanceScore
    signals: DeterministicSignals
    reason: str

    @property
    def enrich(self) -> bool:
        return self.decision is TriageDecision.INDEX_AND_ENRICH

    @property
    def index(self) -> bool:
        return self.decision is not TriageDecision.SKIP


class TriageService:
    def __init__(self, policy: TriagePolicy | None = None) -> None:
        self._policy = policy or TriagePolicy()

    def evaluate(
        self,
        document: ParsedDocument,
        *,
        attachment_count: int = 0,
        hierarchy_depth: int = 0,
        modified_at: datetime | None = None,
        duplicate_hash_count: int = 0,
        source_authority: float = 0.5,
        semantic: float | None = None,
        historical_demand: float | None = None,
        now: datetime | None = None,
    ) -> TriageResult:
        signals = compute_signals(
            document,
            attachment_count=attachment_count,
            hierarchy_depth=hierarchy_depth,
            modified_at=modified_at,
            duplicate_hash_count=duplicate_hash_count,
            now=now,
        )
        components = derive_components(
            signals,
            semantic=semantic,
            source_authority=source_authority,
            historical_demand=historical_demand,
        )
        score = score_relevance(components, self._policy.weights)

        has_visual_evidence = signals.image_count + signals.attachment_count > 0
        if signals.text_length < self._policy.min_text_length and not has_visual_evidence:
            return TriageResult(
                decision=TriageDecision.SKIP,
                score=score,
                signals=signals,
                reason="insufficient text and no visual evidence",
            )
        if score.value < self._policy.index_threshold:
            return TriageResult(
                decision=TriageDecision.SKIP,
                score=score,
                signals=signals,
                reason=f"relevance {score.value:.3f} below index threshold",
            )
        if score.meets(self._policy.deep_enrichment_threshold):
            return TriageResult(
                decision=TriageDecision.INDEX_AND_ENRICH,
                score=score,
                signals=signals,
                reason=f"relevance {score.value:.3f} justifies enrichment",
            )
        return TriageResult(
            decision=TriageDecision.INDEX_ONLY,
            score=score,
            signals=signals,
            reason=f"relevance {score.value:.3f} below enrichment threshold",
        )
