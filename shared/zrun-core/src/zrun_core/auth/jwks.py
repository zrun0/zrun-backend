"""JWKS provider for JWT verification.

This module provides a reusable JWKS (JSON Web Key Set) provider
that can be used by both BFF (for Casdoor token verification) and
internal services (for BFF token verification).

Features:
- Async JWKS fetching with HTTP client
- TTL-based caching to reduce network calls
- Thread-safe double-check locking pattern
- Configurable cache TTL and timeout
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import structlog
from cachetools import TTLCache

from zrun_core.errors import InfrastructureError


logger = structlog.get_logger()


@dataclass(frozen=True)
class JWKSProviderConfig:
    """Configuration for JWKS provider.

    Attributes:
        jwks_url: URL to fetch JWKS from.
        cache_ttl_seconds: Cache TTL in seconds (default: 300 = 5 minutes).
        timeout_seconds: HTTP request timeout in seconds (default: 10).
        max_cache_size: Maximum number of JWKS to cache (default: 10).
    """

    jwks_url: str
    cache_ttl_seconds: int = 300
    timeout_seconds: int = 10
    max_cache_size: int = 10


class JWKSProviderError(InfrastructureError):
    """Error raised when JWKS fetching fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="JWKS_PROVIDER_ERROR")


class JWKSProvider:
    """Async JWKS provider with caching.

    This provider fetches JWKS from a given URL and caches them
    for a configurable TTL to reduce network calls.

    Thread-safe: Uses asyncio.Lock for concurrent access protection.

    Example:
        >>> provider = JWKSProvider(
        ...     config=JWKSProviderConfig(
        ...         jwks_url="https://casdoor.example.com/.well-known/jwks.json",
        ...         cache_ttl_seconds=300,
        ...     )
        ... )
        >>> jwks = await provider.get_jwks()
        >>> keys = jwks.get("keys", [])
    """

    def __init__(
        self,
        config: JWKSProviderConfig,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the JWKS provider.

        Args:
            config: Provider configuration.
            http_client: Optional HTTP client. If None, creates a new client.
        """
        self._config = config
        self._http_client = http_client or httpx.AsyncClient(
            timeout=config.timeout_seconds,
        )
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=config.max_cache_size,
            ttl=config.cache_ttl_seconds,
        )
        self._key_index: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._owned_client = http_client is None

    async def get_jwks(self) -> dict[str, Any]:
        """Get JWKS from cache or fetch fresh.

        Uses double-check locking pattern for thread safety:
        1. Check cache without lock
        2. If miss, acquire lock
        3. Check cache again (another goroutine may have fetched)
        4. Fetch if still missing

        Returns:
            JWKS dictionary with "keys" list.

        Raises:
            JWKSProviderError: If fetching JWKS fails.
        """
        cache_key = self._config.jwks_url

        # Fast path: check cache without lock
        if cache_key in self._cache:
            logger.debug("jwks_cache_hit", url=self._config.jwks_url)
            return self._cache[cache_key]

        # Slow path: acquire lock and fetch
        async with self._lock:
            # Double-check: another coroutine may have fetched
            if cache_key in self._cache:
                logger.debug("jwks_cache_hit_after_lock", url=self._config.jwks_url)
                return self._cache[cache_key]

            # Fetch fresh JWKS
            logger.info("jwks_fetching", url=self._config.jwks_url)
            try:
                response = await self._http_client.get(self._config.jwks_url)
                response.raise_for_status()
                jwks = response.json()

                # Validate JWKS structure
                if "keys" not in jwks:
                    msg = (
                        f"Invalid JWKS response: missing 'keys' field from {self._config.jwks_url}"
                    )
                    logger.error("jwks_invalid", error=msg)
                    raise JWKSProviderError(msg)

                self._cache[cache_key] = jwks

                # Build key index for O(1) lookup
                self._key_index = {key["kid"]: key for key in jwks.get("keys", []) if "kid" in key}

                key_count = len(jwks.get("keys", []))
                logger.info(
                    "jwks_fetched",
                    url=self._config.jwks_url,
                    key_count=key_count,
                    cache_ttl=self._config.cache_ttl_seconds,
                )
                return jwks

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                msg = f"HTTP error fetching JWKS: {status_code} from {self._config.jwks_url}"
                logger.error("jwks_http_error", status=status_code, url=self._config.jwks_url)
                raise JWKSProviderError(msg) from e
            except httpx.HTTPError as e:
                msg = f"Network error fetching JWKS: {e} from {self._config.jwks_url}"
                logger.error("jwks_network_error", error=str(e), url=self._config.jwks_url)
                raise JWKSProviderError(msg) from e

    def get_key_by_kid(self, kid: str) -> dict[str, Any] | None:
        """Get a key from JWKS by its key ID (kid).

        Provides O(1) lookup using the pre-built key index.

        Args:
            kid: Key ID to look up.

        Returns:
            Key dictionary if found, None otherwise.
        """
        return self._key_index.get(kid)

    async def close(self) -> None:
        """Close the HTTP client if owned by this provider.

        Should be called when shutting down the service.
        """
        if self._owned_client and self._http_client:
            await self._http_client.aclose()
            logger.debug("jwks_provider_closed", url=self._config.jwks_url)

    async def __aenter__(self) -> JWKSProvider:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()
