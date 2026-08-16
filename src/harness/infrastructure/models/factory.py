"""Build the Model Gateway from configuration.

This module is the single place that maps a configured provider `kind` to
a concrete adapter class. Application code receives a ModelGateway and
never learns which vendor answered.
"""

from harness.config.settings import ProfileSettings, Settings, get_settings
from harness.domain.models.budget import BudgetLimits, BudgetTracker
from harness.domain.models.contracts import ModelTask
from harness.domain.models.ports import ModelCallSink, ModelProvider
from harness.domain.models.routing import ModelProfile, RoutingPolicy
from harness.domain.models.telemetry import ModelPricing
from harness.domain.sources.ports import SecretResolver
from harness.infrastructure.models.anthropic import AnthropicProvider
from harness.infrastructure.models.fake import FakeProvider
from harness.infrastructure.models.gateway import RoutingModelGateway
from harness.infrastructure.models.ollama import OllamaProvider
from harness.infrastructure.models.openai_compat import OpenAICompatibleProvider


class ProviderConfigurationError(ValueError):
    """Raised when a provider is configured with missing or invalid options."""


def build_providers(
    settings: Settings | None = None,
    *,
    secret_resolver: SecretResolver | None = None,
) -> dict[str, ModelProvider]:
    settings = settings or get_settings()
    providers: dict[str, ModelProvider] = {}

    for name, config in settings.models.providers.items():
        if config.kind == "fake":
            providers[name] = FakeProvider(
                embedding_dimension=settings.embedding_dimension
            )
        elif config.kind == "ollama":
            providers[name] = OllamaProvider.from_base_url(
                config.base_url or "http://localhost:11434"
            )
        elif config.kind in ("openai_compatible", "anthropic"):
            api_key = _resolve_api_key(name, config.api_key_ref, secret_resolver)
            if config.kind == "openai_compatible":
                providers[name] = OpenAICompatibleProvider.from_api_key(
                    api_key,
                    base_url=config.base_url or "https://api.openai.com/v1",
                    name=name,
                )
            else:
                providers[name] = AnthropicProvider.from_api_key(
                    api_key, base_url=config.base_url or "https://api.anthropic.com/v1"
                )
        else:  # pragma: no cover - Literal keeps this unreachable
            raise ProviderConfigurationError(f"unknown provider kind {config.kind!r}")

    return providers


def build_routing_policy(settings: Settings | None = None) -> RoutingPolicy:
    settings = settings or get_settings()
    profiles = {
        name: _to_profile(name, config) for name, config in settings.models.profiles.items()
    }
    routes = {
        ModelTask(task): profile_name for task, profile_name in settings.models.routes.items()
    }
    return RoutingPolicy(
        profiles=profiles,
        routes=routes,
        default_profile=settings.models.default_profile,
    )


def build_budget_tracker(settings: Settings | None = None) -> BudgetTracker:
    settings = settings or get_settings()
    return BudgetTracker(
        limits=BudgetLimits(
            per_job_usd=settings.models.budgets.per_job_usd,
            daily_usd=settings.models.budgets.daily_usd,
        )
    )


def build_gateway(
    settings: Settings | None = None,
    *,
    sink: ModelCallSink | None = None,
    secret_resolver: SecretResolver | None = None,
) -> RoutingModelGateway:
    settings = settings or get_settings()
    return RoutingModelGateway(
        providers=build_providers(settings, secret_resolver=secret_resolver),
        policy=build_routing_policy(settings),
        sink=sink,
        budget=build_budget_tracker(settings),
    )


def _to_profile(name: str, config: ProfileSettings) -> ModelProfile:
    return ModelProfile(
        name=name,
        provider=config.provider,
        model=config.model,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        pricing=ModelPricing(
            input_per_million=config.pricing.input_per_million,
            output_per_million=config.pricing.output_per_million,
            cached_input_per_million=config.pricing.cached_input_per_million,
        ),
        escalates_to=config.escalates_to,
        local_only=config.local_only,
    )


def _resolve_api_key(
    provider_name: str, api_key_ref: str | None, resolver: SecretResolver | None
) -> str:
    if api_key_ref is None:
        raise ProviderConfigurationError(
            f"provider {provider_name!r} requires api_key_ref pointing at a secret"
        )
    if resolver is None:
        raise ProviderConfigurationError(
            f"provider {provider_name!r} needs a SecretResolver to resolve {api_key_ref!r}"
        )
    credentials = resolver.resolve(api_key_ref)
    for key in ("api_key", "token", "key"):
        if key in credentials:
            return credentials[key]
    raise ProviderConfigurationError(
        f"secret {api_key_ref!r} has no api_key/token/key entry for provider {provider_name!r}"
    )
