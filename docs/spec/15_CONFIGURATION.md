# 15 --- Configuration

Use YAML for human-editable policies and environment variables for
secrets/runtime overrides.

Example:

``` yaml
app:
  environment: development

storage:
  postgres:
    dsn: ${POSTGRES_DSN}
  object_store:
    endpoint: ${S3_ENDPOINT}
    bucket: harness

queue:
  redis_url: ${REDIS_URL}

models:
  providers:
    openai:
      api_key: ${OPENAI_API_KEY}
    anthropic:
      api_key: ${ANTHROPIC_API_KEY}
    ollama:
      base_url: ${OLLAMA_BASE_URL}

  profiles:
    cheap_classifier:
      provider: openai
      model: ${CLASSIFIER_MODEL}

    image_deep:
      provider: openai
      model: ${VISION_MODEL}

    synthesis:
      provider: anthropic
      model: ${SYNTHESIS_MODEL}

    private_local:
      provider: ollama
      model: ${OLLAMA_MODEL}

routing:
  classification: cheap_classifier
  image_description: image_deep
  diagram_interpretation: image_deep
  page_synthesis: synthesis

processing:
  duplicate_text_threshold: 0.95
  duplicate_image_threshold: 0.98
  semantic_duplicate_threshold: 0.92
  image_deep_enrichment_threshold: 0.70

budgets:
  daily_usd: 100
```

No API key may be committed.

Configuration MUST be validated with Pydantic Settings.
