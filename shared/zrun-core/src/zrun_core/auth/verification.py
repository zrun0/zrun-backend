"""JWT verification utilities for zrun services.

This module provides reusable JWT verification functions that can be used
by both BFF (for verifying Casdoor tokens) and internal services
(for verifying BFF-issued tokens).

Features:
- JWT signature verification using JWKS
- Claims validation (exp, nbf, aud, iss, sub)
- Key ID (kid) matching in JWKS
- Standard error handling
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from zrun_core.errors import AuthenticationError

if TYPE_CHECKING:
    from .protocols import JWKSProviderProtocol

logger = structlog.get_logger()


@dataclass(frozen=True)
class JWTVerificationConfig:
    """Configuration for JWT verification.

    Attributes:
        audience: Expected JWT audience claim (e.g., "zrun-services").
        issuer: Expected JWT issuer claim (e.g., "zrun-bff" or "casdoor").
        algorithms: Allowed JWT algorithms (default: ["RS256"]).
        require_sub: Whether subject claim is required (default: True).
    """

    audience: str
    issuer: str
    algorithms: list[str] | None = None
    require_sub: bool = True


class JWTVerificationError(AuthenticationError):
    """Error raised when JWT verification fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message=message, code="JWT_VERIFICATION_ERROR")


async def verify_jwt_with_jwks(
    token: str,
    jwks_provider: JWKSProviderProtocol,
    config: JWTVerificationConfig,
) -> dict[str, Any]:
    """Verify JWT token using JWKS and return payload.

    This function performs:
    1. JWKS fetching (cached)
    2. JWT header parsing to extract key ID (kid)
    3. RSA key construction from JWKS
    4. JWT signature verification
    5. Claims validation (exp, nbf, aud, iss, sub)

    Args:
        token: JWT token string.
        jwks_provider: JWKS provider instance (Protocol or Class).
        config: Verification configuration.

    Returns:
        Token payload dictionary if valid.

    Raises:
        JWTVerificationError: If verification fails.
    """
    from jose import JWTError, jwt
    from jose.exceptions import ExpiredSignatureError

    algorithms = config.algorithms or ["RS256"]

    try:
        # Ensure JWKS is fetched (uses cache internally)
        await jwks_provider.get_jwks()

        # Get JWT header to find key ID
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")

        if not kid:
            logger.error("jwt_verification_no_kid")
            msg = "JWT header missing 'kid' claim"
            raise JWTVerificationError(msg)

        # Get key by kid using indexed lookup (O(1))
        key = jwks_provider.get_key_by_kid(kid)
        if not key:
            logger.error("jwt_verification_key_not_found", kid=kid)
            msg = f"Key not found in JWKS: {kid}"
            raise JWTVerificationError(msg)

        # Build RSA key dict for jose library
        rsa_key = {
            "kty": key["kty"],
            "kid": key["kid"],
            "use": key.get("use", "sig"),
            "n": key["n"],
            "e": key["e"],
        }

        # Verify and decode token with full validation
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=algorithms,
            audience=config.audience,
            issuer=config.issuer,
        )

        # Validate subject claim if required
        if config.require_sub:
            sub = payload.get("sub")
            if not sub or not isinstance(sub, str):
                logger.error("jwt_verification_no_sub")
                msg = "JWT missing or invalid 'sub' claim"
                raise JWTVerificationError(msg)

        logger.debug("jwt_verification_success", sub=payload.get("sub"))
        return payload

    except ExpiredSignatureError:
        logger.warning("jwt_verification_expired")
        msg = "Token has expired"
        raise JWTVerificationError(msg) from None
    except JWTError as e:
        logger.warning("jwt_verification_error", error=str(e))
        msg = f"JWT verification failed: {e}"
        raise JWTVerificationError(msg) from e
    except JWTVerificationError:
        # Re-raise our custom errors
        raise
    except Exception as e:
        logger.error("jwt_verification_unexpected", error=str(e))
        msg = f"Unexpected error during verification: {e}"
        raise JWTVerificationError(msg) from e
