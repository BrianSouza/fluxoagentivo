# 05 --- Parsers and Multimodal Enrichment

## 1. Parser interface

``` python
class DocumentParser(Protocol):
    def supports(self, mime_type: str, filename: str) -> bool: ...
    async def parse(self, artifact: FetchedArtifact) -> ParsedDocument: ...
```

## 2. Deterministic parsing

Use: - PyMuPDF for PDF - python-docx for DOCX - python-pptx for PPTX -
BeautifulSoup/lxml for HTML - plain text readers for TXT/MD - Pillow for
image metadata - tree-sitter or language-specific parsers later for
source code

Do not use an LLM for information that can be extracted
deterministically.

## 3. Image evidence

For each image: 1. fingerprint; 2. detect dimensions; 3. determine
whether decorative; 4. OCR if useful; 5. classify; 6. enrich if
valuable.

## 4. Image categories

Minimum: - architecture_diagram - sequence_diagram - flowchart -
infrastructure_landscape - ui_screenshot - gameplay_screenshot - chart -
table - photograph - decorative - unknown

## 5. Multimodal structured output

The model MUST return schema-constrained JSON:

``` json
{
  "image_type": "architecture_diagram",
  "summary": "...",
  "components": [
    {
      "name": "Mobile App",
      "type": "application",
      "description": "..."
    }
  ],
  "relationships": [
    {
      "from": "Mobile App",
      "to": "Checkout API",
      "relationship": "calls",
      "confidence": 0.91
    }
  ],
  "visible_text": [],
  "business_context": "...",
  "technical_context": "...",
  "uncertainties": []
}
```

The enrichment MUST never claim invisible details as facts.

## 6. Cost-aware image pipeline

``` text
Image
 -> exact/perceptual dedup
 -> decorative classifier
 -> OCR
 -> cheap multimodal classifier
 -> relevance score
 -> deep interpretation only if threshold met
```

Default thresholds MUST be configuration.

## 7. Mixed page fusion

The page-level synthesizer receives: - high-value extracted text; -
high-value image interpretations; - page hierarchy; - source metadata; -
relationship evidence.

It produces: - page summary; - concepts; - entities; - architecture
facts; - process facts; - evidence references.

It MUST NOT replace child evidence.

## 8. Token optimization

Never send an entire Confluence page blindly.

Use: - HTML boilerplate removal; - section extraction; - duplicate block
removal; - OCR only once; - cached image interpretations; - prompt
templates; - token budgets; - batch embeddings; - changed-part
processing; - model escalation.

## 9. Image cache key

`sha256(image_bytes + processor_version + prompt_version + model_profile)`

If unchanged, reuse enrichment.
