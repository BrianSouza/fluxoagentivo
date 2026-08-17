"""Batch chunk embedding via the Model Gateway (TASK-030).

Storage into pgvector is the infrastructure adapter's job
(infrastructure/search/postgres.py); this service only turns chunk text
into vectors through whatever provider is configured.
"""

from typing import Any

from harness.domain.models.contracts import EmbeddingRequest, ModelTask
from harness.domain.retrieval.models import ChunkText, EmbeddedChunk


class EmbeddingIndexer:
    def __init__(self, gateway: Any, *, task: ModelTask = ModelTask.EMBEDDING) -> None:
        self._gateway = gateway
        self._task = task

    async def embed_chunks(self, chunks: list[ChunkText]) -> list[EmbeddedChunk]:
        if not chunks:
            return []
        response = await self._gateway.embed(
            EmbeddingRequest(inputs=[chunk.content for chunk in chunks], task=self._task)
        )
        if len(response.vectors) != len(chunks):
            raise ValueError(
                f"embedding provider returned {len(response.vectors)} vectors "
                f"for {len(chunks)} chunks"
            )
        return [
            EmbeddedChunk(chunk_id=chunk.chunk_id, embedding=vector)
            for chunk, vector in zip(chunks, response.vectors, strict=True)
        ]
