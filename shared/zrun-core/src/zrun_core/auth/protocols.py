"""Protocol interfaces for authentication components.

This module defines Protocol interfaces for authentication-related components,
enabling dependency injection and improved testability.

Protocols:
    JWKSProviderProtocol: Interface for JWKS providers
    JWTVerifierProtocol: Interface for JWT verifiers
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping


@runtime_checkable
class JWKSProviderProtocol(Protocol):
    """Protocol for JWKS providers.

    A JWKS provider is responsible for fetching and caching JSON Web Key Sets
    from an identity provider or other source.

    Implementations can use different strategies:
    - HTTP fetcher with TTL caching
    - In-memory provider for testing
    - Redis-backed provider for distributed caching
    """

    async def get_jwks(self) -> Mapping[str, object]:
        """Get JWKS from cache or fetch fresh.

        Returns:
            JWKS dictionary with "keys" list.

        Raises:
            JWKSProviderError: If fetching JWKS fails.
        """
        ...

    def get_key_by_kid(self, kid: str) -> dict[str, Any] | None:
        """Get a key from JWKS by its key ID (kid).

        Provides O(1) lookup using the pre-built key index.

        Args:
            kid: Key ID to look up.

        Returns:
            Key dictionary if found, None otherwise.
        """
        ...

    async def close(self) -> None:
        """Close the provider and release resources.

        Should be called when shutting down the service.
        """
        ...

    async def __aenter__(self) -> JWKSProviderProtocol:
        """Async context manager entry."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Async context manager exit."""
        ...


@runtime_checkable
class JWTVerifierProtocol(Protocol):
    """Protocol for JWT verifiers.

    A JWT verifier is responsible for validating JWT tokens and returning
    their payload if valid.

    Implementations can use different strategies:
    - JWKS-based verification for RS256 tokens
    - Secret-based verification for HS256 tokens
    - Mock verifier for testing
    """

    async def verify(
        self,
        token: str,
    ) -> Mapping[str, object]:
        """Verify JWT token and return payload.

        Args:
            token: JWT token string.

        Returns:
            Token payload dictionary if valid.

        Raises:
            JWTVerificationError: If verification fails.
        """
        ...
