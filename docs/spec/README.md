# Agentic Knowledge & Assessment Harness --- V2

This repository is the implementation-ready specification for the
Harness discussed in the architecture sessions.

## What it builds

A multimodal enterprise knowledge platform for: - Confluence; -
repositories; - PDFs; - DOC/DOCX; - PPT/PPTX; - images; - diagrams; -
screenshots; - source code.

It provides: - automated ingestion; - triage; - deduplication; -
multimodal enrichment; - hybrid retrieval; - evidence-backed answers; -
citations; - assessments; - cost/quality telemetry; - cloud and local
LLM support.

## Recommended stack

Python 3.12+, FastAPI, Pydantic, SQLAlchemy, PostgreSQL + pgvector,
Redis, Celery, S3/MinIO, OpenTelemetry, Docker, Ollama and a
provider-neutral Model Gateway.

## Start here

1.  `00_MASTER_SPEC.md`
2.  `18_IMPLEMENTATION_BACKLOG.md`
3.  `19_AGENT_EXECUTION_PROMPT.md`

## Important architectural choice

The Harness does not depend on Codex, Claude Code or Copilot at runtime.

Those are coding agents that can implement the repository from this
specification.

Runtime inference is selected through the Model Gateway and can use
cloud APIs or local models such as Ollama.

## First milestone

Build the end-to-end path using synthetic fixtures before connecting the
full corporate Confluence:

`source -> ingest -> parse -> triage -> enrich -> index -> retrieve -> answer -> citation`

Then scale the connector.
