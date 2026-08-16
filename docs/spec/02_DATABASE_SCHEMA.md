# 02 --- Database Schema

Use PostgreSQL with pgvector.

## 1. Core tables

### sources

``` sql
id uuid primary key
name varchar(200) not null
type varchar(50) not null
config_ref varchar(500)
enabled boolean not null default true
created_at timestamptz not null
updated_at timestamptz not null
```

### artifacts

``` sql
id uuid primary key
source_id uuid not null references sources(id)
external_id varchar(1000) not null
parent_artifact_id uuid references artifacts(id)
artifact_type varchar(50) not null
title text
source_uri text not null
version varchar(500)
checksum_sha256 char(64) not null
mime_type varchar(200)
size_bytes bigint
created_at timestamptz
modified_at timestamptz
discovered_at timestamptz not null
metadata jsonb not null default '{}'
unique(source_id, external_id, version, checksum_sha256)
```

### artifact_parts

``` sql
id uuid primary key
artifact_id uuid not null references artifacts(id)
parent_part_id uuid references artifact_parts(id)
part_type varchar(50) not null
ordinal integer not null
location jsonb not null default '{}'
text_content text
binary_object_key text
checksum_sha256 char(64)
metadata jsonb not null default '{}'
```

### evidence

``` sql
id uuid primary key
artifact_id uuid not null references artifacts(id)
artifact_part_id uuid not null references artifact_parts(id)
modality varchar(30) not null
content text not null
content_hash char(64) not null
confidence numeric(5,4)
extraction_method varchar(100) not null
created_at timestamptz not null
metadata jsonb not null default '{}'
```

### enrichments

``` sql
id uuid primary key
evidence_id uuid not null references evidence(id)
enrichment_type varchar(100) not null
content jsonb not null
provider varchar(100)
model varchar(200)
prompt_version varchar(100)
input_tokens integer
output_tokens integer
estimated_cost numeric(18,8)
confidence numeric(5,4)
created_at timestamptz not null
```

### knowledge_units

``` sql
id uuid primary key
title text not null
summary text not null
version integer not null
status varchar(30) not null
valid_from timestamptz
valid_to timestamptz
metadata jsonb not null default '{}'
created_at timestamptz not null
updated_at timestamptz not null
```

### knowledge_unit_evidence

``` sql
knowledge_unit_id uuid references knowledge_units(id)
evidence_id uuid references evidence(id)
primary key(knowledge_unit_id, evidence_id)
```

### relationships

``` sql
id uuid primary key
subject_type varchar(50) not null
subject_id uuid not null
predicate varchar(100) not null
object_type varchar(50) not null
object_id uuid not null
confidence numeric(5,4)
evidence_id uuid references evidence(id)
metadata jsonb not null default '{}'
created_at timestamptz not null
```

## 2. Search tables

### chunks

``` sql
id uuid primary key
evidence_id uuid not null references evidence(id)
chunk_index integer not null
content text not null
token_estimate integer not null
embedding vector(<configured_dimension>)
metadata jsonb not null default '{}'
```

Create HNSW vector index when operationally appropriate.

Also create PostgreSQL full-text indexes.

## 3. Processing

### processing_runs

``` sql
id uuid primary key
artifact_id uuid references artifacts(id)
stage varchar(50) not null
status varchar(30) not null
idempotency_key varchar(500) not null unique
started_at timestamptz
finished_at timestamptz
error_code varchar(100)
error_message text
metrics jsonb not null default '{}'
```

### model_calls

``` sql
id uuid primary key
task varchar(100) not null
provider varchar(100) not null
model varchar(200) not null
artifact_id uuid references artifacts(id)
evidence_id uuid references evidence(id)
prompt_version varchar(100)
input_tokens integer
output_tokens integer
latency_ms integer
estimated_cost numeric(18,8)
status varchar(30) not null
created_at timestamptz not null
metadata jsonb not null default '{}'
```

## 4. Deduplication

### artifact_duplicates

``` sql
artifact_id uuid primary key references artifacts(id)
canonical_artifact_id uuid not null references artifacts(id)
method varchar(50) not null
similarity numeric(6,5)
```

## 5. Assessments

``` sql
assessment_templates
assessment_runs
assessment_questions
assessment_findings
```

Findings MUST reference evidence IDs.

## 6. Access control readiness

All major entities MUST have a `scope_id` or equivalent tenancy/project
boundary if multi-tenancy is enabled.

## 7. Migration policy

All schema changes use Alembic. No manual production schema
modifications.
