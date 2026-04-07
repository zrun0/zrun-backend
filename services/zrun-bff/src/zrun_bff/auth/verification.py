"""Shared JWT verification utilities for BFF auth module.

This module provides common JWT verification functions used across
dependencies, middleware, and tokens modules.
"""

from __future__ import annotations

from jose import JWTError, jwt

from zrun_bff.config import BFFConfig
from zrun_core.auth import get_public_key_pem
from structlog import get_logger

logger = get_logger()


def verify_jwt_with_config(
    token: str,
    config: BFFConfig,
) -> dict[str, object]:
    """Verify JWT token using BFF configuration.

    This is a shared verification function that extracts the public key
    from the private key and verifies the token signature.

    Args:
        token: JWT token string.
        config: BFF configuration with JWT settings.

    Returns:
        Decoded JWT payload.

    Raises:
        JWTError: If token is invalid or expired.
    """
    public_key_pem = get_public_key_pem(config.jwt_private_key)

    payload = jwt.decode(
        token=token,
        key=public_key_pem,
        algorithms=["RS256"],
        audience=config.jwt_audience,
        issuer=config.jwt_issuer,
    )

    return payload


__all__ = [
    "verify_jwt_with_config",
]
