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
        "PROCESSING__DUPLICATE_TEXT_THRESHOLD",
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


class TestPolicyFile:
    """Human-editable YAML policy (docs/spec/15_CONFIGURATION.md)."""

    def test_defaults_apply_when_no_policy_file_exists(self) -> None:
        # The autouse fixture runs from an empty tmp_path, so config/policy.yaml
        # is absent here: a missing policy file must not break startup.
        settings = Settings()
        assert settings.processing.duplicate_text_threshold == 0.95
        assert settings.relevance_weights.structural == 0.20

    def test_policy_file_values_are_loaded(self, tmp_path: Path) -> None:
        policy = tmp_path / "config"
        policy.mkdir()
        (policy / "policy.yaml").write_text(
            "processing:\n"
            "  duplicate_text_threshold: 0.80\n"
            "relevance_weights:\n"
            "  structural: 0.40\n"
            "  semantic: 0.00\n"
            "  relationship: 0.15\n"
            "  visual: 0.15\n"
            "  freshness: 0.10\n"
            "  source_authority: 0.10\n"
            "  historical_demand: 0.10\n"
        )
        settings = Settings()
        assert settings.processing.duplicate_text_threshold == 0.80
        assert settings.relevance_weights.structural == 0.40

    def test_environment_overrides_the_policy_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        policy = tmp_path / "config"
        policy.mkdir()
        (policy / "policy.yaml").write_text(
            "processing:\n  duplicate_text_threshold: 0.80\n"
        )
        monkeypatch.setenv("PROCESSING__DUPLICATE_TEXT_THRESHOLD", "0.55")
        assert Settings().processing.duplicate_text_threshold == 0.55

    def test_invalid_threshold_in_policy_file_is_rejected(self, tmp_path: Path) -> None:
        policy = tmp_path / "config"
        policy.mkdir()
        (policy / "policy.yaml").write_text(
            "processing:\n  duplicate_text_threshold: 1.5\n"
        )
        with pytest.raises(ValueError):
            Settings()
