# 03 --- API Contracts

Base path: `/api/v1`

## GET /health

Response:

``` json
{"status":"ok","version":"0.1.0"}
```

## POST /sources

Creates a source configuration.

Request:

``` json
{
  "name": "Corporate Confluence",
  "type": "confluence",
  "config_ref": "secret://confluence/main"
}
```

## POST /sources/{source_id}/sync

Starts asynchronous synchronization.

Response:

``` json
{
  "job_id": "uuid",
  "status": "queued"
}
```

## GET /jobs/{job_id}

Returns job status and metrics.

## GET /artifacts/{artifact_id}

Returns artifact metadata and processing state.

## GET /artifacts/{artifact_id}/evidence

Returns evidence with provenance.

## POST /search

Request:

``` json
{
  "query": "How does the checkout WebView work?",
  "filters": {
    "source_ids": [],
    "artifact_types": [],
    "valid_at": null
  },
  "top_k": 20
}
```

Response:

``` json
{
  "results": [
    {
      "evidence_id": "uuid",
      "artifact_id": "uuid",
      "title": "Checkout Flow",
      "content": "...",
      "score": 0.92,
      "location": {"page": 3, "image_index": 1}
    }
  ]
}
```

## POST /questions

Request:

``` json
{
  "question": "How does checkout work today?",
  "filters": {},
  "answer_profile": "default"
}
```

Response:

``` json
{
  "answer": "...",
  "citations": [
    {
      "evidence_id": "uuid",
      "source_uri": "https://...",
      "location": {"page": 3}
    }
  ],
  "confidence": 0.88,
  "evidence_coverage": 0.93
}
```

## POST /assessments

Request:

``` json
{
  "template_id": "mobile_architecture",
  "scope": {
    "source_ids": ["uuid"]
  }
}
```

Response:

``` json
{
  "run_id": "uuid",
  "status": "queued"
}
```

## POST /admin/reprocess

Request:

``` json
{
  "artifact_ids": ["uuid"],
  "stages": ["enrichment", "indexing"],
  "force": false
}
```

## API rules

-   JSON only for API payloads.
-   Pydantic validation.
-   RFC 7807-style error responses.
-   Correlation ID on every request.
-   Authentication/authorization middleware MUST be pluggable.
