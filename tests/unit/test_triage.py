"""Deterministic signals, relevance policy and triage decisions (TASK-018)."""

from datetime import UTC, datetime, timedelta

import pytest

from harness.application.services.triage import (
    TriageDecision,
    TriagePolicy,
    TriageService,
    policy_from_settings,
)
from harness.config.settings import (
    ProcessingSettings,
    RelevanceWeightSettings,
    Settings,
)
from harness.domain.artifacts.parsing import ParsedDocument, ParsedPart, PartType
from harness.domain.triage.relevance import (
    RelevanceComponents,
    RelevanceWeights,
    derive_components,
    score_relevance,
)
from harness.domain.triage.signals import (
    compute_signals,
    repeated_block_ratio,
    unique_token_ratio,
)

NOW = datetime(2026, 8, 16, tzinfo=UTC)


def document(*parts: ParsedPart) -> ParsedDocument:
    return ParsedDocument(parts=list(parts))


def section(text: str, ordinal: int = 0, **metadata: object) -> ParsedPart:
    return ParsedPart(
        part_type=PartType.SECTION,
        ordinal=ordinal,
        text_content=text,
        metadata=dict(metadata),
    )


def rich_document() -> ParsedDocument:
    body = " ".join(f"architectural detail number {n}" for n in range(120))
    return document(
        section("Checkout flow", 0, heading="Checkout flow", links=[{"href": "/a"}] * 8),
        section(body, 1, heading="Backend services", links=[{"href": "/b"}] * 6),
        ParsedPart(part_type=PartType.IMAGE, ordinal=2, binary_content=b"png"),
        ParsedPart(part_type=PartType.IMAGE, ordinal=3, binary_content=b"png"),
    )


class TestSignals:
    def test_unique_token_ratio(self) -> None:
        assert unique_token_ratio("a b c") == 1.0
        assert unique_token_ratio("a a a a") == 0.25
        assert unique_token_ratio("") == 0.0

    def test_repeated_block_ratio(self) -> None:
        assert repeated_block_ratio([]) == 0.0
        assert repeated_block_ratio(["x", "y"]) == 0.0
        assert repeated_block_ratio(["x", "x"]) == 0.5
        assert repeated_block_ratio(["x", "X  "]) == 0.5  # normalized

    def test_counts_headings_images_and_links(self) -> None:
        signals = compute_signals(rich_document(), attachment_count=1, hierarchy_depth=2)
        assert signals.heading_count == 2
        assert signals.image_count == 2
        assert signals.attachment_count == 1
        assert signals.link_count == 14
        assert signals.hierarchy_depth == 2
        assert signals.text_length > 0

    def test_modification_age_is_computed_in_days(self) -> None:
        signals = compute_signals(
            rich_document(), modified_at=NOW - timedelta(days=30), now=NOW
        )
        assert signals.modification_age_days == pytest.approx(30.0)

    def test_unknown_modification_date_leaves_age_none(self) -> None:
        assert compute_signals(rich_document()).modification_age_days is None


class TestRelevanceWeights:
    def test_defaults_match_the_spec_and_sum_to_one(self) -> None:
        weights = RelevanceWeights()
        assert weights.total == pytest.approx(1.0)
        assert (weights.structural, weights.semantic) == (0.20, 0.20)

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            RelevanceWeights(structural=0.9)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            RelevanceWeights(structural=-0.1, semantic=0.5)


