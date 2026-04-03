"""Key provider abstraction for secure credential management.

This module provides a unified interface for fetching secrets from multiple
backends, enabling smooth migration from K8s Secrets to Vault without
code changes.

Migration Path:
    Phase 1: K8s Secrets (FileProvider via mounted volumes)
    Phase 2: Vault (VaultProvider) - gradual rollout
    Phase 3: Vault (full migration) - remove K8s Secrets

Environment Variables:
    KEY_PROVIDER: Provider to use (auto|env|file|k8s|vault)
    VAULT_ADDR: Vault server address
    VAULT_ROLE: Vault Kubernetes authentication role
    VAULT_NAMESPACE: Vault namespace (Enterprise)
    VAULT_PATH_PREFIX: Prefix for Vault secrets (default: secret/zrun)
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal

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
    """Abstract base class for key providers.

    All providers must implement the get_key method to fetch credentials.
    """

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
        """Check if the provider is healthy.

        Returns:
            True if the provider is available, False otherwise.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of this provider."""
        ...


class EnvKeyProvider(KeyProvider):
    """Provider that reads keys from environment variables.

    Highest priority - useful for development and quick overrides.
    """

    def __init__(self) -> None:
        """Initialize environment provider."""
        self._prefix_map: dict[str, str] = {
            "jwt_private_key": "JWT_PRIVATE_KEY",
            "casdoor_client_secret": "CASDOOR_CLIENT_SECRET",
            "database_url": "DATABASE_URL",
        }

    def get_key(self, key_name: str) -> str:
        """Get key from environment variable."""
        env_var = self._prefix_map.get(key_name, key_name.upper())
        value = os.getenv(env_var, "")

        if not value:
            msg = f"Environment variable {env_var} not set"
            raise KeyError(msg)

        logger.debug("key_from_env", key=key_name, env_var=env_var)
        return value

    def health_check(self) -> bool:
        """Environment provider is always healthy."""
        return True

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "env"


class FileKeyProvider(KeyProvider):
    """Provider that reads keys from files.

    Used for K8s Secrets mounted as volumes, or local files in development.
    Supports both direct file paths and structured formats (JSON, YAML).
    """

    def __init__(self, base_path: str = "/etc/secrets") -> None:
        """Initialize file provider with base path."""
        self._base_path = base_path
        self._key_map: dict[str, str] = {
            "jwt_private_key": "jwt_private_key.pem",
            "casdoor_client_secret": "casdoor_client_secret.txt",
            "database_url": "database_url.txt",
        }

    def get_key(self, key_name: str) -> str:
        """Get key from file."""
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
        """Check if base directory is readable."""
        from pathlib import Path

        return Path(self._base_path).exists()

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "file"


class K8sSecretProvider(KeyProvider):
    """Provider that reads K8s Secrets via the Kubernetes API.

    Directly accesses K8s Secrets without mounting volumes.
    Useful for pod-to-secret communication without volume mounts.
    """

    def __init__(self) -> None:
        """Initialize K8s provider."""
        self._client: Any | None = None
        self._namespace: str = os.getenv("POD_NAMESPACE", "default")

    def _get_client(self) -> Any:
        """Lazy-load the kubernetes client."""
        if self._client is None:
            try:
                from kubernetes import client, config  # type: ignore[import-untyped]

                # Try in-cluster config first, then fallback to kubeconfig
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config()

                self._client = client.CoreV1Api()
            except ImportError as e:
                msg = "kubernetes package not installed"
                raise RuntimeError(msg) from e

        return self._client

    def get_key(self, key_name: str) -> str:
        """Get key from K8s Secret."""
        client = self._get_client()

        # Parse key_name: "secret_name/data_key" or just "secret_name"
        parts = key_name.split("/", 1)
        secret_name = parts[0]
        data_key = parts[1] if len(parts) > 1 else key_name

        try:
            secret = client.read_namespaced_secret(
                name=secret_name,
                namespace=self._namespace,
            )
        except Exception as e:
            msg = f"Failed to read K8s secret {secret_name}: {e}"
            raise KeyError(msg) from e

        if secret.data is None or data_key not in secret.data:
            msg = f"Key {data_key} not found in secret {secret_name}"
            raise KeyError(msg)

        import base64

        value = base64.b64decode(secret.data[data_key]).decode("utf-8")
        logger.debug("key_from_k8s", key=key_name, secret=secret_name)
        return value

    def health_check(self) -> bool:
        """Check if K8s API is accessible."""
        try:
            self._get_client()
            return True
        except ImportError, RuntimeError, OSError:
            return False

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "k8s"


class VaultKeyProvider(KeyProvider):
    """Provider that reads keys from HashiCorp Vault.

    Supports Kubernetes authentication method and KV secrets engine v2.
    Designed for production use with automatic token renewal and retry logic.

    Environment Variables:
        VAULT_ADDR: Vault server address (required)
        VAULT_ROLE: Kubernetes authentication role (required)
        VAULT_NAMESPACE: Vault namespace for Enterprise (optional)
        VAULT_PATH_PREFIX: Prefix for secrets (default: secret/zrun)
    """

    def __init__(
        self,
        address: str | None = None,
        role: str | None = None,
        namespace: str | None = None,
        path_prefix: str = "secret/zrun",
    ) -> None:
        """Initialize Vault provider.

        Args:
            address: Vault server address. Defaults to VAULT_ADDR env var.
            role: Kubernetes authentication role. Defaults to VAULT_ROLE env var.
            namespace: Vault namespace for Enterprise. Defaults to VAULT_NAMESPACE env var.
            path_prefix: Prefix for secrets. Defaults to "secret/zrun".
        """
        self._address = address or os.getenv("VAULT_ADDR")
        self._role = role or os.getenv("VAULT_ROLE")
        self._namespace = namespace or os.getenv("VAULT_NAMESPACE")
        self._path_prefix = path_prefix

        if not self._address:
            msg = "VAULT_ADDR environment variable is required for Vault provider"
            raise RuntimeError(msg)

        self._client: Any | None = None
        self._token_ttl: int = 0
        self._token_expiry: float = 0

    def _get_client(self) -> Any:
        """Lazy-load and authenticate the Vault client."""
        if self._client is not None:
            # Check if token needs renewal
            if time.time() < self._token_expiry:
                return self._client
            # Token expired, need to re-authenticate
            self._client = None

        try:
            import hvac  # type: ignore[import-untyped]

            client = hvac.Client(
                url=self._address,
                namespace=self._namespace,
            )

            # Kubernetes authentication
            jwt_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
            from pathlib import Path

            jwt_token = Path(jwt_path).read_text()

            client.auth.kubernetes.login(
                role=self._role or "bff-service",
                jwt=jwt_token,
            )

            # Set token expiry (renew before expiry)
            self._token_expiry = time.time() + client.auth.token.lease_duration - 60
            self._client = client

            logger.info("vault_authenticated", role=self._role, ttl=self._token_ttl)
            return self._client

        except ImportError as e:
            msg = "hvac package not installed"
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Failed to authenticate with Vault: {e}"
            raise RuntimeError(msg) from e

    def get_key(self, key_name: str) -> str:
        """Get key from Vault KV secrets engine v2."""
        client = self._get_client()

        secret_path = f"{self._path_prefix}/{key_name}"

        try:
            response = client.secrets.kv.v2.read_secret_version(path=secret_path)
            value = response["data"]["data"]["value"]

            logger.debug("key_from_vault", key=key_name, path=secret_path)
            return value

        except Exception as e:
            msg = f"Failed to read secret from Vault ({secret_path}): {e}"
            raise KeyError(msg) from e

    def health_check(self) -> bool:
        """Check if Vault is accessible."""
        try:
            client = self._get_client()
            # Try to read a non-critical path
            client.secrets.kv.v2.read_secret_version(path=f"{self._path_prefix}/health")
            return True
        except ImportError, RuntimeError, OSError:
            return False

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "vault"


class KeyProviderConfig(BaseSettings):
    """Configuration for key provider selection.

    Environment Variables:
        KEY_PROVIDER: Provider to use (auto|env|file|k8s|vault)
                      Default: auto (tries each provider in priority order)
        KEY_PROVIDER_FALLBACK: Enable fallback to next provider on failure
                              Default: true
        VAULT_ADDR: Vault server address
        VAULT_ROLE: Vault Kubernetes authentication role
        SECRETS_PATH: Base path for file provider (default: /etc/secrets)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    key_provider: Literal["auto", "env", "file", "k8s", "vault"] = "auto"
    key_provider_fallback: bool = True
    vault_addr: str = ""
    vault_role: str = ""
    vault_namespace: str = ""
    vault_path_prefix: str = "secret/zrun"
    secrets_path: str = "/etc/secrets"


