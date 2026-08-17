# 16 --- Local Development Environment

Docker Compose services:

``` text
api
worker
postgres
redis
minio
ollama (optional)
```

## 1. Local flow

``` text
docker compose up
```

API: `http://localhost:8000`

PostgreSQL: `localhost:5432`

Redis: `localhost:6379`

MinIO: `localhost:9000`

Ollama: `localhost:11434`

## 2. Local development profile

The default profile MUST work without paid LLM APIs.

Use deterministic parsers and optionally Ollama.

The application MUST clearly indicate when AI enrichment is disabled.

## 3. Test fixtures

Include: - sample Confluence HTML; - sample PDF; - sample PPTX; - sample
DOCX; - architecture diagram; - UI screenshot; - duplicate files.

Fixtures MUST be synthetic or licensed for repository use.