class TestRelevanceScoring:
    def test_all_ones_scores_one(self) -> None:
        components = RelevanceComponents(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
        assert score_relevance(components, RelevanceWeights()).value == pytest.approx(1.0)

    def test_all_zeros_scores_zero(self) -> None:
        components = RelevanceComponents(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        assert score_relevance(components, RelevanceWeights()).value == 0.0

    def test_components_must_be_fractions(self) -> None:
        with pytest.raises(ValueError, match="structural"):
            RelevanceComponents(1.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_rich_document_outscores_thin_one(self) -> None:
        rich = derive_components(compute_signals(rich_document(), attachment_count=2))
        thin = derive_components(compute_signals(document(section("hi"))))
        weights = RelevanceWeights()
        assert score_relevance(rich, weights).value > score_relevance(thin, weights).value

    def test_fresher_content_scores_higher(self) -> None:
        fresh = derive_components(
            compute_signals(rich_document(), modified_at=NOW - timedelta(days=1), now=NOW)
        )
        stale = derive_components(
            compute_signals(rich_document(), modified_at=NOW - timedelta(days=2000), now=NOW)
        )
        assert fresh.freshness > stale.freshness

    def test_unknown_age_is_neutral_not_stale(self) -> None:
        assert derive_components(compute_signals(rich_document())).freshness == 0.5

    def test_repetitive_content_is_penalized(self) -> None:
        repeated = "the same sentence over and over again "
        padded = derive_components(compute_signals(document(section(repeated * 40))))
        varied = derive_components(compute_signals(rich_document()))
        assert varied.structural > padded.structural

    def test_weights_change_the_outcome(self) -> None:
        components = RelevanceComponents(1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        structural_heavy = RelevanceWeights(
            structural=1.0,
            semantic=0.0,
            relationship=0.0,
            visual=0.0,
            freshness=0.0,
            source_authority=0.0,
            historical_demand=0.0,
        )
        assert score_relevance(components, structural_heavy).value == pytest.approx(1.0)
        assert score_relevance(components, RelevanceWeights()).value == pytest.approx(0.20)


class TestTriageDecisions:
    def test_rich_document_is_indexed_and_enriched(self) -> None:
        service = TriageService(TriagePolicy(deep_enrichment_threshold=0.4))
        result = service.evaluate(
            rich_document(), attachment_count=2, source_authority=0.9, modified_at=NOW, now=NOW
        )
        assert result.decision is TriageDecision.INDEX_AND_ENRICH
        assert result.enrich and result.index

    def test_moderate_document_is_indexed_without_enrichment(self) -> None:
        service = TriageService(TriagePolicy(index_threshold=0.1, deep_enrichment_threshold=0.99))
        result = service.evaluate(rich_document())
        assert result.decision is TriageDecision.INDEX_ONLY
        assert result.index and not result.enrich

    def test_empty_document_is_skipped(self) -> None:
        result = TriageService().evaluate(document(section("hi")))
        assert result.decision is TriageDecision.SKIP
        assert "insufficient text" in result.reason

    def test_short_text_with_an_image_is_not_skipped_outright(self) -> None:
        doc = document(
            section("hi"),
            ParsedPart(part_type=PartType.IMAGE, ordinal=1, binary_content=b"png"),
        )
        result = TriageService(TriagePolicy(index_threshold=0.0)).evaluate(doc)
        assert result.decision is not TriageDecision.SKIP

    def test_below_index_threshold_is_skipped(self) -> None:
        service = TriageService(TriagePolicy(index_threshold=0.99, deep_enrichment_threshold=0.99))
        result = service.evaluate(rich_document())
        assert result.decision is TriageDecision.SKIP
        assert "below index threshold" in result.reason

    def test_result_carries_signals_and_score_for_audit(self) -> None:
        result = TriageService().evaluate(rich_document(), attachment_count=2)
        assert result.signals.image_count == 2
        assert 0.0 <= result.score.value <= 1.0
        assert result.score.weights.total == pytest.approx(1.0)

    def test_invalid_policy_thresholds_rejected(self) -> None:
        with pytest.raises(ValueError, match="index_threshold"):
            TriagePolicy(index_threshold=0.9, deep_enrichment_threshold=0.1)


class TestPolicyFromSettings:
    def test_uses_configured_weights_and_thresholds(self) -> None:
        settings = Settings(
            processing=ProcessingSettings(
                triage_index_threshold=0.4, image_deep_enrichment_threshold=0.8
            ),
            relevance_weights=RelevanceWeightSettings(
                structural=0.4,
                semantic=0.2,
                relationship=0.1,
                visual=0.1,
                freshness=0.1,
                source_authority=0.05,
                historical_demand=0.05,
            ),
        )
        policy = policy_from_settings(settings)
        assert policy.index_threshold == 0.4
        assert policy.deep_enrichment_threshold == 0.8
        assert policy.weights.structural == 0.4

    def test_configured_weights_must_still_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            RelevanceWeightSettings(structural=0.9)
