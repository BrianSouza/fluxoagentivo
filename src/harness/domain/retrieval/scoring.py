"""Merge, score and suppress duplicates among retrieved candidates.

Implements retrieval stages 3-7 from `07_RETRIEVAL.md` §1 (metadata
filtering is enforced by the search index adapters before hits reach this
module): merge lexical + vector hits, apply the hybrid formula from §3,
prefer evidence valid at the requested time (§8), and suppress duplicates
per `06_DEDUP_TRIAGE.md` §7 (canonical first, bounded alternates, nothing
deleted).
"""

import math
from datetime import datetime
from uuid import UUID

from harness.domain.common.decay import exponential_decay
from harness.domain.retrieval.models import Candidate, RetrievalWeights, ScoreComponents
from harness.domain.retrieval.ports import (
    CanonicalArtifactLookup,
    LexicalHit,
    SourceAuthorityLookup,
    VectorHit,
)

DEFAULT_FRESHNESS_HALF_LIFE_DAYS = 180.0
# Applied to candidates that fall outside the requested valid_at window,
# so temporal misses lose priority without being hidden outright.
TEMPORAL_MISS_PENALTY = 0.5
RELATIONSHIP_HIT_SCORE = 1.0


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"vectors must have the same dimension, got {len(a)} and {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def merge_hits(
    lexical_hits: list[LexicalHit], vector_hits: list[VectorHit]
) -> dict[UUID, Candidate]:
    """Combine lexical and vector hits into one Candidate per chunk.

    A chunk absent from one side has genuinely zero relevance on that
    dimension (the search ran and found nothing), unlike triage's "not yet
    computed" neutral default.
    """
    candidates: dict[UUID, Candidate] = {}
    for lexical_hit in lexical_hits:
        candidate = candidates.setdefault(
            lexical_hit.chunk_id,
            Candidate(
                chunk_id=lexical_hit.chunk_id,
                evidence_id=lexical_hit.evidence_id,
                artifact_id=lexical_hit.artifact_id,
                content=lexical_hit.content,
                source_id=lexical_hit.source_id,
                valid_from=lexical_hit.valid_from,
                valid_to=lexical_hit.valid_to,
                metadata=dict(lexical_hit.metadata or {}),
            ),
        )
        candidate.lexical_rank = lexical_hit.rank
    for vector_hit in vector_hits:
        candidate = candidates.setdefault(
            vector_hit.chunk_id,
            Candidate(
                chunk_id=vector_hit.chunk_id,
                evidence_id=vector_hit.evidence_id,
                artifact_id=vector_hit.artifact_id,
                content=vector_hit.content,
                source_id=vector_hit.source_id,
                valid_from=vector_hit.valid_from,
                valid_to=vector_hit.valid_to,
                metadata=dict(vector_hit.metadata or {}),
            ),
        )
        candidate.semantic_similarity = vector_hit.similarity
    return candidates


def score_candidates(
    candidates: list[Candidate],
    weights: RetrievalWeights,
    *,
    valid_at: datetime | None = None,
    authority: SourceAuthorityLookup | None = None,
    freshness_half_life_days: float = DEFAULT_FRESHNESS_HALF_LIFE_DAYS,
    now: datetime | None = None,
) -> None:
    """Scores candidates in place, normalizing lexical rank across the pool."""
    max_rank = max((c.lexical_rank or 0.0 for c in candidates), default=0.0) or 1.0
    reference_time = now or valid_at

    for candidate in candidates:
        lexical = (candidate.lexical_rank or 0.0) / max_rank
        semantic = max(0.0, min(1.0, candidate.semantic_similarity or 0.0))
        metadata_score = 1.0 if candidate.metadata else 0.5
        authority_score = (
            authority.authority_for(candidate.source_id) if authority is not None else 0.5
        )
        age_days = _age_in_days(candidate.valid_from, reference_time)
        freshness_score = exponential_decay(age_days, half_life_days=freshness_half_life_days)
        relationship_score = RELATIONSHIP_HIT_SCORE if candidate.via_relationship else 0.0

        candidate.scores = ScoreComponents(
            semantic=semantic,
            lexical=lexical,
            metadata=metadata_score,
            authority=authority_score,
            freshness=freshness_score,
            relationship=relationship_score,
        )
        hybrid = (
            weights.semantic * semantic
            + weights.lexical * lexical
            + weights.metadata * metadata_score
            + weights.authority * authority_score
            + weights.freshness * freshness_score
            + weights.relationship * relationship_score
        )
        if valid_at is not None and not candidate.is_valid_at(valid_at):
            hybrid *= TEMPORAL_MISS_PENALTY
        candidate.hybrid_score = max(0.0, min(1.0, hybrid))


def _age_in_days(valid_from: datetime | None, reference: datetime | None) -> float | None:
    if valid_from is None or reference is None:
        return None
    return max((reference - valid_from).total_seconds() / 86400.0, 0.0)


def suppress_duplicates(
    candidates: list[Candidate],
    canonical: CanonicalArtifactLookup,
    *,
    max_duplicates: int = 1,
) -> list[Candidate]:
    """TASK-033: collapse duplicate candidates without deleting anything.

    Ranked by final_score, the canonical (or best-scoring, if none of the
    group is formally canonical) representative of each artifact group is
    always kept; at most `max_duplicates` further alternates follow,
    tagged with `duplicate_of` so callers can still surface alternate
    source links (06_DEDUP_TRIAGE.md §7).
    """
    if max_duplicates < 0:
        raise ValueError(f"max_duplicates must be >= 0, got {max_duplicates!r}")

    ordered = sorted(candidates, key=lambda c: c.final_score, reverse=True)
    kept: list[Candidate] = []
    seen_per_group: dict[UUID, int] = {}
    group_representative: dict[UUID, UUID] = {}

    for candidate in ordered:
        group = canonical.canonical_for(candidate.artifact_id)
        count = seen_per_group.get(group, 0)
        if count == 0:
            group_representative[group] = candidate.artifact_id
        elif count > max_duplicates:
            continue
        else:
            candidate.duplicate_of = group_representative[group]
        seen_per_group[group] = count + 1
        kept.append(candidate)

    return kept
