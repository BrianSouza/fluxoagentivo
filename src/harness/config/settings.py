"""Runtime configuration validated with Pydantic Settings.

Secrets and runtime overrides come from environment variables (or a local
`.env` file). Defaults target the local Docker Compose environment and must
never contain production credentials.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_environment: Literal["development", "test", "production"] = "development"

    postgres_dsn: str = "postgresql+psycopg://harness:harness@localhost:5432/harness"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "harness"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"


@lru_cache
def get_settings() -> Settings:
    return Settings()
