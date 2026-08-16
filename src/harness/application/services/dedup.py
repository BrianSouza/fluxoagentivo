"""Deduplication services (TASK-015, TASK-016, TASK-017).

Each detector keeps an index of what it has already seen and reports a
DuplicateVerdict when a new artifact matches. Nothing is ever deleted:
callers persist the verdict as a relationship (spec §5).
"""

from dataclasses import dataclass, field

from harness.domain.triage.dedup import (
    DEFAULT_SHINGLE_SIZE,
    DuplicateMethod,
    DuplicateVerdict,
    image_similarity,
    normalize_text,
    shingles,
    text_similarity,
)


class ExactDuplicateDetector:
    """TASK-015: checksum equality."""

    def __init__(self) -> None:
        self._by_checksum: dict[str, str] = {}

    def add(self, artifact_id: str, checksum: str) -> DuplicateVerdict | None:
        canonical = self._by_checksum.get(checksum)
        if canonical is None:
            self._by_checksum[checksum] = artifact_id
            return None
        if canonical == artifact_id:
            return None
        return DuplicateVerdict(
            artifact_id=artifact_id,
            canonical_artifact_id=canonical,
            method=DuplicateMethod.EXACT,
            similarity=1.0,
        )


class NearTextDuplicateDetector:
    """TASK-016: normalized text similarity above a configured threshold.

    Candidates are narrowed by shared shingles before scoring, so adding a
    document compares against plausible matches instead of the whole
    corpus.
    """

    def __init__(
        self,
        threshold: float = 0.95,
        *,
        shingle_size: int = DEFAULT_SHINGLE_SIZE,
    ) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")
        self._threshold = threshold
        self._shingle_size = shingle_size
        self._texts: dict[str, str] = {}
        self._index: dict[str, set[str]] = {}

    def add(self, artifact_id: str, text: str) -> DuplicateVerdict | None:
        fingerprint = shingles(text, self._shingle_size)
        candidates = {
            candidate
            for shingle in fingerprint
            for candidate in self._index.get(shingle, ())
            if candidate != artifact_id
        }

        best_id: str | None = None
        best_score = 0.0
        for candidate in sorted(candidates):
            score = text_similarity(text, self._texts[candidate], size=self._shingle_size)
            if score > best_score:
                best_id, best_score = candidate, score

        self._texts[artifact_id] = text
        for shingle in fingerprint:
            self._index.setdefault(shingle, set()).add(artifact_id)

        if best_id is not None and best_score >= self._threshold:
            return DuplicateVerdict(
                artifact_id=artifact_id,
                canonical_artifact_id=best_id,
                method=DuplicateMethod.NEAR_TEXT,
                similarity=best_score,
            )
        return None


class ImageDuplicateDetector:
    """TASK-017: perceptual-hash similarity above a configured threshold."""

    def __init__(self, threshold: float = 0.98) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")
        self._threshold = threshold
        self._hashes: dict[str, str] = {}

    def add(self, artifact_id: str, perceptual_hash: str) -> DuplicateVerdict | None:
        best_id: str | None = None
        best_score = 0.0
        for candidate, candidate_hash in sorted(self._hashes.items()):
            score = image_similarity(perceptual_hash, candidate_hash)
            if score > best_score:
                best_id, best_score = candidate, score

        self._hashes[artifact_id] = perceptual_hash

        if best_id is not None and best_score >= self._threshold:
            return DuplicateVerdict(
                artifact_id=artifact_id,
                canonical_artifact_id=best_id,
                method=DuplicateMethod.NEAR_IMAGE,
                similarity=best_score,
            )
        return None


@dataclass(slots=True)
class BoilerplateReport:
    blocks: dict[str, int] = field(default_factory=dict)

    def is_boilerplate(self, block: str, *, min_documents: int) -> bool:
        return self.blocks.get(normalize_text(block), 0) >= min_documents


class BoilerplateDetector:
    """Spec §6: blocks repeated across many documents are boilerplate.

    Boilerplate is excluded from primary semantic indexing, never removed
    from the original artifact.
    """

    def __init__(self, min_documents: int = 3) -> None:
        if min_documents < 2:
            raise ValueError("min_documents must be >= 2")
        self._min_documents = min_documents
        self._counts: dict[str, int] = {}

    def observe(self, blocks: list[str]) -> None:
        """Record one document's blocks (each counted at most once)."""
        for block in {normalize_text(b) for b in blocks if b.strip()}:
            self._counts[block] = self._counts.get(block, 0) + 1

    def is_boilerplate(self, block: str) -> bool:
        return self._counts.get(normalize_text(block), 0) >= self._min_documents

    def report(self) -> BoilerplateReport:
        return BoilerplateReport(blocks=dict(self._counts))
