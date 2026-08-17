# 17 --- Repository and Engineering Standards

## 1. pyproject

Use: - uv - ruff - mypy - pytest - pytest-asyncio

## 2. Python standards

-   Python 3.12+
-   type hints everywhere in application/domain code;
-   async I/O for network-bound operations;
-   dataclasses or Pydantic models where appropriate;
-   no global mutable state.

## 3. Dependency rule

Domain packages cannot import: - FastAPI - SQLAlchemy - Celery -
provider SDKs

Use ports/interfaces.

## 4. Testing

Unit: - domain policies; - scoring; - dedup; - routing.

Integration: - PostgreSQL; - Redis; - MinIO; - connector clients; -
model adapters using mocks.

E2E: - ingest fixture; - enrich; - index; - ask; - validate citation.

## 5. Deterministic tests

No test should require a paid LLM.

LLM contract tests use recorded fixtures or fake providers.

## 6. Logging

Structured logs only.

Every processing operation logs: - correlation ID; - artifact ID; -
stage; - status; - duration.

Never log secrets or raw sensitive content.

## 7. Versioning

API uses `/v1`.

Prompt versions are semantic.

Knowledge records retain the versions of processing components used.
