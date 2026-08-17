"""Duplicate detection and canonicalization (docs/spec/06_DEDUP_TRIAGE.md §4-§5).

Three levels are supported today: exact (identical checksum), near text
(normalized shingle similarity) and near image (perceptual hash distance).
Semantic duplicates additionally require embeddings and a confirming
classifier, so `DuplicateMethod.SEMANTIC` is defined here but produced by
the search epic once embeddings exist.

Duplicates are NEVER deleted. Detection yields a relationship pointing at
a canonical artifact; the duplicate remains addressable (§5).
"""

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from harness.domain.common.values import validate_confidence

DEFAULT_SHINGLE_SIZE = 3

_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


class DuplicateMethod(StrEnum):
    EXACT = "exact"
    NEAR_TEXT = "near_text"
    NEAR_IMAGE = "near_image"
    SEMANTIC = "semantic"


@dataclass(frozen=True, slots=True)
class DuplicateVerdict:
    """A duplicate relationship, not a deletion instruction."""

    artifact_id: str
    canonical_artifact_id: str
    method: DuplicateMethod
    similarity: float

    def __post_init__(self) -> None:
        validate_confidence(self.similarity, field="similarity")
        if self.artifact_id == self.canonical_artifact_id:
            raise ValueError("an artifact cannot be its own duplicate")


@dataclass(slots=True)
class CanonicalCandidate:
    """Inputs to canonical selection (§5)."""

    artifact_id: str
    source_authority: float = 0.5
    version_ordinal: int = 0
    completeness: float = 0.0
    evidence_richness: float = 0.0
    duplication_ratio: float = 0.0
    hierarchy_depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ranking_key(self) -> tuple[float, int, float, float, float, int, str]:
        """Higher is better; ties break deterministically on artifact_id.

        Order mirrors the spec's factor list: source authority, latest
        valid version, completeness, richer evidence, lower duplication,
        shallower hierarchy.
        """
        return (
            self.source_authority,
            self.version_ordinal,
            self.completeness,
            self.evidence_richness,
            -self.duplication_ratio,
            -self.hierarchy_depth,
            self.artifact_id,
        )


def normalize_text(text: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    Normalization is what lets near-duplicate detection see through
    reformatting, copy-paste drift and inconsistent punctuation.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_accents.casefold()
    return _WHITESPACE.sub(" ", _PUNCTUATION.sub(" ", lowered)).strip()


def shingles(text: str, size: int = DEFAULT_SHINGLE_SIZE) -> set[str]:
    """Overlapping word n-grams of normalized text."""
    if size < 1:
        raise ValueError("shingle size must be >= 1")
    tokens = normalize_text(text).split()
    if not tokens:
        return set()
    if len(tokens) <= size:
        return {" ".join(tokens)}
    return {" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def text_similarity(left: str, right: str, *, size: int = DEFAULT_SHINGLE_SIZE) -> float:
    """Jaccard similarity over word shingles; 1.0 means identical content."""
    left_shingles = shingles(left, size)
    right_shingles = shingles(right, size)
    if not left_shingles and not right_shingles:
        return 1.0
    if not left_shingles or not right_shingles:
        return 0.0
    intersection = len(left_shingles & right_shingles)
    union = len(left_shingles | right_shingles)
    return intersection / union


def image_similarity(hash_a: str, hash_b: str, *, bits: int = 64) -> float:
    """Similarity derived from perceptual-hash Hamming distance."""
    distance = bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")
    return max(0.0, 1.0 - distance / bits)


def select_canonical(candidates: list[CanonicalCandidate]) -> CanonicalCandidate:
    if not candidates:
        raise ValueError("cannot select a canonical artifact from an empty group")
    return max(candidates, key=lambda candidate: candidate.ranking_key)
