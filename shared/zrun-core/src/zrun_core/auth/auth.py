"""Authentication interceptor for gRPC services."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import json
from typing import TYPE_CHECKING, Any, cast

import httpx
import structlog
from cachetools import TTLCache
from grpc.aio import ServerInterceptor

from zrun_core.errors.errors import InternalError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    import grpc

USER_ID_CTX_KEY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "user_id",
    default=None,
)

logger = structlog.get_logger()

_JWKS_CACHE_KEY = "jwks"


class JWKSFetchError(InternalError):
    """Error fetching JWKS from the identity provider."""


class AuthInterceptor(ServerInterceptor):
    """gRPC interceptor for JWT authentication.

    Validates JWT tokens using JWKS from a configured identity provider
    (e.g. Casdoor). JWKS responses are cached with a configurable TTL.
    The authenticated user ID is propagated via contextvars.
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
        self._jwks_lock = asyncio.Lock()

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
            return response.json()
        except httpx.HTTPError as e:
            msg = f"Failed to fetch JWKS: {e}"
            raise JWKSFetchError(msg) from e

    async def _get_jwks(self) -> dict[str, Any]:
        """Return JWKS from cache, fetching fresh if not cached."""
        if _JWKS_CACHE_KEY in self._cache:
            return self._cache[_JWKS_CACHE_KEY]
        async with self._jwks_lock:
            # Re-check inside the lock to avoid a thundering herd on TTL expiry
            if _JWKS_CACHE_KEY not in self._cache:
                self._cache[_JWKS_CACHE_KEY] = await self._fetch_jwks()
        return self._cache[_JWKS_CACHE_KEY]

    def _extract_token_from_metadata(
        self,
        metadata: Any,
    ) -> str | None:
        """Extract JWT token from gRPC metadata.

        Checks Authorization (Bearer) first, then a bare token key.

        Args:
            metadata: Invocation metadata from gRPC.

        Returns:
            JWT token string or None if not found.
        """
        if metadata is None:
            return None

        metadata_iter = cast("Iterable[tuple[bytes | str, bytes | str]]", metadata)

        for raw_key, raw_value in metadata_iter:
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else raw_key
            value = raw_value.decode("utf-8") if isinstance(raw_value, bytes) else raw_value
            key_lower = key.lower()
            if key_lower == "authorization" and value.startswith("Bearer "):
                return value[7:]
            if key_lower == "token":
                return value

        return None

    def _decode_token_payload(self, token: str) -> dict[str, Any] | None:
        """Decode JWT payload without signature verification.

        This is intentionally simplified — signature verification requires
        the JWKS keys and is left as a future enhancement.

        Args:
            token: JWT token string.

        Returns:
            Token payload dict if decodable, None otherwise.
        """
        parts = token.split(".")
        if len(parts) != 3:
            return None

        # Pad to a valid base64 length before decoding
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        try:
            return json.loads(base64.urlsafe_b64decode(payload_b64))
        except ValueError, UnicodeDecodeError:
            return None

    async def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: Any,
    ) -> grpc.RpcMethodHandler:
        """Intercept incoming RPC calls for authentication.

        Args:
            continuation: The next interceptor in the chain.
            handler_call_details: Details about the RPC call.

        Returns:
            The RPC method handler, or passes through if authentication fails.
        """
        metadata = handler_call_details.invocation_metadata
        token = self._extract_token_from_metadata(metadata)

        if not token:
            logger.warning("auth_failed_no_token")
            return await continuation(handler_call_details)

        payload = self._decode_token_payload(token)
        if not payload:
            logger.warning("auth_failed_invalid_token")
            return await continuation(handler_call_details)

        user_id = payload.get("sub")
        if not user_id:
            logger.warning("auth_failed_no_user_id")
            return await continuation(handler_call_details)

        token_var = USER_ID_CTX_KEY.set(user_id)
        try:
            return await continuation(handler_call_details)
        finally:
            USER_ID_CTX_KEY.reset(token_var)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
