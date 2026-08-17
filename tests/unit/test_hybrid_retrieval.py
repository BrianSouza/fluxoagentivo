"""Hybrid retrieval orchestration (TASK-031, TASK-032, TASK-033)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from harness.application.services.retrieval import HybridRetrievalService
from harness.domain.models.contracts import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelTask,
    RerankRequest,
    RerankResponse,
    RerankResult,
)
from harness.domain.models.routing import ModelProfile, RoutingPolicy
from harness.domain.retrieval.models import RetrievalWeights, SearchFilters, SearchQuery
from harness.domain.retrieval.ports import LexicalHit, RelatedHit, VectorHit
from harness.infrastructure.models.fake import FakeProvider
from harness.infrastructure.models.gateway import RoutingModelGateway

NOW = datetime(2026, 8, 17, tzinfo=UTC)
NEUTRAL_WEIGHTS = RetrievalWeights(
    semantic=1.0, lexical=0.0, metadata=0.0, authority=0.0, freshness=0.0, relationship=0.0
)


class FakeLexicalIndex:
    def __init__(self, hits: list[LexicalHit] | None = None) -> None:
        self._hits = hits or []
        self.calls: list[tuple[str, SearchFilters, int]] = []

    def search(self, query: str, filters: SearchFilters, limit: int) -> list[LexicalHit]:
        self.calls.append((query, filters, limit))
        return self._hits[:limit]


class FakeVectorIndex:
    def __init__(self, hits: list[VectorHit] | None = None) -> None:
        self._hits = hits or []
        self.calls: list[tuple[list[float], SearchFilters, int]] = []

    def search(
        self, embedding: list[float], filters: SearchFilters, limit: int
    ) -> list[VectorHit]:
        self.calls.append((embedding, filters, limit))
        return self._hits[:limit]


class FakeRelationshipExpander:
    def __init__(self, hits: list[RelatedHit]) -> None:
        self._hits = hits
        self.calls: list[tuple[list[UUID], int]] = []

    def expand(self, seed_evidence_ids: list[UUID], limit: int) -> list[RelatedHit]:
        self.calls.append((seed_evidence_ids, limit))
        return self._hits[:limit]


class ScriptedGateway:
    """Deterministic embed + rerank-by-index, for precise orchestration tests."""

    def __init__(self, rerank_order: list[int] | None = None) -> None:
        self.embed_calls: list[EmbeddingRequest] = []
        self.rerank_calls: list[RerankRequest] = []
        self._rerank_order = rerank_order

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.embed_calls.append(request)
        return EmbeddingResponse(vectors=[[0.1, 0.2, 0.3]], provider="scripted", model="m")

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        self.rerank_calls.append(request)
        order = self._rerank_order or list(range(len(request.documents)))
        results = [
            RerankResult(index=index, score=1.0 - position * 0.01)
            for position, index in enumerate(order)
        ]
        return RerankResponse(results=results, provider="scripted", model="m")


def lexical_hit(rank: float = 0.5, **overrides: object) -> LexicalHit:
    defaults: dict[str, object] = {
        "chunk_id": uuid4(),
        "evidence_id": uuid4(),
        "artifact_id": uuid4(),
        "content": "the checkout webview",
        "rank": rank,
    }
    defaults.update(overrides)
    return LexicalHit(**defaults)  # type: ignore[arg-type]


def vector_hit(similarity: float = 0.8, **overrides: object) -> VectorHit:
    defaults: dict[str, object] = {
        "chunk_id": uuid4(),
        "evidence_id": uuid4(),
        "artifact_id": uuid4(),
        "content": "the checkout webview",
        "similarity": similarity,
    }
    defaults.update(overrides)
    return VectorHit(**defaults)  # type: ignore[arg-type]


class TestQueryNormalizationAndPool:
    async def test_query_is_normalized_before_reaching_the_indexes(self) -> None:
        lexical, vector = FakeLexicalIndex(), FakeVectorIndex()
        service = HybridRetrievalService(lexical, vector, ScriptedGateway())
        await service.search(SearchQuery(text="  checkout   api  "))
        assert lexical.calls[0][0] == "checkout api"

    async def test_candidate_pool_size_is_passed_to_both_indexes(self) -> None:
        lexical, vector = FakeLexicalIndex(), FakeVectorIndex()
        service = HybridRetrievalService(lexical, vector, ScriptedGateway())
        await service.search(SearchQuery(text="q", top_k=5, candidate_pool_size=50))
        assert lexical.calls[0][2] == 50
        assert vector.calls[0][2] == 50

    async def test_no_candidates_returns_empty_without_calling_rerank(self) -> None:
        gateway = ScriptedGateway()
        service = HybridRetrievalService(FakeLexicalIndex(), FakeVectorIndex(), gateway)
        results = await service.search(SearchQuery(text="q"))
        assert results == []
        assert gateway.rerank_calls == []  # RerankRequest forbids empty documents


class TestScoringAndRanking:
    async def test_merges_and_ranks_by_final_score_after_rerank(self) -> None:
        weak = lexical_hit(rank=0.1)
        strong = lexical_hit(rank=0.9)
        gateway = ScriptedGateway(rerank_order=[1, 0])  # rerank flips the order
        service = HybridRetrievalService(
            FakeLexicalIndex([weak, strong]), FakeVectorIndex(), gateway, weights=NEUTRAL_WEIGHTS
        )
        results = await service.search(SearchQuery(text="q"))
        assert [c.chunk_id for c in results] == [strong.chunk_id, weak.chunk_id]

    async def test_top_k_truncates_the_final_list(self) -> None:
        hits = [lexical_hit(rank=r) for r in (0.9, 0.8, 0.7, 0.6, 0.5)]
        service = HybridRetrievalService(
            FakeLexicalIndex(hits), FakeVectorIndex(), ScriptedGateway()
        )
        results = await service.search(SearchQuery(text="q", top_k=2, candidate_pool_size=5))
        assert len(results) == 2

    async def test_valid_at_deprioritizes_out_of_window_evidence(self) -> None:
        fresh = vector_hit(
            similarity=0.7, valid_from=NOW - timedelta(days=1), valid_to=NOW + timedelta(days=1)
        )
        stale = vector_hit(similarity=0.7, valid_to=NOW - timedelta(days=365))
        gateway = ScriptedGateway()  # identity rerank order preserves hybrid ranking
        service = HybridRetrievalService(
            FakeLexicalIndex(), FakeVectorIndex([fresh, stale]), gateway, weights=NEUTRAL_WEIGHTS
        )
        results = await service.search(
            SearchQuery(text="q", filters=SearchFilters(valid_at=NOW))
        )
        assert results[0].chunk_id == fresh.chunk_id


class TestRelationshipExpansion:
    async def test_expanded_evidence_is_added_to_the_pool(self) -> None:
        seed = lexical_hit()
        related = RelatedHit(
            chunk_id=uuid4(), evidence_id=uuid4(), artifact_id=uuid4(), content="related chunk"
        )
        expander = FakeRelationshipExpander([related])
        service = HybridRetrievalService(
            FakeLexicalIndex([seed]), FakeVectorIndex(), ScriptedGateway(),
            relationship_expander=expander,
        )
        results = await service.search(SearchQuery(text="q"))
        assert related.chunk_id in {c.chunk_id for c in results}
        assert expander.calls[0][0] == [seed.evidence_id]

    async def test_no_expander_configured_means_no_expansion(self) -> None:
        seed = lexical_hit()
        service = HybridRetrievalService(
            FakeLexicalIndex([seed]), FakeVectorIndex(), ScriptedGateway()
        )
        results = await service.search(SearchQuery(text="q"))
        assert len(results) == 1

    async def test_already_present_evidence_is_not_duplicated_by_expansion(self) -> None:
        seed = lexical_hit()
        same_evidence = RelatedHit(
            chunk_id=uuid4(), evidence_id=seed.evidence_id, artifact_id=uuid4(), content="dup"
        )
        expander = FakeRelationshipExpander([same_evidence])
        service = HybridRetrievalService(
            FakeLexicalIndex([seed]), FakeVectorIndex(), ScriptedGateway(),
            relationship_expander=expander,
        )
        results = await service.search(SearchQuery(text="q"))
        assert len(results) == 1


class TestDuplicateSuppression:
    async def test_duplicates_are_suppressed_before_the_final_result(self) -> None:
        shared_artifact_group = uuid4()
        a = lexical_hit(rank=0.9, artifact_id=uuid4())
        b = lexical_hit(rank=0.8, artifact_id=uuid4())

        class GroupLookup:
            def canonical_for(self, artifact_id: UUID) -> UUID:
                return shared_artifact_group

        service = HybridRetrievalService(
            FakeLexicalIndex([a, b]), FakeVectorIndex(), ScriptedGateway(),
            canonical_lookup=GroupLookup(), max_duplicates=0,
        )
        results = await service.search(SearchQuery(text="q"))
        assert len(results) == 1
        assert results[0].chunk_id == a.chunk_id  # higher-ranked survives


class TestEndToEndWithRealGateway:
    async def test_works_with_the_deterministic_fake_provider(self) -> None:
        # Proves retrieval, like the rest of the harness, runs with no paid API.
        provider = FakeProvider(embedding_dimension=16)
        policy = RoutingPolicy(
            profiles={"p": ModelProfile("p", "fake", "m")},
            routes={ModelTask.EMBEDDING: "p", ModelTask.RERANK: "p"},
        )
        gateway = RoutingModelGateway(providers={"fake": provider}, policy=policy)
        hits = [lexical_hit(rank=0.9), lexical_hit(rank=0.1)]
        service = HybridRetrievalService(FakeLexicalIndex(hits), FakeVectorIndex(), gateway)
        results = await service.search(SearchQuery(text="how does checkout work?"))
        assert len(results) == 2
        assert all(0.0 <= c.final_score <= 1.0 for c in results)
