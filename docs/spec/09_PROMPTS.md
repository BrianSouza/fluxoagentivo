# 09 --- Prompt Contracts

## 1. Classification prompt

Input: - title - metadata - extracted text sample - image metadata

Output schema:

``` json
{
  "relevance": 0.0,
  "categories": [],
  "requires_visual_enrichment": false,
  "reason": ""
}
```

## 2. Diagram interpretation prompt

Input: - image - OCR text - source page title - nearby relevant text

Output: - image_type - summary - components - relationships -
visible_text - business_context - technical_context - uncertainties

## 3. Page synthesis prompt

Input: - selected text evidence - selected image evidence - hierarchy -
metadata

Output: - title - summary - key_facts - concepts - entities -
relationships - evidence_ids

## 4. Answer prompt

Input: - user question - evidence objects - answer profile

Output:

``` json
{
  "answer": "...",
  "claims": [
    {
      "text": "...",
      "evidence_ids": ["..."]
    }
  ],
  "uncertainties": []
}
```

The renderer converts claims into human-readable citations.

## 5. Assessment prompt

Input: - assessment question - evidence - scoring rubric

Output:

``` json
{
  "finding": "...",
  "score": 0,
  "confidence": 0,
  "evidence_ids": [],
  "gaps": [],
  "recommendation": "..."
}
```

## 6. Prompt testing

Every prompt MUST have: - happy-path fixture; - ambiguous fixture; -
insufficient-evidence fixture; - malformed-output fixture.
