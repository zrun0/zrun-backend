"""Configuration management for zrun services."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceConfig(BaseSettings):
    """Configuration for zrun services loaded from environment variables."""

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

    # Distributed Lock
    lock_mode: Literal["single", "redlock"] = "single"
    lock_redis_urls: list[str] = []
    lock_ttl: int = 30  # Lock TTL in seconds
    lock_retry_times: int = 3  # Retry attempts for lock acquisition
    lock_retry_delay: float = 0.2  # Delay between retries in seconds
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

    @model_validator(mode="after")
    def validate_lock_config(self) -> ServiceConfig:
        """Require at least one Redis URL when lock_mode is 'redlock'."""
        if self.lock_mode == "redlock" and not self.lock_redis_urls:
            msg = "lock_redis_urls must contain at least one URL when lock_mode is 'redlock'"
            raise ValueError(msg)
        return self

    @property
    def is_prod(self) -> bool:
        """Check if running in production."""
        return self.env == "prod"

    @property
    def is_dev(self) -> bool:
        """Check if running in development."""
        return self.env == "dev"

    @property
    def is_staging(self) -> bool:
        """Check if running in staging."""
        return self.env == "staging"

    @property
    def database_pool_min_size(self) -> int:
        """Minimum pool size: half of pool_size, floored at 1."""
        return max(1, self.database_pool_size // 2)


@lru_cache
def get_config() -> ServiceConfig:
    """Return the cached service configuration."""
    return ServiceConfig()
