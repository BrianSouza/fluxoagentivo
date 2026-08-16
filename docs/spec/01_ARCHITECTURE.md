# 01 --- Detailed Architecture

## 1. Layer model

``` text
Interface
  API / CLI

Application
  Commands / Queries / Jobs / Use Cases

Domain
  Entities / Value Objects / Policies / Ports

Infrastructure
  PostgreSQL / Redis / S3 / Connectors / LLM providers
```

Dependency direction:

`Interface -> Application -> Domain <- Infrastructure`

Infrastructure implements domain/application ports.

## 2. Repository layout

``` text
src/
  harness/
    api/
      routes/
      dependencies.py
      app.py
    application/
      commands/
      queries/
      services/
      jobs/
    domain/
      artifacts/
      evidence/
      knowledge/
      retrieval/
      assessments/
      models/
      common/
    infrastructure/
      db/
      object_store/
      queue/
      connectors/
      parsers/
      ocr/
      models/
      embeddings/
      search/
    config/
    observability/
    cli/

tests/
  unit/
  integration/
  contract/
  e2e/

prompts/
  classification/
  image/
  diagram/
  synthesis/
  answer/
  assessment/

migrations/
scripts/
docker/
docs/
```

## 3. Modular monolith rule

Keep modules isolated by Python package and ports. Avoid microservices
until scaling evidence requires it.

A worker may execute the same application services as the API.

## 4. Command/query separation

Commands mutate state: - sync source - ingest artifact - enrich
evidence - rebuild index - run assessment

Queries read: - artifact - evidence - search - answer - assessment
result

## 5. Idempotency

Every externally triggered operation MUST accept an idempotency key or
derive one from source/version/checksum.

Example:

`ingest_key = sha256(source_system + source_uri + source_version + checksum)`

## 6. Transaction boundaries

Metadata state changes are transactional.

Large binary operations MUST use object storage and database references
rather than storing large binaries directly in PostgreSQL.

## 7. Concurrency

Celery queues: - `discovery` - `normalization` - `triage` -
`enrichment` - `embedding` - `indexing` - `answer` - `assessment`

Each queue has configurable concurrency and rate limits.

## 8. Failure handling

Retry transient: - HTTP 429 - HTTP 5xx - network timeout - temporary
provider failure

Do not retry permanent: - invalid credentials - unsupported format -
corrupted artifact - schema validation failure after configured retries

All failures create an auditable ProcessingRun record.
