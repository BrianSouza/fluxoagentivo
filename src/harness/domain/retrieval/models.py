"""Retrieval value objects (docs/spec/07_RETRIEVAL.md).

Evidence assembly (spec §5, stage 9) — building the full answer-time
Context object — is TASK-034 in Epic 10. This module stops at ranked
Candidates, which is as far as TASK-029 through TASK-033 go.
"""

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any
from uuid import UUID

from harness.domain.common.values import validate_confidence

WEIGHT_SUM_TOLERANCE = 1e-6


def normalize_query(text: str) -> str:
    """Stage 1: trim and collapse whitespace.

    Deliberately lighter than triage/dedup normalization — punctuation and
    case carry meaning for both full-text search and embeddings, so only
    whitespace is touched here.
    """
    return " ".join(text.strip().split())


@dataclass(slots=True)
class SearchFilters:
    source_ids: list[UUID] = field(default_factory=list)
    artifact_types: list[str] = field(default_factory=list)
    # Temporal queries (spec §8), e.g. "what was the architecture in 2024?"
    valid_at: datetime | None = None

    @property
    def is_empty(self) -> bool:
        return not self.source_ids and not self.artifact_types


@dataclass(slots=True)
class SearchQuery:
    text: str
    filters: SearchFilters = field(default_factory=SearchFilters)
    top_k: int = 10
    # Broad pool fetched before reranking (spec §2): never rerank top_k directly.
    candidate_pool_size: int = 100

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("query text must not be empty")
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k!r}")
        if self.candidate_pool_size < self.top_k:
            raise ValueError(
                f"candidate_pool_size ({self.candidate_pool_size}) must be >= "
                f"top_k ({self.top_k})"
            )

    @property
    def normalized_text(self) -> str:
        return normalize_query(self.text)


@dataclass(frozen=True, slots=True)
class RetrievalWeights:
    """Weights from `07_RETRIEVAL.md` §3; defaults match the spec."""

    semantic: float = 0.35
    lexical: float = 0.25
    metadata: float = 0.15
    authority: float = 0.10
    freshness: float = 0.10
    relationship: float = 0.05

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if value < 0:
                raise ValueError(f"weight {f.name} must not be negative, got {value!r}")
        if abs(self.total - 1.0) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"retrieval weights must sum to 1.0, got {self.total!r}")

    @property
    def total(self) -> float:
        return float(sum(float(getattr(self, f.name)) for f in fields(self)))


@dataclass(frozen=True, slots=True)
class ScoreComponents:
    semantic: float = 0.0
    lexical: float = 0.0
    metadata: float = 0.5
    authority: float = 0.5
    freshness: float = 0.5
    relationship: float = 0.0

    def __post_init__(self) -> None:
        for f in fields(self):
            validate_confidence(getattr(self, f.name), field=f.name)


@dataclass(slots=True)
class Candidate:
    """A retrieved chunk carrying enough context to score and rank it."""

    chunk_id: UUID
    evidence_id: UUID
    artifact_id: UUID
    content: str
    source_id: UUID | None = None
    lexical_rank: float | None = None
    semantic_similarity: float | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    via_relationship: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    scores: ScoreComponents | None = None
    hybrid_score: float = 0.0
    rerank_score: float | None = None
    duplicate_of: UUID | None = None

    @property
    def final_score(self) -> float:
        return self.rerank_score if self.rerank_score is not None else self.hybrid_score

    def is_valid_at(self, moment: datetime) -> bool:
        if self.valid_from is not None and moment < self.valid_from:
            return False
        return not (self.valid_to is not None and moment > self.valid_to)


@dataclass(frozen=True, slots=True)
class ChunkText:
    """Input to embedding (TASK-030): a chunk not yet vectorized."""

    chunk_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    chunk_id: UUID
    embedding: list[float]