@cache
def _get_key_provider_cached(_config_hash: int) -> KeyProvider:
    """Cached key provider getter (hash-based to avoid unhashable config).

    Args:
        _config_hash: Hash of the config object for cache key.

    Returns:
        A KeyProvider instance.
    """
    config = KeyProviderConfig()
    return _create_provider(config)


def _create_provider(config: KeyProviderConfig) -> KeyProvider:
    """Create a provider instance based on configuration.

    Args:
        config: Provider configuration.

    Returns:
        A KeyProvider instance.
    """
    provider_type = config.key_provider

    # Build provider chain for "auto" mode
    providers: list[KeyProvider] = []

    if provider_type == "auto":
        # Priority: env -> file -> k8s -> vault
        providers.extend(
            [
                EnvKeyProvider(),
                FileKeyProvider(base_path=config.secrets_path),
            ]
        )

        # Add K8s provider if in cluster
        from pathlib import Path

        if Path("/var/run/secrets/kubernetes.io/serviceaccount/token").exists():
            providers.append(K8sSecretProvider())

        # Add Vault if configured
        if config.vault_addr:
            providers.append(
                VaultKeyProvider(
                    address=config.vault_addr,
                    role=config.vault_role,
                    namespace=config.vault_namespace or None,
                    path_prefix=config.vault_path_prefix,
                )
            )

    else:
        # Use specific provider
        if provider_type == "vault" and not config.vault_addr:
            msg = "Vault provider requires VAULT_ADDR environment variable"
            raise RuntimeError(msg)

        provider = _create_single_provider(provider_type, config)
        providers.append(provider)

    # Try providers in order
    last_error: Exception | None = None

    for provider in providers:
        try:
            if provider.health_check():
                logger.info(
                    "key_provider_selected",
                    provider=provider.provider_name,
                    selected_from=provider_type,
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


def _create_single_provider(
    provider_type: str,
    config: KeyProviderConfig,
) -> KeyProvider:
    """Create a single provider instance.

    Args:
        provider_type: Type of provider to create.
        config: Provider configuration.

    Returns:
        A KeyProvider instance.
    """
    if provider_type == "env":
        return EnvKeyProvider()
    if provider_type == "file":
        return FileKeyProvider(base_path=config.secrets_path)
    if provider_type == "k8s":
        return K8sSecretProvider()
    if provider_type == "vault":
        return VaultKeyProvider(
            address=config.vault_addr,
            role=config.vault_role,
            namespace=config.vault_namespace or None,
            path_prefix=config.vault_path_prefix,
        )

    msg = f"Unknown provider type: {provider_type}"
    raise ValueError(msg)


def get_key_provider(config: KeyProviderConfig | None = None) -> KeyProvider:
    """Get the configured key provider instance.

    Args:
        config: Provider configuration. If None, loads from environment.

    Returns:
        A KeyProvider instance based on configuration.

    Raises:
        RuntimeError: If no provider is available.
    """
    if config is None:
        config = KeyProviderConfig()

    # Use hash for cache key since config is not hashable
    config_dict = config.model_dump()
    config_hash = hash(str(sorted(config_dict.items())))

    return _get_key_provider_cached(config_hash)


def get_key(key_name: str, config: KeyProviderConfig | None = None) -> str:
    """Get a key value from the configured provider.

    This is the main entry point for application code to fetch secrets.

    Args:
        key_name: Name of the key to fetch (e.g., "jwt_private_key").
        config: Optional provider configuration.

    Returns:
        The key value as a string.

    Raises:
        KeyError: If the key is not found in any provider.
        RuntimeError: If no provider is available.

    Example:
        >>> # In application code
        >>> from zrun_bff.secrets import get_key
        >>>
        >>> # Get JWT private key
        >>> private_key = get_key("jwt_private_key")
        >>>
        >>> # Get database URL
        >>> db_url = get_key("database_url")
    """
    provider = get_key_provider(config)
    return provider.get_key(key_name)


__all__ = [
    "get_key",
    "get_key_provider",
    "KeyProvider",
    "KeyProviderConfig",
    "KeyMetadata",
    "EnvKeyProvider",
    "FileKeyProvider",
    "K8sSecretProvider",
    "VaultKeyProvider",
]
