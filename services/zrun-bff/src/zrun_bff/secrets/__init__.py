"""Key provider abstraction for secure credential management.

Supports two backends:
- EnvKeyProvider:  reads from environment variables (dev / CI overrides)
- FileKeyProvider: reads from files on disk (K8s Secret volume mounts)

The "auto" mode (default) tries Env first, then File.

Environment Variables:
    KEY_PROVIDER: Provider to use (auto|env|file). Default: auto.
    SECRETS_PATH: Base path for file provider. Default: /etc/secrets.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
from typing import Literal

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger()


@dataclass(frozen=True)
class KeyMetadata:
    """Metadata for a key fetch operation."""

    key_name: str
    provider: str
    source: str
    cache_hit: bool = False


class KeyProvider(ABC):
    """Abstract base class for key providers."""

    @abstractmethod
    def get_key(self, key_name: str) -> str:
        """Get a key/secret value.

        Args:
            key_name: Name of the key to fetch (e.g., "jwt_private_key").

        Returns:
            The key value as a string.

        Raises:
            KeyError: If the key is not found.
            RuntimeError: If the provider is unavailable.
        """
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier string."""
        ...


class EnvKeyProvider(KeyProvider):
    """Reads keys from environment variables.

    Highest priority — useful for development and quick overrides.
    """

    def __init__(self) -> None:
        self._prefix_map: dict[str, str] = {
            "jwt_private_key": "JWT_PRIVATE_KEY",
            "casdoor_client_secret": "CASDOOR_CLIENT_SECRET",
            "database_url": "DATABASE_URL",
        }

    def get_key(self, key_name: str) -> str:
        env_var = self._prefix_map.get(key_name, key_name.upper())
        value = os.getenv(env_var, "")
        if not value:
            msg = f"Environment variable {env_var} not set"
            raise KeyError(msg)
        logger.debug("key_from_env", key=key_name, env_var=env_var)
        return value

    def health_check(self) -> bool:
        return True

    @property
    def provider_name(self) -> str:
        return "env"


class FileKeyProvider(KeyProvider):
    """Reads keys from files on disk (K8s Secret volume mounts).

    Supports both direct file paths and structured formats.
    """

    def __init__(self, base_path: str = "/etc/secrets") -> None:
        self._base_path = base_path
        self._key_map: dict[str, str] = {
            "jwt_private_key": "jwt_private_key.pem",
            "casdoor_client_secret": "casdoor_client_secret.txt",
            "database_url": "database_url.txt",
        }

    def get_key(self, key_name: str) -> str:
        from pathlib import Path

        filename = self._key_map.get(key_name, f"{key_name}.txt")
        file_path = Path(self._base_path) / filename
        if not file_path.exists():
            msg = f"Key file not found: {file_path}"
            raise KeyError(msg)
        value = file_path.read_text().strip()
        logger.debug("key_from_file", key=key_name, path=str(file_path))
        return value

    def health_check(self) -> bool:
        from pathlib import Path

        return Path(self._base_path).exists()

    @property
    def provider_name(self) -> str:
        return "file"


class KeyProviderConfig(BaseSettings):
    """Configuration for key provider selection.

    Environment Variables:
        KEY_PROVIDER: Provider to use (auto|env|file). Default: auto.
        SECRETS_PATH: Base path for file provider. Default: /etc/secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    key_provider: Literal["auto", "env", "file"] = "auto"
    secrets_path: str = "/etc/secrets"


@cache
def _get_key_provider_cached(_config_hash: int) -> KeyProvider:
    config = KeyProviderConfig()
    return _create_provider(config)


def _create_provider(config: KeyProviderConfig) -> KeyProvider:
    provider_type = config.key_provider

    if provider_type == "env":
        return EnvKeyProvider()
    if provider_type == "file":
        return FileKeyProvider(base_path=config.secrets_path)

    # auto: try Env first, then File
    providers: list[KeyProvider] = [
        EnvKeyProvider(),
        FileKeyProvider(base_path=config.secrets_path),
    ]
    last_error: Exception | None = None
    for provider in providers:
        try:
            if provider.health_check():
                logger.info(
                    "key_provider_selected",
                    provider=provider.provider_name,
                )
                return provider
        except (ImportError, RuntimeError, OSError, KeyError) as e:
            logger.warning(
                "key_provider_unavailable",
                provider=provider.provider_name,
                error=str(e),
            )
            last_error = e

    msg = f"No key provider available. Tried: {[p.provider_name for p in providers]}"
    raise RuntimeError(msg) from last_error


def get_key_provider(config: KeyProviderConfig | None = None) -> KeyProvider:
    """Get the configured key provider instance.

    Args:
        config: Provider configuration. If None, loads from environment.

    Returns:
        A KeyProvider instance based on configuration.
    """
    if config is None:
        config = KeyProviderConfig()
    config_hash = hash(str(sorted(config.model_dump().items())))
    return _get_key_provider_cached(config_hash)


def get_key(key_name: str, config: KeyProviderConfig | None = None) -> str:
    """Get a key value from the configured provider.

    Args:
        key_name: Name of the key to fetch (e.g., "jwt_private_key").
        config: Optional provider configuration.

    Returns:
        The key value as a string.

    Raises:
        KeyError: If the key is not found in any provider.
        RuntimeError: If no provider is available.
    """
    return get_key_provider(config).get_key(key_name)


__all__ = [
    "EnvKeyProvider",
    "FileKeyProvider",
    "KeyMetadata",
    "KeyProvider",
    "KeyProviderConfig",
    "get_key",
    "get_key_provider",
]
