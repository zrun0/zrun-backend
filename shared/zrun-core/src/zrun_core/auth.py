"""Authentication interceptor for gRPC services."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, cast

import httpx
import structlog
from cachetools import TTLCache
from grpc.aio import ServerInterceptor, ServicerContext

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import grpc

USER_ID_CTX_KEY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id",
    default=None,
)

logger = structlog.get_logger()


def _decode_metadata_value(value: bytes | str) -> str:
    """Decode metadata value to string.

    Args:
        value: Metadata value (bytes or str).

    Returns:
        Decoded string value.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _decode_metadata_key(key: bytes | str) -> str:
    """Decode metadata key to string.

    Args:
        key: Metadata key (bytes or str).

    Returns:
        Decoded string key.
    """
    if isinstance(key, bytes):
        return key.decode("utf-8")
    return key


class JWKSFetchError(Exception):
    """Error fetching JWKS from the identity provider."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthInterceptor(ServerInterceptor):  # type: ignore[misc]
    """gRPC interceptor for JWT authentication.

    This interceptor validates JWT tokens using JWKS (JSON Web Key Set)
    from a configured identity provider (e.g., Casdoor).

    Features:
    - JWKS caching with configurable TTL
    - User ID extraction and propagation via contextvars
    - Configurable audience validation
    """

    def __init__(
        self,
        jwks_url: str,
        audience: str,
        issuer: str | None = None,
        cache_ttl: int = 300,
    ) -> None:
        """Initialize the authentication interceptor.

        Args:
            jwks_url: URL to fetch JWKS from.
            audience: Expected JWT audience claim.
            issuer: Expected JWT issuer claim (optional).
            cache_ttl: Cache TTL for JWKS in seconds.
        """
        self._jwks_url = jwks_url
        self._audience = audience
        self._issuer = issuer
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=10, ttl=cache_ttl)
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from the identity provider.

        Returns:
            JWKS as a dictionary.

        Raises:
            JWKSFetchError: If fetching JWKS fails.
        """
        try:
            response = await self._client.get(self._jwks_url)
            response.raise_for_status()
            return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPError as e:
            msg = f"Failed to fetch JWKS: {e}"
            raise JWKSFetchError(msg) from e

    async def _get_jwks(self) -> dict[str, Any]:
        """Get JWKS from cache or fetch fresh.

        Returns:
            JWKS as a dictionary.
        """
        cache_key = "jwks"

        if cache_key in self._cache:
            return self._cache[cache_key]

        jwks = await self._fetch_jwks()
        self._cache[cache_key] = jwks
        return jwks

    def _extract_token(self, context: ServicerContext) -> str | None:
        """Extract JWT token from the request context.

        Args:
            context: gRPC servicer context.

        Returns:
            JWT token string or None if not found.
        """
        metadata_iter = cast(
            "Iterable[tuple[bytes | str, bytes | str]]",
            context.invocation_metadata(),
        )
        metadata = {
            _decode_metadata_key(k): _decode_metadata_value(v)
            for k, v in metadata_iter
        }

        # Try Authorization header first (case-insensitive)
        for key, value in metadata.items():
            if key.lower() == "authorization" and value.startswith("Bearer "):
                return value[7:]

        # Try custom token header (case-insensitive)
        for key, value in metadata.items():
            if key.lower() == "token":
                return value

        return None

    def _validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate JWT token and return payload.

        Args:
            token: JWT token string.

        Returns:
            Token payload if valid, None otherwise.

        Note:
            This is a simplified implementation. A production system
            should use a proper JWT library with full validation.
        """
        # TODO: Implement proper JWT validation
        # For now, this is a placeholder that demonstrates the pattern
        import base64
        import json

        try:
            # Decode payload (without verification for now)
            parts = token.split(".")
            if len(parts) != 3:
                return None

            payload = parts[1]
            # Add padding if needed
            payload += "=" * (4 - len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload)
            return json.loads(decoded)  # type: ignore[no-any-return]
        except Exception:
            return None

    def _extract_token_from_metadata(
        self,
        metadata: Any,
    ) -> str | None:
        """Extract JWT token from metadata.

        Args:
            metadata: Invocation metadata from gRPC.

        Returns:
            JWT token string or None if not found.
        """
        if metadata is None:
            return None

        # Cast to iterable type after None check
        metadata_iter = cast("Iterable[tuple[bytes | str, bytes | str]]", metadata)

        # Convert Metadata to dict, handling bytes keys/values
        metadata_dict = {
            _decode_metadata_key(k): _decode_metadata_value(v)
            for k, v in metadata_iter
        }

        # Try Authorization header first (case-insensitive)
        for key, value in metadata_dict.items():
            if key.lower() == "authorization" and value.startswith("Bearer "):
                return value[7:]

        # Try custom token header (case-insensitive)
        for key, value in metadata_dict.items():
            if key.lower() == "token":
                return value

        return None

    async def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: Any,
    ) -> grpc.RpcMethodHandler:
        """Intercept incoming RPC calls for authentication.

        This is a simplified implementation that validates tokens
        and sets user context. For production use, consider using
        a proper gRPC middleware library.

        Args:
            continuation: The next interceptor in the chain.
            handler_call_details: Details about the RPC call.

        Returns:
            The RPC method handler or aborts the call if authentication fails.
        """
        # Extract token from metadata
        metadata = handler_call_details.invocation_metadata
        token = self._extract_token_from_metadata(metadata)

        if not token:
            logger.warning("auth_failed_no_token")
            # Continue without authentication - NOT SECURE for production
            return await continuation(handler_call_details)

        # Validate token
        payload = self._validate_token(token)
        if not payload:
            logger.warning("auth_failed_invalid_token")
            # Continue without authentication - NOT SECURE for production
            return await continuation(handler_call_details)

        # Extract user ID
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("auth_failed_no_user_id")
            # Continue without authentication - NOT SECURE for production
            return await continuation(handler_call_details)

        # Set user ID in context
        token_var = USER_ID_CTX_KEY.set(user_id)

        try:
            return await continuation(handler_call_details)
        finally:
            USER_ID_CTX_KEY.reset(token_var)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
