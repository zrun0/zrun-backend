"""Token management for access and refresh tokens.

This module provides:
- Token pair generation (access + refresh)
- Refresh token validation and rotation
- Token claim utilities
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from pydantic import BaseModel
from structlog import get_logger

if TYPE_CHECKING:
    from zrun_bff.config import BFFConfig

from zrun_bff.auth.constants import InternalTokenType, TokenType
from zrun_core.auth import generate_token

logger = get_logger()


class TokenPair(BaseModel):
    """Access and refresh token pair.

    Attributes:
        access_token: JWT access token for API authentication.
        refresh_token: JWT refresh token for obtaining new access tokens.
        expires_in: Access token expiration time in seconds.
        token_type: Token type (always "Bearer").
    """

    access_token: str
    refresh_token: str
    expires_in: int
    token_type: TokenType = TokenType.BEARER


class TokenClaims(BaseModel):
    """JWT token claims.

    Attributes:
        sub: Subject (user ID).
        iss: Issuer.
        aud: Audience.
        exp: Expiration time.
        nbf: Not before time.
        iat: Issued at time.
        scope: OAuth scopes.
        token_type: Token type ("access" or "refresh").
    """

    sub: str
    iss: str
    aud: str
    exp: datetime
    nbf: datetime
    iat: datetime
    scope: str
    token_type: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TokenClaims:
        """Create TokenClaims from JWT payload dictionary.

        Args:
            data: JWT payload dictionary.

        Returns:
            TokenClaims instance.
        """
        # Handle timestamp claims
        exp = data["exp"]
        nbf = data["nbf"]
        iat = data["iat"]

        # Convert timestamps to datetime if needed
        if isinstance(exp, (int, float)):
            exp = datetime.fromtimestamp(exp, tz=UTC)
        if isinstance(nbf, (int, float)):
            nbf = datetime.fromtimestamp(nbf, tz=UTC)
        if isinstance(iat, (int, float)):
            iat = datetime.fromtimestamp(iat, tz=UTC)

        return cls(
            sub=data["sub"],
            iss=data["iss"],
            aud=data["aud"],
            exp=exp,
            nbf=nbf,
            iat=iat,
            scope=data.get("scope", ""),
            token_type=data.get("token_type", "access"),
        )


def generate_token_pair(
    config: BFFConfig,
    user_id: str,
    scopes: str = "pda:read pda:write",
) -> TokenPair:
    """Generate access and refresh token pair.

    Args:
        config: BFF configuration.
        user_id: User ID (subject).
        scopes: OAuth scopes for the tokens.

    Returns:
        TokenPair with access and refresh tokens.
    """
    # Generate access token (short-lived)
    access_token = generate_token(
        private_key=config.jwt_private_key,
        issuer=config.jwt_issuer,
        audience=config.jwt_audience,
        subject=user_id,
        expiration_seconds=config.jwt_expiration_seconds,
        key_id=config.jwt_key_id,
        additional_claims={
            "scope": scopes,
            "token_type": InternalTokenType.ACCESS,
        },
    )

    # Generate refresh token (long-lived)
    refresh_token = generate_token(
        private_key=config.jwt_private_key,
        issuer=config.jwt_issuer,
        audience=config.jwt_audience,
        subject=user_id,
        expiration_seconds=config.jwt_refresh_expiration_seconds,
        key_id=config.jwt_key_id,
        additional_claims={
            "scope": scopes,
            "token_type": InternalTokenType.REFRESH,
        },
    )

    logger.info(
        "token_pair_generated",
        sub=user_id,
        access_exp_seconds=config.jwt_expiration_seconds,
        refresh_exp_seconds=config.jwt_refresh_expiration_seconds,
    )

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=config.jwt_expiration_seconds,
    )


def refresh_access_token(
    config: BFFConfig,
    refresh_token: str,
) -> TokenPair:
    """Generate new token pair using refresh token.

    Implements token rotation: the old refresh token is invalidated
    and a new pair is issued.

    Args:
        config: BFF configuration.
        refresh_token: Valid refresh token.

    Returns:
        New TokenPair with fresh access and refresh tokens.

    Raises:
        ValueError: If refresh token is invalid or expired.
    """
    try:
        # Decode and verify refresh token using public key
        payload = jwt.decode(
            refresh_token,
            key=config.jwt_public_key,
            algorithms=["RS256"],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
        )

        claims = TokenClaims.from_dict(payload)

        # Validate token type
        if claims.token_type != InternalTokenType.REFRESH:
            expected = InternalTokenType.REFRESH
            msg = f"Invalid token type: expected '{expected}', got '{claims.token_type}'"
            logger.error("refresh_token_invalid_type", token_type=claims.token_type)
            raise ValueError(msg)

        # Generate new token pair
        logger.info("refresh_token_valid", sub=claims.sub)
        return generate_token_pair(
            config=config,
            user_id=claims.sub,
            scopes=claims.scope,
        )

    except ExpiredSignatureError as e:
        msg = "Refresh token has expired"
        logger.error("refresh_token_expired")
        raise ValueError(msg) from e
    except JWTError as e:
        msg = f"Invalid refresh token: {e}"
        logger.error("refresh_token_invalid", error=str(e))
        raise ValueError(msg) from e
    except KeyError as e:
        msg = f"Refresh token missing required claim: {e}"
        logger.error("refresh_token_missing_claim", claim=str(e))
        raise ValueError(msg) from e


def verify_access_token(
    config: BFFConfig,
    token: str,
) -> TokenClaims:
    """Verify and decode access token.

    Args:
        config: BFF configuration.
        token: Access token to verify.

    Returns:
        TokenClaims with decoded token data.

    Raises:
        ValueError: If token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            key=config.jwt_public_key,
            algorithms=["RS256"],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
        )

        claims = TokenClaims.from_dict(payload)

        # Validate token type
        if claims.token_type != "access":  # noqa: S105
            msg = f"Invalid token type: expected 'access', got '{claims.token_type}'"
            logger.error("access_token_invalid_type", token_type=claims.token_type)
            raise ValueError(msg)

        logger.debug("access_token_valid", sub=claims.sub)
        return claims

    except ExpiredSignatureError as e:
        msg = "Access token has expired"
        logger.error("access_token_expired")
        raise ValueError(msg) from e
    except JWTError as e:
        msg = f"Invalid access token: {e}"
        logger.error("access_token_invalid", error=str(e))
        raise ValueError(msg) from e
    except KeyError as e:
        msg = f"Access token missing required claim: {e}"
        logger.error("access_token_missing_claim", claim=str(e))
        raise ValueError(msg) from e
