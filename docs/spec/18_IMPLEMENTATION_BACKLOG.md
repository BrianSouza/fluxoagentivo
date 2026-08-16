# 18 --- Implementation Backlog

## Epic 1 --- Bootstrap

### TASK-001 Repository

Create Python 3.12 project using uv, FastAPI, Pydantic Settings,
SQLAlchemy, Alembic, pytest, ruff and mypy.

Acceptance: - `uv run pytest` passes; - `uv run ruff check .` passes; -
`uv run mypy` passes; - FastAPI health endpoint works.

### TASK-002 Docker

Create Compose environment with PostgreSQL+pgvector, Redis and MinIO.

Acceptance: - one command starts dependencies; - migrations execute.

## Epic 2 --- Domain and persistence

### TASK-003 Domain models

Implement Artifact, ArtifactPart, Evidence, Enrichment, KnowledgeUnit
and Relationship.

### TASK-004 Database

Implement SQLAlchemy models and Alembic migrations matching
`02_DATABASE_SCHEMA.md`.

### TASK-005 Object storage

Implement S3/MinIO adapter.

## Epic 3 --- Processing engine

### TASK-006 ProcessingRun

Implement idempotent processing run tracking.

### TASK-007 Job queues

Implement Celery queues and retry policies.

## Epic 4 --- Parsers

### TASK-008 PDF

Implement PyMuPDF parser.

### TASK-009 DOCX

Implement python-docx parser.

### TASK-010 PPTX

Implement python-pptx parser with slide boundaries.

### TASK-011 HTML

Implement HTML parser preserving headings, links and image references.

### TASK-012 Images

Implement image metadata, checksum and perceptual hash.

## Epic 5 --- Connectors

### TASK-013 Filesystem connector

Implement recursive fixture connector.

### TASK-014 Confluence connector

Implement discovery, pagination, fetch, attachments and incremental
version detection.

Acceptance: - test fixtures simulate 1,000 pages; - unchanged pages are
skipped.

## Epic 6 --- Triage and dedup

### TASK-015 Exact dedup

Checksum-based.

### TASK-016 Near dedup

Text normalization + similarity.

### TASK-017 Image dedup

Perceptual hash.

### TASK-018 Relevance

Implement configurable relevance policy.

## Epic 7 --- Model Gateway

### TASK-019 Gateway contracts

Implement provider-neutral interfaces.

### TASK-020 Fake provider

Create deterministic fake model for tests.

### TASK-021 Ollama

Implement local adapter.

### TASK-022 Cloud adapters

Implement at least one cloud adapter and one OpenAI-compatible adapter.

### TASK-023 Routing

Implement model profile and capability routing.

### TASK-024 Cost telemetry

Persist model call metrics.

## Epic 8 --- Multimodal

### TASK-025 OCR adapter

Create pluggable OCR interface.

### TASK-026 Image classification

Implement cheap classification route.

### TASK-027 Diagram interpretation

Implement schema-constrained multimodal enrichment.

### TASK-028 Page synthesis

Fuse text + visual evidence.

Acceptance: - mixed fixture page produces a KnowledgeUnit referencing
both text and image evidence.

## Epic 9 --- Search

### TASK-029 Full-text index

Implement PostgreSQL FTS.

### TASK-030 Embeddings

Implement Model Gateway embeddings and pgvector.

### TASK-031 Hybrid retrieval

Implement configurable hybrid score.

### TASK-032 Reranking

Implement provider-neutral reranking.

### TASK-033 Duplicate suppression

Suppress duplicate candidates.

## Epic 10 --- Answering

### TASK-034 Evidence assembly

Create bounded context.

### TASK-035 Answer generation

Structured claim output.

### TASK-036 Citation resolver

Resolve Evidence IDs.

### TASK-037 Citation validator

Reject unsupported citations.

## Epic 11 --- Assessment

### TASK-038 Assessment templates

YAML-based templates.

### TASK-039 Assessment execution

Question -\> retrieval -\> reasoning -\> finding.

### TASK-040 Assessment reporting

Evidence-backed findings.

## Epic 12 --- Observability/security

### TASK-041 OpenTelemetry

Trace pipeline and model calls.

### TASK-042 Metrics

Expose Prometheus-compatible metrics.

### TASK-043 Data policies

Implement provider allow/deny policy.

### TASK-044 Audit

Implement audit records.

## Epic 13 --- Evaluation

### TASK-045 Golden dataset

Create synthetic fixtures.

### TASK-046 Retrieval evaluation

Implement Recall@K, MRR, nDCG.

### TASK-047 Answer evaluation

Implement citation validity and unsupported claim measurement.

## Delivery gates

### Gate A

Bootstrap + domain + storage works.

### Gate B

A file can be ingested and queried.

### Gate C

Confluence mixed page works.

### Gate D

Cloud/local model can be swapped by configuration.

### Gate E

Answers contain validated citations.

### Gate F

Assessment produces evidence-backed findings.

Do not proceed to the next gate with failing mandatory acceptance tests.
