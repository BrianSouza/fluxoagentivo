# 06 --- Triage, Relevance and Deduplication

## 1. Triage goals

Triage decides: - whether the artifact contains useful knowledge; -
which parts are useful; - whether expensive AI enrichment is justified.

It MUST NOT delete source artifacts.

## 2. Deterministic signals

Calculate: - text length - unique token ratio - heading count - image
count - attachment count - link count - repeated block ratio - source
hierarchy depth - modification age - duplicate hashes

## 3. Relevance score

Initial score:

``` text
relevance =
  0.20 * structural_score
+ 0.20 * semantic_signal
+ 0.15 * relationship_score
+ 0.15 * visual_value
+ 0.10 * freshness
+ 0.10 * source_authority
+ 0.10 * historical_demand
```

Weights MUST be configuration, not constants in business code.

## 4. Duplicate levels

### Exact

Checksum identical.

### Near duplicate

Normalized text or perceptual image similarity exceeds threshold.

### Semantic duplicate

Embedding similarity exceeds threshold and a classifier confirms same
subject.

## 5. Canonicalization

Canonical selection factors: - source authority - latest valid version -
completeness - richer evidence - lower duplication - page hierarchy

Never delete duplicates. Mark relationships.

## 6. Boilerplate

Repeated navigation, legal disclaimers, templates and instructional
boilerplate SHOULD be excluded from primary semantic indexing when
confidence is high.

Original content remains available.

## 7. Query-time duplicate suppression

If retrieval returns five near-identical evidence items: - return
canonical evidence first; - include at most configured number of
duplicates; - preserve alternate source links.

## 8. Adaptive enrichment

Track retrieval demand.

An artifact with repeated failed retrieval or high user demand MAY be
escalated for deeper enrichment.

Do not use demand as the only relevance signal.
