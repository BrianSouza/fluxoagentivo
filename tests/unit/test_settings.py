from pathlib import Path

import pytest

from harness.config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run from an empty directory so a developer's local .env file is never picked up,
    # and clear any settings-related variables inherited from the host environment.
    monkeypatch.chdir(tmp_path)
    for name in (
        "APP_ENVIRONMENT",
        "POSTGRES_DSN",
        "REDIS_URL",
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_target_local_compose() -> None:
    settings = Settings()
    assert settings.app_environment == "development"
    assert settings.postgres_dsn.startswith("postgresql+psycopg://")
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.s3_bucket == "harness"


def test_environment_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_DSN", "postgresql+psycopg://u:p@db:5432/other")
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    settings = Settings()
    assert settings.postgres_dsn == "postgresql+psycopg://u:p@db:5432/other"
    assert settings.app_environment == "test"


def test_dotenv_file_is_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("REDIS_URL=redis://elsewhere:6379/1\n")
    settings = Settings()
    assert settings.redis_url == "redis://elsewhere:6379/1"


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
