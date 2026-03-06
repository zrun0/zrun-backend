"""Unit tests for configuration management."""

from __future__ import annotations

import os

import pytest

from zrun_core.config import ServiceConfig, get_config


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

    def test_is_prod_property(self) -> None:
        """Test is_prod property."""
        config = ServiceConfig(env="prod")
        assert config.is_prod is True
        assert config.is_dev is False

    def test_is_dev_property(self) -> None:
        """Test is_dev property."""
        config = ServiceConfig(env="dev")
        assert config.is_dev is True
        assert config.is_prod is False

    def test_database_pool_min_size(self) -> None:
        """Test database_pool_min_size calculation."""
        config = ServiceConfig(database_pool_size=10)
        assert config.database_pool_min_size == 5

    def test_database_pool_min_size_minimum(self) -> None:
        """Test database_pool_min_size has minimum of 1."""
        config = ServiceConfig(database_pool_size=1)
        assert config.database_pool_min_size == 1

    def test_database_pool_min_size_zero(self) -> None:
        """Test database_pool_min_size with zero pool size."""
        config = ServiceConfig(database_pool_size=0)
        # max(1, 0 // 2) = max(1, 0) = 1
        assert config.database_pool_min_size == 1


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
