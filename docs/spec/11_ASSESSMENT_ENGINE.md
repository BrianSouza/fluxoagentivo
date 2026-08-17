# 11 --- Assessment Engine

## 1. Purpose

Assess architecture, documentation, systems, dependencies or compliance
using the knowledge base.

## 2. Template

``` yaml
id: mobile_architecture
name: Mobile Architecture Assessment
questions:
  - id: backend_services
    question: Which backend services are used?
    evidence_required: true
    scoring:
      type: completeness
  - id: webviews
    question: Which WebViews exist and what do they call?
    evidence_required: true
```

## 3. Execution

For each question: 1. retrieve evidence; 2. assemble context; 3. run
assessment model; 4. validate evidence IDs; 5. calculate score; 6.
record gaps; 7. generate finding.

## 4. Assessment result

Must include: - question; - finding; - evidence; - confidence; -
score; - gaps; - recommendation; - generated_at; - knowledge base
version.

## 5. No unsupported conclusions

If evidence is missing, finding MUST say that the knowledge base lacks
sufficient evidence.

## 6. Repeatability

Same: - knowledge base version; - assessment template version; - prompt
version; - model profile

should produce an auditable comparable run.
