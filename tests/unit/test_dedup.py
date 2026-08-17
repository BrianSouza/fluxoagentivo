"""Exact, near-text and image deduplication (TASK-015 to TASK-017)."""

import pytest

from harness.application.services.dedup import (
    BoilerplateDetector,
    ExactDuplicateDetector,
    ImageDuplicateDetector,
    NearTextDuplicateDetector,
)
from harness.domain.triage.dedup import (
    CanonicalCandidate,
    DuplicateMethod,
    DuplicateVerdict,
    image_similarity,
    normalize_text,
    select_canonical,
    shingles,
    text_similarity,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


class TestNormalization:
    def test_strips_accents_case_and_punctuation(self) -> None:
        assert normalize_text("Olá,  MUNDO!!") == "ola mundo"

    def test_collapses_whitespace(self) -> None:
        assert normalize_text("a\n\n  b\tc") == "a b c"

    def test_reformatted_text_normalizes_identically(self) -> None:
        assert normalize_text("The Checkout API.") == normalize_text("the   checkout api")


class TestTextSimilarity:
    def test_identical_text_is_one(self) -> None:
        text = "checkout flow uses a webview"
        assert text_similarity(text, text) == 1.0

    def test_punctuation_and_case_changes_stay_identical(self) -> None:
        assert (
            text_similarity("Checkout flow, uses a WebView!", "checkout flow uses a webview")
            == 1.0
        )

    def test_unrelated_text_is_zero(self) -> None:
        assert text_similarity("checkout flow webview", "payroll tax calculation rules") == 0.0

    def test_small_edit_stays_high(self) -> None:
        original = "the mobile checkout flow opens a webview that calls the checkout api"
        edited = "the mobile checkout flow opens a webview which calls the checkout api"
        assert 0.5 < text_similarity(original, edited) < 1.0

    def test_empty_texts_are_equal(self) -> None:
        assert text_similarity("", "") == 1.0
        assert text_similarity("something", "") == 0.0

    def test_shingle_size_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="shingle size"):
            shingles("a b c", 0)


class TestExactDetector:
    def test_first_artifact_is_not_a_duplicate(self) -> None:
        assert ExactDuplicateDetector().add("a1", SHA_A) is None

    def test_identical_checksum_is_flagged(self) -> None:
        detector = ExactDuplicateDetector()
        detector.add("a1", SHA_A)
        verdict = detector.add("a2", SHA_A)
        assert verdict == DuplicateVerdict("a2", "a1", DuplicateMethod.EXACT, 1.0)

    def test_different_checksums_are_independent(self) -> None:
        detector = ExactDuplicateDetector()
        detector.add("a1", SHA_A)
        assert detector.add("a2", SHA_B) is None

    def test_reingesting_the_same_artifact_is_not_a_duplicate_of_itself(self) -> None:
        detector = ExactDuplicateDetector()
        detector.add("a1", SHA_A)
        assert detector.add("a1", SHA_A) is None


class TestNearTextDetector:
    def test_near_identical_documents_are_flagged(self) -> None:
        # A realistic near-duplicate: a long page copied with one word
        # edited. Shingle Jaccard only reads as "near identical" when the
        # edited span is a small fraction of the document, which is
        # exactly the copy-paste-drift case this detector targets.
        detector = NearTextDuplicateDetector(threshold=0.8)
        base = " ".join(f"checkout architecture paragraph {n}" for n in range(30))
        detector.add("a1", base)
        verdict = detector.add("a2", base.replace("paragraph 7", "section 7"))
        assert verdict is not None
        assert verdict.method is DuplicateMethod.NEAR_TEXT
        assert verdict.canonical_artifact_id == "a1"
        assert verdict.similarity >= 0.8

    def test_distinct_documents_are_not_flagged(self) -> None:
        detector = NearTextDuplicateDetector(threshold=0.8)
        detector.add("a1", "the mobile checkout flow opens a webview")
        assert detector.add("a2", "payroll tax rules for contractors in brazil") is None

    def test_threshold_is_respected(self) -> None:
        base = "alpha beta gamma delta epsilon zeta eta theta"
        variant = "alpha beta gamma delta epsilon zeta eta omega"

        strict = NearTextDuplicateDetector(threshold=0.99)
        strict.add("a1", base)
        assert strict.add("a2", variant) is None

        lenient = NearTextDuplicateDetector(threshold=0.5)
        lenient.add("a1", base)
        assert lenient.add("a2", variant) is not None

    def test_invalid_threshold_rejected(self) -> None:
        with pytest.raises(ValueError, match="threshold"):
            NearTextDuplicateDetector(threshold=0.0)
        with pytest.raises(ValueError, match="threshold"):
            NearTextDuplicateDetector(threshold=1.5)

    def test_canonical_is_the_earliest_seen_match(self) -> None:
        detector = NearTextDuplicateDetector(threshold=0.8)
        text = "one two three four five six seven eight nine ten"
        detector.add("first", text)
        detector.add("second", text)
        verdict = detector.add("third", text)
        assert verdict is not None
        assert verdict.canonical_artifact_id == "first"


