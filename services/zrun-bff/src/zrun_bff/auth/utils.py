"""Casdoor JWT signature verification utilities.

This module provides utilities for verifying Casdoor JWT tokens
using JWKS (JSON Web Key Set) public keys.

Refactored to use zrun_core.auth utilities for consistent
JWT verification across all services.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache

from structlog import get_logger
from zrun_core.auth import (
    JWKSProvider,
    JWKSProviderConfig,
    JWTVerificationConfig,
    JWTVerificationError,
    verify_jwt_with_jwks,
)

from zrun_bff.config import BFFConfig

logger = get_logger()


@lru_cache
def get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    return BFFConfig()


# Global JWKS provider instance
_jwks_provider: JWKSProvider | None = None


def get_jwks_provider() -> JWKSProvider:
    """Get or create global JWKS provider for Casdoor.

    Returns:
        JWKSProvider instance configured for Casdoor.
    """
    global _jwks_provider

    if _jwks_provider is None:
        config = get_config()
        # Build JWKS URL from Casdoor endpoint
        # Example: http://localhost:8080/api/oauth/authorize
        #          -> http://localhost:8080/.well-known/jwks.json
        base_url = config.casdoor_authorization_endpoint.rsplit("/", 2)[0]
        jwks_url = f"{base_url}/.well-known/jwks.json"

        jwks_config = JWKSProviderConfig(
            jwks_url=jwks_url,
            cache_ttl_seconds=300,  # 5 minutes
            timeout_seconds=10,
        )
        _jwks_provider = JWKSProvider(config=jwks_config)

    return _jwks_provider


def verify_casdoor_token(token: str, config: BFFConfig | None = None) -> dict[str, object]:
    """Verify Casdoor JWT token signature using JWKS.

    This function provides a synchronous interface for token verification,
    internally handling async execution using zrun_core.auth utilities.

    Args:
        token: Casdoor JWT access token.
        config: BFF configuration. If None, loads from environment.

    Returns:
        Decoded JWT payload with verified signature.

    Raises:
        ValueError: If token is invalid, expired, or verification fails.
    """
    if config is None:
        config = get_config()

    # Run async verification in sync context
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # We're in an async context with a running loop
            # Run in a thread to avoid blocking
            import threading

            result_container: list[dict[str, object] | None] = [None]
            exception_container: list[Exception | None] = [None]

            def run_in_new_loop() -> None:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result_container[0] = new_loop.run_until_complete(
                        _verify_casdoor_token_async(token, config)
                    )
                except Exception as e:
                    exception_container[0] = e
                finally:
                    new_loop.close()

            thread = threading.Thread(target=run_in_new_loop)
            thread.start()
            thread.join(timeout=10)

            if exception_container[0]:
                raise exception_container[0]
            if result_container[0] is None:
                msg = "Token verification failed"
                raise RuntimeError(msg)

            return result_container[0]

    except RuntimeError:
        pass  # No running loop, create a new one below

    # No running event loop, create and use a new one
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_verify_casdoor_token_async(token, config))
    finally:
        loop.close()


async def _verify_casdoor_token_async(
    token: str,
    config: BFFConfig,
) -> dict[str, object]:
    """Async implementation of Casdoor token verification.

    Uses zrun_core.auth.verify_jwt_with_jwks for consistent
    JWT verification across all services.

    Args:
        token: Casdoor JWT access token.
        config: BFF configuration.

    Returns:
        Decoded JWT payload with verified signature.

    Raises:
        ValueError: If token verification fails.
    """
    provider = get_jwks_provider()

    # Create verification config for Casdoor tokens
    # Note: Casdoor tokens use the client_id as audience
    jwt_config = JWTVerificationConfig(
        audience=config.casdoor_client_id,
        issuer="",  # Casdoor issuer varies, so we don't validate it
        algorithms=["RS256"],
        require_sub=True,
    )

    try:
        payload = await verify_jwt_with_jwks(
            token=token,
            jwks_provider=provider,
            config=jwt_config,
        )
        logger.info("casdoor_token_verified", sub=payload.get("sub"))
        return payload
    except JWTVerificationError as e:
        logger.error("casdoor_token_verification_failed", error=str(e))
        msg = f"Token verification failed: {e}"
        raise ValueError(msg) from e
