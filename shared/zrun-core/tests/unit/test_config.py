"""Unit tests for configuration management."""

from __future__ import annotations

import pytest

from zrun_core.infra import ServiceConfig, get_config


class TestServiceConfig:
    """Tests for ServiceConfig class."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = ServiceConfig()
        assert config.env == "dev"
        assert config.port == 50051
        assert config.log_level == "INFO"
        assert config.log_format == "console"
        assert config.enable_auth is False
        assert config.enable_metrics is True
        assert config.enable_tracing is False

    @pytest.mark.parametrize(
        ("env", "expected_is_prod", "expected_is_dev", "expected_is_staging"),
        [
            ("prod", True, False, False),
            ("dev", False, True, False),
            ("staging", False, False, True),
        ],
    )
    def test_env_properties(
        self,
        env: str,
        expected_is_prod: bool,
        expected_is_dev: bool,
        expected_is_staging: bool,
    ) -> None:
        """Test is_prod, is_dev, and is_staging properties for each environment."""
        config = ServiceConfig(env=env)  # type: ignore[arg-type]
        assert config.is_prod is expected_is_prod
        assert config.is_dev is expected_is_dev
        assert config.is_staging is expected_is_staging

    @pytest.mark.parametrize(
        ("pool_size", "expected_min"),
        [
            (10, 5),  # Standard: half of pool_size
            (1, 1),  # Floor at 1 when half rounds down to 0
            (0, 1),  # Floor at 1 even for zero pool_size
        ],
    )
    def test_database_pool_min_size(self, pool_size: int, expected_min: int) -> None:
        """Test database_pool_min_size is half of pool_size, floored at 1."""
        config = ServiceConfig(database_pool_size=pool_size)
        assert config.database_pool_min_size == expected_min


class TestGetConfig:
    """Tests for get_config function."""

    def test_get_config_returns_service_config(self) -> None:
        """Test get_config returns ServiceConfig instance."""
        config = get_config()
        assert isinstance(config, ServiceConfig)

    def test_get_config_is_cached(self) -> None:
        """Test get_config caches the configuration."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2


class TestEnvironmentVariables:
    """Tests for environment variable loading."""

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test environment variable override."""
        monkeypatch.setenv("ENV", "prod")
        monkeypatch.setenv("PORT", "8080")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        config = ServiceConfig()
        assert config.env == "prod"
        assert config.port == 8080
        assert config.log_level == "DEBUG"

    def test_database_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test DATABASE_URL override."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db")
        config = ServiceConfig()
        assert config.database_url == "postgresql://user:pass@host:5432/db"

    def test_redis_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test REDIS_URL override."""
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
        config = ServiceConfig()
        assert config.redis_url == "redis://localhost:6379/1"

    def test_auth_config_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test authentication config override."""
        monkeypatch.setenv("JWKS_URL", "https://auth.example.com/jwks")
        monkeypatch.setenv("JWT_AUDIENCE", "my-app")
        monkeypatch.setenv("JWT_ISSUER", "https://auth.example.com")
        monkeypatch.setenv("ENABLE_AUTH", "true")

        config = ServiceConfig()
        assert config.jwks_url == "https://auth.example.com/jwks"
        assert config.jwt_audience == "my-app"
        assert config.jwt_issuer == "https://auth.example.com"
        assert config.enable_auth is True

    def test_feature_flags_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test feature flags override."""
        monkeypatch.setenv("ENABLE_AUTH", "true")
        monkeypatch.setenv("ENABLE_METRICS", "false")
        monkeypatch.setenv("ENABLE_TRACING", "true")

        config = ServiceConfig()
        assert config.enable_auth is True
        assert config.enable_metrics is False
        assert config.enable_tracing is True

    def test_redlock_requires_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that redlock mode requires lock_redis_urls."""
        monkeypatch.setenv("LOCK_MODE", "redlock")
        # lock_redis_urls is empty by default

        with pytest.raises(ValueError, match="lock_redis_urls must contain at least one URL"):
            ServiceConfig()

    def test_redlock_with_urls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that redlock mode works with URLs provided."""
        monkeypatch.setenv("LOCK_MODE", "redlock")
        monkeypatch.setenv("LOCK_REDIS_URLS", '["redis://host1", "redis://host2"]')

        config = ServiceConfig()
        assert config.lock_mode == "redlock"
        assert len(config.lock_redis_urls) == 2