class TestImageDetector:
    def test_identical_hashes_are_flagged(self) -> None:
        detector = ImageDuplicateDetector(threshold=0.98)
        detector.add("img1", "ffff0000ffff0000")
        verdict = detector.add("img2", "ffff0000ffff0000")
        assert verdict is not None
        assert verdict.method is DuplicateMethod.NEAR_IMAGE
        assert verdict.similarity == 1.0

    def test_one_bit_difference_still_counts_as_duplicate(self) -> None:
        detector = ImageDuplicateDetector(threshold=0.98)
        detector.add("img1", "ffff0000ffff0000")
        verdict = detector.add("img2", "ffff0000ffff0001")
        assert verdict is not None
        assert verdict.similarity == pytest.approx(1 - 1 / 64)

    def test_distant_hashes_are_not_duplicates(self) -> None:
        detector = ImageDuplicateDetector(threshold=0.98)
        detector.add("img1", "ffffffffffffffff")
        assert detector.add("img2", "0000000000000000") is None

    def test_image_similarity_is_symmetric(self) -> None:
        a, b = "ffff0000ffff0000", "ffff0000ffff00f0"
        assert image_similarity(a, b) == image_similarity(b, a)


class TestCanonicalSelection:
    def test_highest_source_authority_wins(self) -> None:
        chosen = select_canonical(
            [
                CanonicalCandidate("low", source_authority=0.2, version_ordinal=9),
                CanonicalCandidate("high", source_authority=0.9, version_ordinal=1),
            ]
        )
        assert chosen.artifact_id == "high"

    def test_latest_version_breaks_authority_ties(self) -> None:
        chosen = select_canonical(
            [
                CanonicalCandidate("v1", source_authority=0.5, version_ordinal=1),
                CanonicalCandidate("v3", source_authority=0.5, version_ordinal=3),
            ]
        )
        assert chosen.artifact_id == "v3"

    def test_lower_duplication_and_shallower_hierarchy_preferred(self) -> None:
        chosen = select_canonical(
            [
                CanonicalCandidate("noisy", duplication_ratio=0.9, hierarchy_depth=5),
                CanonicalCandidate("clean", duplication_ratio=0.1, hierarchy_depth=1),
            ]
        )
        assert chosen.artifact_id == "clean"

    def test_selection_is_deterministic_for_identical_candidates(self) -> None:
        group = [CanonicalCandidate("b"), CanonicalCandidate("a")]
        assert select_canonical(group).artifact_id == select_canonical(group[::-1]).artifact_id

    def test_empty_group_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty group"):
            select_canonical([])


class TestVerdictInvariants:
    def test_artifact_cannot_duplicate_itself(self) -> None:
        with pytest.raises(ValueError, match="its own duplicate"):
            DuplicateVerdict("a", "a", DuplicateMethod.EXACT, 1.0)

    def test_similarity_must_be_a_fraction(self) -> None:
        with pytest.raises(ValueError, match="similarity"):
            DuplicateVerdict("a", "b", DuplicateMethod.EXACT, 1.5)


class TestBoilerplate:
    def test_blocks_repeated_across_documents_are_boilerplate(self) -> None:
        detector = BoilerplateDetector(min_documents=3)
        footer = "Copyright 2026 Example Corp. All rights reserved."
        for index in range(3):
            detector.observe([f"Unique body {index}", footer])
        assert detector.is_boilerplate(footer)
        assert not detector.is_boilerplate("Unique body 0")

    def test_below_threshold_is_not_boilerplate(self) -> None:
        detector = BoilerplateDetector(min_documents=3)
        footer = "Confidential internal document"
        detector.observe([footer])
        detector.observe([footer])
        assert not detector.is_boilerplate(footer)

    def test_repeats_within_one_document_count_once(self) -> None:
        detector = BoilerplateDetector(min_documents=2)
        detector.observe(["same", "same", "same"])
        assert not detector.is_boilerplate("same")

    def test_report_exposes_counts(self) -> None:
        detector = BoilerplateDetector(min_documents=2)
        detector.observe(["Shared footer"])
        detector.observe(["shared   FOOTER"])  # normalizes to the same block
        assert detector.report().is_boilerplate("Shared footer", min_documents=2)

    def test_min_documents_must_be_at_least_two(self) -> None:
        with pytest.raises(ValueError, match="min_documents"):
            BoilerplateDetector(min_documents=1)
