"""Configuration management for zrun services."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for zrun services.

    This class uses pydantic-settings to load configuration from
    environment variables with type validation and conversion.

    Environment variables:
        ENV: Environment name (dev, staging, prod)
        DATABASE_URL: PostgreSQL connection URL
        REDIS_URL: Redis connection URL
        JWKS_URL: URL to fetch JWKS from
        JWT_AUDIENCE: Expected JWT audience
        JWT_ISSUER: Expected JWT issuer (optional)
        PORT: gRPC server port (default: 50051)
        LOG_LEVEL: Logging level (default: INFO)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    env: Literal["dev", "staging", "prod"] = "dev"

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/zrun"
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 10
    redis_db: int = 0

    # Distributed Lock
    lock_mode: Literal["single", "redlock"] = "single"
    lock_redis_urls: list[str] = []  # Multi-node URLs for redlock mode
    lock_ttl: int = 30  # Lock TTL in seconds
    lock_retry_times: int = 3  # Retry times for lock acquisition
    lock_retry_delay: float = 0.2  # Retry delay in seconds
    lock_drift_factor: float = 0.01  # Clock drift factor for redlock
    lock_auto_renewal: bool = True  # Auto-renewal for single-node locks
    lock_renewal_interval: float = 0.8  # Fraction of TTL before renewal

    # Authentication
    jwks_url: str = "http://localhost:8080/.well-known/jwks.json"
    jwt_audience: str = "zrun"
    jwt_issuer: str | None = None

    # Server
    port: int = 50051
    max_workers: int = 10

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "console"

    # Feature flags
    enable_auth: bool = False  # Disabled by default in dev
    enable_metrics: bool = True
    enable_tracing: bool = False

    @property
    def is_prod(self) -> bool:
        """Check if running in production."""
        return self.env == "prod"

    @property
    def is_dev(self) -> bool:
        """Check if running in development."""
        return self.env == "dev"

    @property
    def database_pool_min_size(self) -> int:
        """Minimum database pool size."""
        return max(1, self.database_pool_size // 2)


@lru_cache
def get_config() -> ServiceConfig:
    """Get the cached service configuration.

    This function caches the configuration to avoid repeated
    environment variable lookups.

    Returns:
        The service configuration.
    """
    return ServiceConfig()
