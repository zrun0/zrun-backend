"""Authentication interceptor for gRPC services.

This interceptor validates JWT tokens issued by the BFF service using JWKS.
Following Architecture Pattern B: BFF re-issues internal JWTs after validating
Casdoor tokens, keeping internal services decoupled from external dependencies.
"""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, cast

import grpc
import structlog
from grpc.aio import ServerInterceptor

if TYPE_CHECKING:
    from .protocols import JWKSProviderProtocol
    from collections.abc import Callable, Iterable

from .jwks import JWKSProvider, JWKSProviderConfig
from .verification import JWTVerificationConfig, JWTVerificationError, verify_jwt_with_jwks

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
    - Dependency injection support for testing

    Architecture Pattern B:
        Frontend → BFF (OAuth2 with Casdoor) → Internal JWT
        Internal Services → Validate BFF JWT (using BFF JWKS)

    Example:
        ```python
        # With default JWKS provider
        interceptor = AuthInterceptor(
            jwks_url="https://bff.example.com/.well-known/jwks.json",
            audience="zrun-services",
            issuer="zrun-bff",
        )

        # With custom JWKS provider (for testing)
        mock_provider = MockJWKSProvider()
        interceptor = AuthInterceptor(
            jwks_provider=mock_provider,
            audience="zrun-services",
            issuer="zrun-bff",
        )
        ```
    """

    def __init__(
        self,
        jwks_url: str | None = None,
        audience: str = "",
        issuer: str | None = None,
        cache_ttl: int = 300,
        jwks_provider: JWKSProviderProtocol | None = None,
    ) -> None:
        """Initialize the authentication interceptor.

        Args:
            jwks_url: URL to fetch JWKS from (BFF endpoint, not Casdoor).
                     Required if jwks_provider is not provided.
            audience: Expected JWT audience claim (e.g., "zrun-services").
            issuer: Expected JWT issuer claim (e.g., "zrun-bff").
            cache_ttl: Cache TTL for JWKS in seconds. Only used if jwks_provider is not provided.
            jwks_provider: Optional JWKS provider for dependency injection.
                          If provided, jwks_url and cache_ttl are ignored.

        Raises:
            ValueError: If neither jwks_url nor jwks_provider is provided.
        """
        if jwks_provider is None:
            if not jwks_url:
                msg = "Either jwks_url or jwks_provider must be provided"
                raise ValueError(msg)
            # Create JWKS provider
            jwks_config = JWKSProviderConfig(
                jwks_url=jwks_url,
                cache_ttl_seconds=cache_ttl,
                timeout_seconds=10,
            )
            self._jwks_provider = JWKSProvider(config=jwks_config)
            self._owned_provider = True
        else:
            self._jwks_provider = jwks_provider
            self._owned_provider = False

        # Create JWT verification config
        self._jwt_config = JWTVerificationConfig(
            audience=audience,
            issuer=issuer or "",
            algorithms=["RS256"],
            require_sub=True,
        )

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
        try:
            payload = await verify_jwt_with_jwks(
                token=token,
                jwks_provider=self._jwks_provider,
                config=self._jwt_config,
            )
            logger.debug("auth_success", user_id=payload.get("sub"))
            return payload
        except JWTVerificationError:
            logger.warning("auth_failed_verification")
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
        """Close the JWKS provider.

        Should be called when shutting down the service.
        Only closes the provider if we own it (i.e., it was created by this interceptor).
        """
        if self._owned_provider:
            await self._jwks_provider.close()

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
