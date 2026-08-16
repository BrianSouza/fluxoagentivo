# 10 --- Citations and Provenance

## 1. Principle

No generated knowledge is valid without a path to source evidence.

## 2. Provenance graph

``` text
Source
  -> Artifact
    -> ArtifactPart
      -> Evidence
        -> Enrichment
          -> KnowledgeUnit
            -> RetrievalResult
              -> Claim
                -> Citation
```

## 3. Citation object

``` json
{
  "evidence_id": "uuid",
  "source_name": "Corporate Confluence",
  "source_uri": "https://...",
  "artifact_title": "Checkout Flow",
  "location": {
    "page": 4,
    "section": "WebView"
  },
  "snippet": "..."
}
```

## 4. Citation granularity

Prefer: - PDF page; - PPT slide; - Confluence page + section; - image
index; - code file + line range when available.

## 5. Citation safety

The model MUST receive opaque evidence IDs. The application resolves IDs
to URLs and locations.

This prevents the LLM from inventing URLs.

## 6. Provenance retention

Derived records MUST retain: - input evidence IDs; - provider/model; -
prompt version; - timestamp; - confidence.

## 7. Source changes

If an artifact changes: - old evidence remains historical; - new
evidence receives a new version; - affected KnowledgeUnits are
invalidated/rebuilt; - citations to old versions remain resolvable.
