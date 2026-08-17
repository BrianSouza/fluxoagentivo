# 07 --- Hybrid Retrieval and Answering

## 1. Retrieval stages

1.  Query normalization
2.  Query classification
3.  Metadata filtering
4.  PostgreSQL full-text retrieval
5.  pgvector retrieval
6.  relationship expansion
7.  duplicate suppression
8.  reranking
9.  evidence assembly

## 2. Initial retrieval

Fetch a broad candidate pool, e.g. 50-100 items, then rerank.

Do not use the final `top_k` directly as the initial pool.

## 3. Hybrid scoring

Initial formula:

``` text
score =
  0.35 * semantic_score
+ 0.25 * lexical_score
+ 0.15 * metadata_score
+ 0.10 * authority_score
+ 0.10 * freshness_score
+ 0.05 * relationship_score
```

All weights configurable and evaluatable.

## 4. Reranker

The reranker receives query + candidate evidence and returns relevance
scores.

Use Model Gateway.

## 5. Evidence assembly

Context must include: - source title; - source URI; - artifact ID; -
evidence ID; - location; - content; - confidence; - relationships; -
temporal validity.

## 6. Answer generation

Prompt contract:

-   Answer only using provided evidence.
-   Cite every externally verifiable claim.
-   Do not invent URLs or source IDs.
-   Distinguish evidence from inference.
-   State uncertainty.
-   If evidence conflicts, describe the conflict.
-   If evidence is insufficient, say so.

## 7. Citation validation

A validator MUST: - parse cited evidence IDs; - verify IDs exist; -
verify evidence is in context; - verify claim/evidence compatibility
where possible; - resolve display metadata.

An answer failing validation is regenerated once with a stricter prompt.
If it still fails, return a safe evidence-limited response.

## 8. Temporal queries

Support `valid_at` filters.

Example: "What was the architecture in 2024?"

The retriever MUST prefer evidence valid at the requested time.

## 9. Source authority

Authority is configurable by source type and specific source.

Example: - architecture standards: high - official Confluence: high -
personal notes: medium - duplicate training page: low
