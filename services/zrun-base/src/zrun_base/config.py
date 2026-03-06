"""Configuration for the zrun-base service."""

from __future__ import annotations

from enum import Enum

from zrun_core.config import ServiceConfig


class DatabaseBackend(Enum):
    """Database backend options."""

    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"


class BaseServiceConfig(ServiceConfig):
    """Configuration specific to the base service.

    Inherits all configuration from ServiceConfig and adds
    service-specific settings.
    """

    database_backend: DatabaseBackend = DatabaseBackend.POSTGRESQL

    # SQLite specific (for testing/development)
    sqlite_path: str = ":memory:"

    @property
    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL."""
        return self.database_backend == DatabaseBackend.POSTGRESQL

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.database_backend == DatabaseBackend.SQLITE


def get_base_config() -> BaseServiceConfig:
    """Get the base service configuration.

    Returns:
        The base service configuration.
    """
    return BaseServiceConfig()
