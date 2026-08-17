"""Runtime configuration validated with Pydantic Settings.

Two layers, per docs/spec/15_CONFIGURATION.md: human-editable policy lives
in YAML (`config/policy.yaml`), while secrets and runtime overrides come
from environment variables (or a local `.env`). Environment variables win
over the YAML file. Defaults target the local Docker Compose environment
and must never contain production credentials.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from harness.domain.retrieval.models import RetrievalWeights
from harness.domain.triage.relevance import RelevanceWeights

POLICY_FILE = Path("config/policy.yaml")


class RelevanceWeightSettings(BaseModel):
    """Relevance weights (06_DEDUP_TRIAGE.md §3) — policy, not code."""

    structural: float = 0.20
    semantic: float = 0.20
    relationship: float = 0.15
    visual: float = 0.15
    freshness: float = 0.10
    source_authority: float = 0.10
    historical_demand: float = 0.10

    @model_validator(mode="after")
    def _validate_domain_invariants(self) -> "RelevanceWeightSettings":
        # Delegate to the domain type so config and domain cannot drift.
        self.to_domain()
        return self

    def to_domain(self) -> RelevanceWeights:
        return RelevanceWeights(
            structural=self.structural,
            semantic=self.semantic,
            relationship=self.relationship,
            visual=self.visual,
            freshness=self.freshness,
            source_authority=self.source_authority,
            historical_demand=self.historical_demand,
        )


class RetrievalWeightSettings(BaseModel):
    """Hybrid retrieval weights (07_RETRIEVAL.md §3) — policy, not code."""

    semantic: float = 0.35
    lexical: float = 0.25
    metadata: float = 0.15
    authority: float = 0.10
    freshness: float = 0.10
    relationship: float = 0.05

    @model_validator(mode="after")
    def _validate_domain_invariants(self) -> "RetrievalWeightSettings":
        self.to_domain()
        return self

    def to_domain(self) -> RetrievalWeights:
        return RetrievalWeights(
            semantic=self.semantic,
            lexical=self.lexical,
            metadata=self.metadata,
            authority=self.authority,
            freshness=self.freshness,
            relationship=self.relationship,
        )


class RetrievalSettings(BaseModel):
    """Retrieval pool/dedup knobs (07_RETRIEVAL.md §2, 06_DEDUP_TRIAGE.md §7)."""

    candidate_pool_size: int = Field(default=100, ge=1)
    max_duplicates: int = Field(default=1, ge=0)
    freshness_half_life_days: float = Field(default=180.0, gt=0.0)
    relationship_expansion_limit: int = Field(default=20, ge=0)


class ProcessingSettings(BaseModel):
    """Thresholds from 15_CONFIGURATION.md."""

    duplicate_text_threshold: float = Field(default=0.95, gt=0.0, le=1.0)
    duplicate_image_threshold: float = Field(default=0.98, gt=0.0, le=1.0)
    semantic_duplicate_threshold: float = Field(default=0.92, gt=0.0, le=1.0)
    image_deep_enrichment_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    triage_index_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    boilerplate_min_documents: int = Field(default=3, ge=2)


class ProviderSettings(BaseModel):
    """A configured provider (08_MODEL_GATEWAY.md §8).

    `api_key_ref` is a `secret://` reference, never a raw credential.
    """

    kind: Literal["fake", "ollama", "openai_compatible", "anthropic"] = "fake"
    base_url: str | None = None
    api_key_ref: str | None = None


class PricingSettings(BaseModel):
    input_per_million: float = Field(default=0.0, ge=0.0)
    output_per_million: float = Field(default=0.0, ge=0.0)
    cached_input_per_million: float | None = Field(default=None, ge=0.0)


class ProfileSettings(BaseModel):
    """Model profile (08_MODEL_GATEWAY.md §4)."""

    provider: str
    model: str
    temperature: float | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)
    pricing: PricingSettings = PricingSettings()
    escalates_to: str | None = None
    local_only: bool = False


class BudgetSettings(BaseModel):
    per_job_usd: float | None = Field(default=None, ge=0.0)
    daily_usd: float | None = Field(default=None, ge=0.0)


def _default_providers() -> dict[str, ProviderSettings]:
    # The default profile works offline with no paid API, which
    # 16_DOCKER_LOCAL.md §2 requires.
    return {"fake": ProviderSettings(kind="fake")}


def _default_profiles() -> dict[str, ProfileSettings]:
    return {
        name: ProfileSettings(provider="fake", model=f"fake-{name}")
        for name in (
            "cheap_classifier",
            "image_deep",
            "synthesis",
            "answer",
            "embedding_default",
            "private_local",
        )
    }


def _default_routes() -> dict[str, str]:
    return {
        "classification": "cheap_classifier",
        "image_description": "image_deep",
        "diagram_interpretation": "image_deep",
        "page_synthesis": "synthesis",
        "answer_generation": "answer",
        "embedding": "embedding_default",
        "rerank": "cheap_classifier",
    }


class ModelSettings(BaseModel):
    """Providers, profiles and routes — all policy, never code."""

    providers: dict[str, ProviderSettings] = Field(default_factory=_default_providers)
    profiles: dict[str, ProfileSettings] = Field(default_factory=_default_profiles)
    routes: dict[str, str] = Field(default_factory=_default_routes)
    default_profile: str | None = "cheap_classifier"
    budgets: BudgetSettings = BudgetSettings()

    @model_validator(mode="after")
    def _validate_references(self) -> "ModelSettings":
        for name, profile in self.profiles.items():
            if profile.provider not in self.providers:
                raise ValueError(
                    f"profile {name!r} names unknown provider {profile.provider!r}"
                )
        for task, profile_name in self.routes.items():
            if profile_name not in self.profiles:
                raise ValueError(f"route {task!r} names unknown profile {profile_name!r}")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
        yaml_file=POLICY_FILE,
    )

    app_environment: Literal["development", "test", "production"] = "development"

    postgres_dsn: str = "postgresql+psycopg://harness:harness@localhost:5432/harness"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "harness"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"

    # Dimension of the pgvector embedding column (02_DATABASE_SCHEMA.md:
    # "vector(<configured_dimension>)"). Must match the embedding model
    # chosen later via the Model Gateway.
    embedding_dimension: int = 1536

    # Upper bound for automatic retries of transient failures
    # (01_ARCHITECTURE.md, section 8).
    celery_task_max_retries: int = 5

    processing: ProcessingSettings = ProcessingSettings()
    relevance_weights: RelevanceWeightSettings = RelevanceWeightSettings()
    models: ModelSettings = ModelSettings()
    retrieval: RetrievalSettings = RetrievalSettings()
    retrieval_weights: RetrievalWeightSettings = RetrievalWeightSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Precedence: init > environment > .env > policy YAML > defaults.
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
