"""Relevance policy (docs/spec/06_DEDUP_TRIAGE.md §3).

The weights are policy, never constants in business code: they arrive from
configuration and this module only applies them. Components not yet
available (semantic signal and historical demand need embeddings and
retrieval telemetry) default to a neutral value rather than silently
counting as zero, so early scores are not systematically depressed.
"""

from dataclasses import dataclass, fields

from harness.domain.common.values import validate_confidence
from harness.domain.triage.signals import DeterministicSignals

WEIGHT_SUM_TOLERANCE = 1e-6

# Scale references for normalizing raw signals into 0..1 components.
_TEXT_LENGTH_SATURATION = 4000
_LINK_SATURATION = 20
_FRESHNESS_HALF_LIFE_DAYS = 180.0
_NEUTRAL = 0.5


@dataclass(frozen=True, slots=True)
class RelevanceWeights:
    """Weights from `06_DEDUP_TRIAGE.md` §3; defaults match the spec."""

    structural: float = 0.20
    semantic: float = 0.20
    relationship: float = 0.15
    visual: float = 0.15
    freshness: float = 0.10
    source_authority: float = 0.10
    historical_demand: float = 0.10

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            if value < 0:
                raise ValueError(f"weight {field.name} must not be negative, got {value!r}")
        if abs(self.total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"relevance weights must sum to 1.0, got {self.total!r}")

    @property
    def total(self) -> float:
        return float(sum(float(getattr(self, field.name)) for field in fields(self)))


@dataclass(frozen=True, slots=True)
class RelevanceComponents:
    structural: float
    semantic: float
    relationship: float
    visual: float
    freshness: float
    source_authority: float
    historical_demand: float

    def __post_init__(self) -> None:
        for field in fields(self):
            validate_confidence(getattr(self, field.name), field=field.name)


@dataclass(frozen=True, slots=True)
class RelevanceScore:
    value: float
    components: RelevanceComponents
    weights: RelevanceWeights

    def meets(self, threshold: float) -> bool:
        return self.value >= threshold


def _saturate(value: float, saturation: float) -> float:
    if saturation <= 0:
        return 0.0
    return min(value / saturation, 1.0)


def structural_score(signals: DeterministicSignals) -> float:
    """Rewards substantial, well-structured, non-repetitive text."""
    length = _saturate(signals.text_length, _TEXT_LENGTH_SATURATION)
    structure = _saturate(signals.heading_count, 5)
    diversity = signals.unique_token_ratio
    penalty = 1.0 - signals.repeated_block_ratio
    return max(0.0, min((0.4 * length + 0.3 * structure + 0.3 * diversity) * penalty, 1.0))


def visual_value(signals: DeterministicSignals) -> float:
    return _saturate(signals.image_count + signals.attachment_count, 4)


def relationship_score(signals: DeterministicSignals) -> float:
    links = _saturate(signals.link_count, _LINK_SATURATION)
    depth = _saturate(signals.hierarchy_depth, 4)
    return min(0.7 * links + 0.3 * depth, 1.0)


def freshness(signals: DeterministicSignals) -> float:
    """Exponential-ish decay; unknown age is neutral, not stale."""
    if signals.modification_age_days is None:
        return _NEUTRAL
    decayed = 1.0 / (1.0 + signals.modification_age_days / _FRESHNESS_HALF_LIFE_DAYS)
    return max(0.0, min(1.0, decayed))


def derive_components(
    signals: DeterministicSignals,
    *,
    semantic: float | None = None,
    source_authority: float = _NEUTRAL,
    historical_demand: float | None = None,
) -> RelevanceComponents:
    return RelevanceComponents(
        structural=structural_score(signals),
        semantic=_NEUTRAL if semantic is None else semantic,
        relationship=relationship_score(signals),
        visual=visual_value(signals),
        freshness=freshness(signals),
        source_authority=source_authority,
        historical_demand=_NEUTRAL if historical_demand is None else historical_demand,
    )


def score_relevance(
    components: RelevanceComponents, weights: RelevanceWeights
) -> RelevanceScore:
    value = (
        weights.structural * components.structural
        + weights.semantic * components.semantic
        + weights.relationship * components.relationship
        + weights.visual * components.visual
        + weights.freshness * components.freshness
        + weights.source_authority * components.source_authority
        + weights.historical_demand * components.historical_demand
    )
    return RelevanceScore(
        value=max(0.0, min(value, 1.0)), components=components, weights=weights
    )
