"""Hybrid retrieval orchestration (TASK-031, TASK-032, TASK-033).

Runs the stages from `07_RETRIEVAL.md` §1 that are in this epic's scope:

    1 query normalization -> 3 metadata filtering (delegated to the index
    adapters) -> 4 full-text retrieval -> 5 vector retrieval ->
    6 relationship expansion -> hybrid scoring (§3) -> 7 duplicate
    suppression -> 8 reranking -> truncate to top_k

Stage 2 (query classification) and stage 9 (evidence assembly) belong to
later epics; this service produces ranked Candidates, not a Context.
"""

from typing import Any
from uuid import UUID

from harness.domain.models.contracts import EmbeddingRequest, ModelTask, RerankRequest
from harness.domain.retrieval.defaults import (
    ConfigurableSourceAuthority,
    IdentityCanonicalLookup,
)
from harness.domain.retrieval.models import Candidate, RetrievalWeights, SearchQuery
from harness.domain.retrieval.ports import (
    CanonicalArtifactLookup,
    LexicalSearchIndex,
    RelationshipExpander,
    SourceAuthorityLookup,
    VectorSearchIndex,
)
from harness.domain.retrieval.scoring import (
    DEFAULT_FRESHNESS_HALF_LIFE_DAYS,
    merge_hits,
    score_candidates,
    suppress_duplicates,
)


class HybridRetrievalService:
    def __init__(
        self,
        lexical_index: LexicalSearchIndex,
        vector_index: VectorSearchIndex,
        gateway: Any,
        *,
        weights: RetrievalWeights | None = None,
        relationship_expander: RelationshipExpander | None = None,
        canonical_lookup: CanonicalArtifactLookup | None = None,
        authority: SourceAuthorityLookup | None = None,
        max_duplicates: int = 1,
        relationship_expansion_limit: int = 20,
        freshness_half_life_days: float = DEFAULT_FRESHNESS_HALF_LIFE_DAYS,
    ) -> None:
        self._lexical_index = lexical_index
        self._vector_index = vector_index
        self._gateway = gateway
        self._weights = weights or RetrievalWeights()
        self._relationship_expander = relationship_expander
        self._canonical_lookup = canonical_lookup or IdentityCanonicalLookup()
        self._authority = authority or ConfigurableSourceAuthority()
        self._max_duplicates = max_duplicates
        self._relationship_expansion_limit = relationship_expansion_limit
        self._freshness_half_life_days = freshness_half_life_days

    async def search(self, query: SearchQuery) -> list[Candidate]:
        normalized = query.normalized_text

        lexical_hits = self._lexical_index.search(
            normalized, query.filters, query.candidate_pool_size
        )
        embedding_response = await self._gateway.embed(
            EmbeddingRequest(inputs=[normalized], task=ModelTask.EMBEDDING)
        )
        vector_hits = self._vector_index.search(
            embedding_response.vectors[0], query.filters, query.candidate_pool_size
        )

        merged = merge_hits(lexical_hits, vector_hits)
        candidates = list(merged.values())
        if self._relationship_expander is not None and candidates:
            candidates = self._expand_relationships(candidates, merged)

        score_candidates(
            candidates,
            self._weights,
            valid_at=query.filters.valid_at,
            authority=self._authority,
            freshness_half_life_days=self._freshness_half_life_days,
        )

        suppressed = suppress_duplicates(
            candidates, self._canonical_lookup, max_duplicates=self._max_duplicates
        )
        reranked = await self._rerank(normalized, suppressed)
        reranked.sort(key=lambda c: c.final_score, reverse=True)
        return reranked[: query.top_k]

    def _expand_relationships(
        self, candidates: list[Candidate], merged: dict[UUID, Candidate]
    ) -> list[Candidate]:
        assert self._relationship_expander is not None
        seed_evidence_ids = [c.evidence_id for c in candidates]
        related = self._relationship_expander.expand(
            seed_evidence_ids, self._relationship_expansion_limit
        )
        known_evidence_ids = {c.evidence_id for c in candidates}
        for hit in related:
            if hit.evidence_id in known_evidence_ids:
                continue
            candidates.append(
                Candidate(
                    chunk_id=hit.chunk_id,
                    evidence_id=hit.evidence_id,
                    artifact_id=hit.artifact_id,
                    content=hit.content,
                    source_id=hit.source_id,
                    valid_from=hit.valid_from,
                    valid_to=hit.valid_to,
                    via_relationship=True,
                )
            )
            known_evidence_ids.add(hit.evidence_id)
        return candidates

    async def _rerank(self, query_text: str, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return []
        response = await self._gateway.rerank(
            RerankRequest(
                query=query_text,
                documents=[c.content for c in candidates],
                task=ModelTask.RERANK,
            )
        )
        for result in response.results:
            candidates[result.index].rerank_score = result.score
        return candidates
