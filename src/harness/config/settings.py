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


class ProcessingSettings(BaseModel):
    """Thresholds from 15_CONFIGURATION.md."""

    duplicate_text_threshold: float = Field(default=0.95, gt=0.0, le=1.0)
    duplicate_image_threshold: float = Field(default=0.98, gt=0.0, le=1.0)
    semantic_duplicate_threshold: float = Field(default=0.92, gt=0.0, le=1.0)
    image_deep_enrichment_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    triage_index_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    boilerplate_min_documents: int = Field(default=3, ge=2)


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
