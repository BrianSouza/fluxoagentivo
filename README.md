# Agentic Knowledge & Assessment Harness

Multimodal enterprise knowledge and assessment platform. The full
implementation-ready specification lives in [`docs/spec/`](docs/spec/) —
start with `00_MASTER_SPEC.md` and `18_IMPLEMENTATION_BACKLOG.md`.

Current status: **Epic 3 — Processing engine** (idempotent processing runs
and Celery stage queues; Epics 1–3 of the backlog).

## Stack

Python 3.12+, uv, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic,
PostgreSQL 16 + pgvector, Redis, MinIO, pytest, ruff, mypy.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Docker.

```bash
# install dependencies
uv sync

# start PostgreSQL (pgvector), Redis, MinIO and the API
docker compose up --build
```

The API container runs `alembic upgrade head` before starting, so the
database is migrated automatically. Once up:

- API: http://localhost:8000 — health check at `GET /api/v1/health`
- PostgreSQL: `localhost:5432` (`harness`/`harness`)
- Redis: `localhost:6379`
- MinIO: `localhost:9000` (console at `localhost:9001`, `minioadmin`/`minioadmin`)

To run the API on the host instead (with dependencies from Compose):

```bash
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn --factory harness.api.app:create_app --reload
```

## Development

```bash
uv run pytest          # tests (no database or LLM required)
uv run ruff check .    # lint
uv run mypy            # type check
```

The default profile works without any paid LLM API
(`docs/spec/16_DOCKER_LOCAL.md`). AI enrichment, connectors and the Model
Gateway are later backlog tasks and are not implemented yet.

## Repository layout

```
src/harness/
  api/              # FastAPI app, routes
  application/      # commands, queries, services, jobs (future)
  domain/           # entities, policies, ports — no framework imports
  infrastructure/   # db, object store, connectors, model adapters
  config/           # Pydantic Settings
  observability/    # logging/tracing setup (future)
  cli/              # CLI entrypoints (future)
migrations/         # Alembic migrations
tests/              # unit (integration/e2e in later tasks)
docker/             # container images
docs/spec/          # the V2 specification (source of truth)
```

Layering rule (`docs/spec/01_ARCHITECTURE.md`): the domain layer must not
import FastAPI, SQLAlchemy, Celery or provider SDKs.
