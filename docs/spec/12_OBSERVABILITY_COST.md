# 12 --- Observability and Cost

## 1. Metrics

System: - ingestion throughput - queue depth - processing duration -
failure rate - API latency

Knowledge: - artifacts processed - duplicate rate - enrichment rate -
image enrichment rate - index size - stale artifact count

LLM: - calls by task - tokens - cost - latency - cache hit rate -
escalation rate - invalid structured outputs - citation validation
failures

Retrieval: - candidate count - rerank latency - retrieval score -
no-evidence rate

## 2. Tracing

OpenTelemetry spans: - HTTP request - ingestion job - parser - LLM
call - embedding call - retrieval - reranking - answer generation -
citation validation

Every span should carry correlation IDs.

## 3. Cost budgets

Support: - per-job budget; - per-source budget; - daily budget; -
monthly budget.

When budget is exceeded: - stop optional enrichment; - continue
deterministic processing; - mark enrichment pending.

## 4. Cost attribution

Every model call references: - source/artifact when applicable; -
task; - model profile; - prompt version.

## 5. Dashboards

MVP may expose metrics through Prometheus-compatible endpoints; a full
UI can come later.
