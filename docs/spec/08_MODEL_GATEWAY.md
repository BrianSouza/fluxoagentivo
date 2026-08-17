# 08 --- Model Gateway

## 1. Objective

Runtime application code must request capabilities, not concrete
providers.

## 2. Capability interface

``` python
class ModelGateway(Protocol):
    async def generate_text(self, request: TextGenerationRequest) -> ModelResponse: ...
    async def generate_multimodal(self, request: MultimodalRequest) -> ModelResponse: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse: ...
    async def rerank(self, request: RerankRequest) -> RerankResponse: ...
```

## 3. Required adapters

-   OpenAI-compatible adapter
-   Anthropic adapter
-   Ollama adapter
-   optional LiteLLM adapter for broad provider coverage

The internal interface remains authoritative even when LiteLLM is used.

## 4. Model profile

``` yaml
profiles:
  cheap_classifier:
    provider: configurable
    model: configurable
    temperature: 0
    max_output_tokens: 512

  embedding_default:
    provider: configurable
    model: configurable

  image_deep:
    provider: configurable
    model: configurable
    max_output_tokens: 2500

  synthesis:
    provider: configurable
    model: configurable
    max_output_tokens: 4000

  answer:
    provider: configurable
    model: configurable
    max_output_tokens: 2500

  private_local:
    provider: ollama
    model: configurable
```

## 5. Routing policy

``` yaml
routes:
  classification: cheap_classifier
  image_description: image_deep
  diagram_interpretation: image_deep
  page_synthesis: synthesis
  answer_generation: answer
```

## 6. Escalation

A task MAY escalate if: - confidence below threshold; - structured
output invalid; - context too complex; - visual category is complex; -
assessment risk is high.

## 7. Provider selection policy

Selection considers: - data sensitivity; - modality; - context length; -
cost; - latency; - availability; - quality target.

## 8. Local inference

Ollama is configured as a provider.

Example:

``` yaml
providers:
  ollama:
    base_url: http://ollama:11434
```

No domain code references Ollama directly.

## 9. Cost control

Record: - input tokens - output tokens - cache usage - latency -
estimated cost - provider/model - task - prompt version

Budget policies MAY stop or downgrade processing.

## 10. Development assistants

Codex, Claude Code and GitHub Copilot/VS Code are development tools.
They should read the repository specification and can implement code.

They are not required for runtime inference.

## 11. Prompt registry

Prompt files live under `prompts/`. Each prompt: - has semantic
version; - has JSON schema if structured; - has test fixtures; - is
referenced by model calls.
