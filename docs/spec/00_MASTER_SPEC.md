# Agentic Knowledge & Assessment Harness --- V2 Master Specification

**Status:** Implementation-ready blueprint\
**Primary implementation language:** Python 3.12+\
**Architecture objective:** Build a vendor-neutral, multimodal
enterprise knowledge and assessment harness.

## 1. Product definition

The Harness is a platform that:

1.  connects to enterprise knowledge sources;
2.  captures original artifacts and versions;
3.  extracts deterministic text, structure and metadata;
4.  identifies relevant images and visual evidence;
5.  uses configurable LLM capabilities to enrich difficult evidence;
6.  deduplicates repeated information;
7.  constructs traceable Knowledge Units;
8.  indexes evidence for hybrid retrieval;
9.  answers questions using retrieved evidence;
10. validates citations before returning answers;
11. executes configurable assessments against the knowledge base;
12. measures quality, latency and AI cost.

The Harness MUST NOT replace source systems such as Confluence or Git.
They remain systems of record.

## 2. Primary use case

A user asks:

> "How does the mobile application's checkout flow work today, and which
> backend services are involved?"

The Harness must be able to retrieve: - a Confluence page describing the
flow; - a diagram showing the application and WebViews; - a screenshot
of the relevant UI; - documentation of the WebView backend; -
source-code evidence if configured.

It then produces an answer whose factual claims cite the exact evidence.

## 3. Architecture principles

-   Python-first
-   API-first
-   modular monolith initially
-   asynchronous ingestion
-   source/derived separation
-   provenance everywhere
-   multimodal by design
-   hybrid retrieval
-   configurable model routing
-   local inference support
-   incremental processing
-   idempotency
-   observable AI calls
-   testable without an LLM
-   security boundaries explicit
-   no provider-specific logic in domain code

## 4. Technology decisions

  Area                   Decision
  ---------------------- --------------------------------------------------------
  Runtime                Python 3.12+
  API                    FastAPI
  Validation             Pydantic v2
  ORM                    SQLAlchemy 2
  Migrations             Alembic
  Database               PostgreSQL 16+
  Vector                 pgvector
  Cache / queue broker   Redis
  Job execution          Celery
  Object storage         S3-compatible; MinIO locally
  HTTP                   httpx
  Workflow/agents        LangGraph only where graph orchestration is useful
  Model abstraction      Internal Model Gateway; optional LiteLLM adapter
  Local LLM              Ollama adapter
  PDF                    PyMuPDF
  DOCX                   python-docx
  PPTX                   python-pptx
  HTML/XML               BeautifulSoup/lxml as required
  OCR                    pluggable adapter
  Image processing       Pillow
  Embeddings             Model Gateway
  Reranking              Model Gateway
  Observability          OpenTelemetry
  Logging                structlog
  Tests                  pytest
  Quality                ruff + mypy
  Packaging              uv + pyproject.toml
  Containers             Docker Compose initially
  UI                     React/TypeScript later; not required for ingestion MVP

## 5. Architectural boundary

``` text
                +----------------------+
                |      FastAPI API     |
                +----------+-----------+
                           |
                    Application Layer
                           |
        +------------------+------------------+
        |                  |                  |
     Ingestion          Retrieval          Assessment
        |                  |                  |
        +------------------+------------------+
                           |
                       Domain Layer
                           |
        +------------------+------------------+
        |                  |                  |
    PostgreSQL          Object Store      Model Gateway
    + pgvector             S3/MinIO       / cloud / local
```

The domain layer MUST NOT import FastAPI, Celery, provider SDKs or
database-specific implementations.

## 6. Deployment modes

### Local development

Docker Compose: - API - worker - PostgreSQL + pgvector - Redis - MinIO -
Ollama optional

### Enterprise deployment

Components may be split into independent containers/services without
changing domain contracts.

## 7. Initial connector scope

MVP: - Confluence - local filesystem - generic uploaded files

Next: - Git - GitHub/GitLab/Azure DevOps - SharePoint - additional wikis

## 8. Initial format scope

Required: - HTML - TXT - Markdown - PDF - DOCX - PPTX - PNG/JPEG/WebP -
source code as text

Legacy DOC and other formats MUST be supported through a conversion
adapter or recorded as unsupported; they MUST NOT silently disappear.

## 9. Quality requirement

The Harness MUST optimize for evidence fidelity, not merely answer
fluency.

A fluent answer without valid evidence is a failure.

## 10. V2 implementation rule

Implementation MUST follow `18_IMPLEMENTATION_BACKLOG.md`. Do not
implement all modules simultaneously.
