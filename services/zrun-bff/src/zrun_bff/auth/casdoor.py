"""Casdoor OAuth2 integration for JWT token verification.

This module provides utilities for verifying Casdoor JWT tokens
using JWKS (JSON Web Key Set) public keys.

Architecture:
    Frontend -> Casdoor (OAuth2) -> BFF (verify Casdoor token) -> Internal JWT

Uses zrun_core.auth utilities for consistent JWT verification across all services.
"""

from __future__ import annotations

from hashlib import sha256
from weakref import WeakValueDictionary

from structlog import get_logger
from zrun_core.auth import (
    JWKSProvider,
    JWKSProviderConfig,
    JWTVerificationConfig,
    JWTVerificationError,
    verify_jwt_with_jwks,
)

from zrun_bff.config import BFFConfig, get_config

logger = get_logger()


# Global JWKS provider cache keyed by config hash
_jwks_providers: WeakValueDictionary[str, JWKSProvider] = WeakValueDictionary()


def _config_hash(config: BFFConfig) -> str:
    """Generate hash for config caching.

    Args:
        config: BFF configuration.

    Returns:
        SHA256 hash of config key fields.
    """
    key = f"{config.casdoor_authorization_endpoint}:{config.casdoor_client_id}"
    return sha256(key.encode()).hexdigest()


def get_jwks_provider(config: BFFConfig | None = None) -> JWKSProvider:
    """Get or create JWKS provider for Casdoor.

    Args:
        config: BFF configuration. If None, uses cached config from get_config().

    Returns:
        JWKSProvider instance configured for Casdoor.
    """
    if config is None:
        config = get_config()

    cache_key = _config_hash(config)
    provider = _jwks_providers.get(cache_key)

    if provider is None:
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
        provider = JWKSProvider(config=jwks_config)
        _jwks_providers[cache_key] = provider

    return provider


async def verify_casdoor_token_async(
    token: str,
    config: BFFConfig | None = None,
) -> dict[str, object]:
    """Verify Casdoor JWT token signature using JWKS.

    Uses zrun_core.auth.verify_jwt_with_jwks for consistent
    JWT verification across all services.

    Args:
        token: Casdoor JWT access token.
        config: BFF configuration. If None, uses cached config from get_config().

    Returns:
        Decoded JWT payload with verified signature.

    Raises:
        ValueError: If token is invalid, expired, or verification fails.
    """
    if config is None:
        config = get_config()

    provider = get_jwks_provider(config)

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


__all__ = [
    "get_jwks_provider",
    "verify_casdoor_token_async",
]
