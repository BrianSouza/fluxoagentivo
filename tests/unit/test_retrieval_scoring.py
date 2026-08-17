"""Merge, hybrid scoring and duplicate suppression (TASK-029 to TASK-031, TASK-033)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from harness.domain.retrieval.defaults import (
    ConfigurableSourceAuthority,
    IdentityCanonicalLookup,
)
from harness.domain.retrieval.models import (
    Candidate,
    RetrievalWeights,
    ScoreComponents,
    SearchFilters,
    SearchQuery,
    normalize_query,
)
from harness.domain.retrieval.ports import LexicalHit, VectorHit
from harness.domain.retrieval.scoring import (
    cosine_similarity,
    merge_hits,
    score_candidates,
    suppress_duplicates,
)

NOW = datetime(2026, 8, 17, tzinfo=UTC)


def make_hit_pair(chunk_id: UUID | None = None) -> tuple[LexicalHit, VectorHit]:
    chunk_id = chunk_id or uuid4()
    evidence_id, artifact_id = uuid4(), uuid4()
    lexical = LexicalHit(
        chunk_id=chunk_id, evidence_id=evidence_id, artifact_id=artifact_id,
        content="the checkout uses a webview", rank=0.5,
    )
    vector = VectorHit(
        chunk_id=chunk_id, evidence_id=evidence_id, artifact_id=artifact_id,
        content="the checkout uses a webview", similarity=0.8,
    )
    return lexical, vector


class TestNormalizeQuery:
    def test_trims_and_collapses_whitespace(self) -> None:
        assert normalize_query("  how does   checkout work?  ") == "how does checkout work?"

    def test_preserves_case_and_punctuation(self) -> None:
        # Unlike dedup normalization, search queries keep meaning-bearing
        # punctuation and case for lexical/embedding matching.
        assert normalize_query("Checkout API?") == "Checkout API?"


class TestSearchQuery:
    def test_rejects_empty_text(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            SearchQuery(text="  ")

    def test_rejects_non_positive_top_k(self) -> None:
        with pytest.raises(ValueError, match="top_k"):
            SearchQuery(text="q", top_k=0)

    def test_pool_must_be_at_least_top_k(self) -> None:
        # Spec §2: never rerank top_k directly, always fetch a broader pool.
        with pytest.raises(ValueError, match="candidate_pool_size"):
            SearchQuery(text="q", top_k=50, candidate_pool_size=10)


class TestRetrievalWeights:
    def test_defaults_match_the_spec_and_sum_to_one(self) -> None:
        weights = RetrievalWeights()
        assert weights.total == pytest.approx(1.0)
        assert (weights.semantic, weights.lexical) == (0.35, 0.25)

    def test_weights_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            RetrievalWeights(semantic=0.9)

    def test_negative_weight_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            RetrievalWeights(semantic=-0.1, lexical=0.5)


class TestCosineSimilarity:
    def test_identical_vectors_are_one(self) -> None:
        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors_are_zero(self) -> None:
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_are_negative_one(self) -> None:
        assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_zero_vector_yields_zero_not_a_crash(self) -> None:
        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_mismatched_dimensions_rejected(self) -> None:
        with pytest.raises(ValueError, match="dimension"):
            cosine_similarity([1.0], [1.0, 2.0])


class TestMergeHits:
    def test_chunk_in_both_lists_merges_into_one_candidate(self) -> None:
        lexical, vector = make_hit_pair()
        merged = merge_hits([lexical], [vector])
        assert len(merged) == 1
        candidate = merged[lexical.chunk_id]
        assert candidate.lexical_rank == 0.5
        assert candidate.semantic_similarity == 0.8

    def test_lexical_only_hit_has_no_semantic_similarity(self) -> None:
        lexical, _ = make_hit_pair()
        merged = merge_hits([lexical], [])
        candidate = merged[lexical.chunk_id]
        assert candidate.lexical_rank == 0.5
        assert candidate.semantic_similarity is None

    def test_vector_only_hit_has_no_lexical_rank(self) -> None:
        _, vector = make_hit_pair()
        merged = merge_hits([], [vector])
        candidate = merged[vector.chunk_id]
        assert candidate.semantic_similarity == 0.8
        assert candidate.lexical_rank is None

    def test_distinct_chunks_stay_separate(self) -> None:
        a_lex, a_vec = make_hit_pair()
        b_lex, b_vec = make_hit_pair()
        merged = merge_hits([a_lex, b_lex], [a_vec, b_vec])
        assert len(merged) == 2


class TestScoreCandidates:
    def test_zero_signal_on_a_dimension_yields_zero_score_not_neutral(self) -> None:
        # A chunk the lexical search truly did not find is genuinely
        # irrelevant lexically — unlike triage's "not yet computed" default.
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="x", lexical_rank=None, semantic_similarity=0.9,
        )
        score_candidates([candidate], RetrievalWeights())
        assert candidate.scores is not None
        assert candidate.scores.lexical == 0.0

    def test_lexical_rank_is_normalized_against_the_pool_max(self) -> None:
        a = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="a", lexical_rank=0.2,
        )
        b = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="b", lexical_rank=0.8,
        )
        score_candidates([a, b], RetrievalWeights())
        assert a.scores is not None and b.scores is not None
        assert a.scores.lexical == pytest.approx(0.25)
        assert b.scores.lexical == pytest.approx(1.0)

    def test_negative_similarity_is_clamped_to_zero(self) -> None:
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="x", semantic_similarity=-0.5,
        )
        score_candidates([candidate], RetrievalWeights())
        assert candidate.scores is not None
        assert candidate.scores.semantic == 0.0

    def test_authority_lookup_is_applied(self) -> None:
        source_id = uuid4()
        authority = ConfigurableSourceAuthority({source_id: 0.9}, default=0.2)
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="x", source_id=source_id,
        )
        score_candidates([candidate], RetrievalWeights(), authority=authority)
        assert candidate.scores is not None
        assert candidate.scores.authority == 0.9

    def test_relationship_expanded_candidates_score_the_relationship_component(self) -> None:
        organic = Candidate(chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(), content="a")
        expanded = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(), content="b",
            via_relationship=True,
        )
        score_candidates([organic, expanded], RetrievalWeights())
        assert organic.scores is not None and expanded.scores is not None
        assert organic.scores.relationship == 0.0
        assert expanded.scores.relationship == 1.0

    def test_hybrid_score_is_a_weighted_sum(self) -> None:
        weights = RetrievalWeights(
            semantic=1.0, lexical=0.0, metadata=0.0, authority=0.0,
            freshness=0.0, relationship=0.0,
        )
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="x", semantic_similarity=0.7,
        )
        score_candidates([candidate], weights)
        assert candidate.hybrid_score == pytest.approx(0.7)

    def test_valid_at_penalizes_candidates_outside_the_window(self) -> None:
        weights = RetrievalWeights(
            semantic=1.0, lexical=0.0, metadata=0.0, authority=0.0,
            freshness=0.0, relationship=0.0,
        )
        in_window = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(), content="a",
            semantic_similarity=0.8, valid_from=NOW - timedelta(days=10),
            valid_to=NOW + timedelta(days=10),
        )
        out_of_window = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(), content="b",
            semantic_similarity=0.8, valid_to=NOW - timedelta(days=100),
        )
        score_candidates([in_window, out_of_window], weights, valid_at=NOW)
        assert in_window.hybrid_score > out_of_window.hybrid_score

    def test_score_is_clamped_to_the_unit_interval(self) -> None:
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(),
            content="x", semantic_similarity=1.0, lexical_rank=1.0,
        )
        score_candidates([candidate], RetrievalWeights())
        assert 0.0 <= candidate.hybrid_score <= 1.0


class TestScoreComponentsValidation:
    def test_components_must_be_fractions(self) -> None:
        with pytest.raises(ValueError, match="semantic"):
            ScoreComponents(semantic=1.5)


class TestSuppressDuplicates:
    def make(self, artifact_id: object, score: float) -> Candidate:
        candidate = Candidate(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=artifact_id, content="x",  # type: ignore[arg-type]
        )
        candidate.hybrid_score = score
        return candidate

    def test_identity_lookup_keeps_everything(self) -> None:
        candidates = [self.make(uuid4(), 0.9), self.make(uuid4(), 0.5)]
        kept = suppress_duplicates(candidates, IdentityCanonicalLookup())
        assert len(kept) == 2

    def test_duplicates_are_capped_but_not_deleted_from_the_result(self) -> None:
        group = uuid4()
        artifacts = [uuid4() for _ in range(4)]

        class GroupLookup:
            def canonical_for(self, artifact_id: object) -> object:
                return group

        candidates = [
            self.make(a, score)
            for a, score in zip(artifacts, [0.9, 0.8, 0.7, 0.6], strict=True)
        ]
        kept = suppress_duplicates(candidates, GroupLookup(), max_duplicates=1)  # type: ignore[arg-type]
        assert len(kept) == 2  # canonical + 1 alternate
        assert kept[0].artifact_id == artifacts[0]
        assert kept[0].duplicate_of is None
        assert kept[1].duplicate_of == artifacts[0]

    def test_zero_max_duplicates_keeps_only_the_best_per_group(self) -> None:
        group = uuid4()
        artifacts = [uuid4(), uuid4()]

        class GroupLookup:
            def canonical_for(self, artifact_id: object) -> object:
                return group

        candidates = [self.make(a, s) for a, s in zip(artifacts, [0.9, 0.5], strict=True)]
        kept = suppress_duplicates(candidates, GroupLookup(), max_duplicates=0)  # type: ignore[arg-type]
        assert len(kept) == 1

    def test_negative_max_duplicates_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_duplicates"):
            suppress_duplicates([], IdentityCanonicalLookup(), max_duplicates=-1)

    def test_best_scoring_representative_is_kept_regardless_of_input_order(self) -> None:
        group = uuid4()
        artifacts = [uuid4(), uuid4()]

        class GroupLookup:
            def canonical_for(self, artifact_id: object) -> object:
                return group

        # Worst-scoring candidate listed first; the ranker must still pick
        # the best one as the representative.
        candidates = [self.make(artifacts[0], 0.3), self.make(artifacts[1], 0.95)]
        kept = suppress_duplicates(candidates, GroupLookup(), max_duplicates=0)  # type: ignore[arg-type]
        assert kept[0].artifact_id == artifacts[1]


class TestSourceAuthority:
    def test_unknown_source_falls_back_to_default(self) -> None:
        authority = ConfigurableSourceAuthority({}, default=0.4)
        assert authority.authority_for(uuid4()) == 0.4

    def test_none_source_id_uses_default(self) -> None:
        assert ConfigurableSourceAuthority(default=0.6).authority_for(None) == 0.6

    def test_rejects_out_of_range_values(self) -> None:
        with pytest.raises(ValueError, match="authority"):
            ConfigurableSourceAuthority({uuid4(): 1.5})


def test_search_filters_is_empty() -> None:
    assert SearchFilters().is_empty
    assert not SearchFilters(source_ids=[uuid4()]).is_empty
