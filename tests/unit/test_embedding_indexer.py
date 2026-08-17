"""Batch embedding via the Model Gateway (TASK-030)."""

from uuid import uuid4

import pytest

from harness.application.services.embedding_indexer import EmbeddingIndexer
from harness.domain.models.contracts import EmbeddingRequest, EmbeddingResponse
from harness.domain.retrieval.models import ChunkText
from harness.infrastructure.models.fake import FakeProvider


class RecordingGateway:
    def __init__(self) -> None:
        self.requests: list[EmbeddingRequest] = []

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        self.requests.append(request)
        provider = FakeProvider(embedding_dimension=8)
        return await provider.embed(request, "fake-embedding")


async def test_embeds_each_chunk_and_preserves_order() -> None:
    gateway = RecordingGateway()
    indexer = EmbeddingIndexer(gateway)
    chunks = [
        ChunkText(chunk_id=uuid4(), content="checkout flow"),
        ChunkText(chunk_id=uuid4(), content="payment gateway"),
    ]
    embedded = await indexer.embed_chunks(chunks)
    assert [e.chunk_id for e in embedded] == [c.chunk_id for c in chunks]
    assert len(embedded[0].embedding) == 8
    assert gateway.requests[0].inputs == ["checkout flow", "payment gateway"]


async def test_empty_input_returns_empty_without_calling_gateway() -> None:
    gateway = RecordingGateway()
    indexer = EmbeddingIndexer(gateway)
    assert await indexer.embed_chunks([]) == []
    assert gateway.requests == []


async def test_mismatched_vector_count_raises() -> None:
    class BrokenGateway:
        async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
            return EmbeddingResponse(vectors=[[0.1]], provider="x", model="m")

    indexer = EmbeddingIndexer(BrokenGateway())
    with pytest.raises(ValueError, match="vectors"):
        await indexer.embed_chunks(
            [ChunkText(chunk_id=uuid4(), content="a"), ChunkText(chunk_id=uuid4(), content="b")]
        )


async def test_same_text_yields_same_vector_deterministically() -> None:
    gateway = RecordingGateway()
    indexer = EmbeddingIndexer(gateway)
    embedded = await indexer.embed_chunks(
        [
            ChunkText(chunk_id=uuid4(), content="repeat"),
            ChunkText(chunk_id=uuid4(), content="repeat"),
        ]
    )
    assert embedded[0].embedding == embedded[1].embedding
