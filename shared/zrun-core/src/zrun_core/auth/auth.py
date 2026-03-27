"""Authentication interceptor for gRPC services.

This interceptor validates JWT tokens issued by the BFF service using JWKS.
Following Architecture Pattern B: BFF re-issues internal JWTs after validating
Casdoor tokens, keeping internal services decoupled from external dependencies.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, cast

import grpc
import httpx
import structlog
from cachetools import TTLCache
from grpc.aio import ServerInterceptor

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

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


class AuthInterceptor(ServerInterceptor):
    """gRPC interceptor for JWT authentication.

    This interceptor validates JWT tokens using JWKS (JSON Web Key Set)
    from the BFF service, which re-issues tokens after Casdoor validation.

    Features:
    - JWKS caching with configurable TTL
    - User ID extraction and propagation via contextvars
    - Proper JWT signature verification
    - Claims validation (exp, nbf, aud, iss)
    - Request abortion on authentication failure

    Architecture Pattern B:
        Frontend → BFF (OAuth2 with Casdoor) → Internal JWT
        Internal Services → Validate BFF JWT (using BFF JWKS)
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
            jwks_url: URL to fetch JWKS from (BFF endpoint, not Casdoor).
            audience: Expected JWT audience claim (e.g., "zrun-services").
            issuer: Expected JWT issuer claim (e.g., "zrun-bff").
            cache_ttl: Cache TTL for JWKS in seconds.
        """
        self._jwks_url = jwks_url
        self._audience = audience
        self._issuer = issuer
        self._cache: TTLCache[str, dict[str, Any]] = TTLCache(maxsize=10, ttl=cache_ttl)
        self._client = httpx.AsyncClient(timeout=10.0)

    async def _fetch_jwks(self) -> dict[str, Any]:
        """Fetch JWKS from the BFF service.

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

    def _extract_token(self, metadata: Any) -> str | None:
        """Extract JWT token from gRPC metadata.

        Args:
            metadata: Invocation metadata from gRPC.

        Returns:
            JWT token string or None if not found.
        """
        if metadata is None:
            return None

        metadata_iter = cast("Iterable[tuple[bytes | str, bytes | str]]", metadata)
        metadata_dict = {
            _decode_metadata_key(k): _decode_metadata_value(v) for k, v in metadata_iter
        }

        # Single pass: check both Authorization and Token headers
        for key, value in metadata_dict.items():
            key_lower = key.lower()
            if key_lower == "authorization" and value.startswith("Bearer "):
                return value[7:]
            if key_lower == "token":
                return value

        return None

    async def _validate_token(self, token: str) -> dict[str, Any] | None:
        """Validate JWT token using BFF JWKS and return payload.

        This method performs proper JWT signature verification and validates
        the token's claims (exp, nbf, aud, iss).

        Args:
            token: JWT token string issued by BFF.

        Returns:
            Token payload if valid, None if validation fails.
        """
        from jose import JWTError, jwt
        from jose.exceptions import ExpiredSignatureError

        try:
            # Get JWKS from BFF
            jwks = await self._get_jwks()

            # Get JWT header to find key ID
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")

            if not kid:
                logger.error("auth_failed_no_kid")
                return None

            # Find matching key in JWKS
            rsa_key: dict[str, Any] | None = None
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key.get("use", "sig"),
                        "n": key["n"],
                        "e": key["e"],
                    }
                    break

            if not rsa_key:
                logger.error("auth_failed_no_key", kid=kid)
                return None

            # Verify and decode token with full validation
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )

            logger.debug("auth_success", user_id=payload.get("sub"))
            return payload

        except ExpiredSignatureError:
            logger.warning("auth_failed_token_expired")
            return None
        except JWTError as e:
            logger.warning("auth_failed_jwt_error", error=str(e))
            return None
        except Exception as e:
            logger.error("auth_failed_unexpected", error=str(e))
            return None

    async def intercept_service(
        self,
        continuation: Callable[..., Any],
        handler_call_details: Any,
    ) -> grpc.RpcMethodHandler:
        """Intercept incoming RPC calls for authentication.

        Validates JWT tokens and aborts the call if authentication fails.
        Validated user ID is propagated via context variables.

        Args:
            continuation: The next interceptor in the chain.
            handler_call_details: Details about the RPC call.

        Returns:
            The RPC method handler or aborts with UNAUTHENTICATED status.
        """
        # Extract token from metadata
        metadata = handler_call_details.invocation_metadata
        token = self._extract_token(metadata)

        if not token:
            logger.warning("auth_failed_no_token")
            # Abort with UNAUTHENTICATED status (secure by default)
            await handler_call_details.invocation_metadata.__class__._abort(
                handler_call_details,
                grpc.StatusCode.UNAUTHENTICATED,
                "Missing authentication token",
            )
            return continuation(handler_call_details)

        # Validate token
        payload = await self._validate_token(token)
        if not payload:
            logger.warning("auth_failed_invalid_token")
            await handler_call_details.invocation_metadata.__class__._abort(
                handler_call_details,
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid or expired token",
            )
            return continuation(handler_call_details)

        # Extract user ID
        user_id = payload.get("sub")
        if not user_id:
            logger.warning("auth_failed_no_user_id")
            await handler_call_details.invocation_metadata.__class__._abort(
                handler_call_details,
                grpc.StatusCode.UNAUTHENTICATED,
                "Token missing subject claim",
            )
            return continuation(handler_call_details)

        # Set user ID in context
        token_var = USER_ID_CTX_KEY.set(user_id)

        try:
            return await continuation(handler_call_details)
        finally:
            USER_ID_CTX_KEY.reset(token_var)

    async def close(self) -> None:
        """Close the HTTP client.

        Should be called when shutting down the service.
        """
        await self._client.aclose()

    async def __aenter__(self) -> AuthInterceptor:
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
