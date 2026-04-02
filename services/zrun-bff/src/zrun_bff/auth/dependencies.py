"""FastAPI Security dependencies for JWT authentication.

Provides dependency injection functions for protecting API endpoints
with JWT authentication and scope-based authorization.
"""

from __future__ import annotations

import enum
import typing
from functools import lru_cache
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from structlog import get_logger

from zrun_bff.config import BFFConfig

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger()

security = HTTPBearer(auto_error=False)


class Scope(enum.StrEnum):
    """OAuth2 scope definitions for fine-grained access control.

    Scopes are included in JWT tokens and checked by require_scope().
    """

    PDA_READ = "pda:read"
    PDA_WRITE = "pda:write"
    WEB_ADMIN = "web:admin"
    WEB_READ = "web:read"
    MINI_READ = "mini:read"
    ADMIN_ALL = "admin:all"


@lru_cache
def get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    return BFFConfig()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security)] = None,
    config: BFFConfig = Depends(get_config),
) -> dict:
    """Extract and validate JWT token from Authorization header.

    Args:
        credentials: HTTP Authorization header with Bearer token.
        config: BFF configuration.

    Returns:
        Decoded JWT payload with user claims.

    Raises:
        HTTPException: If token is missing or invalid.
    """
    if credentials is None:
        logger.warning("auth_missing_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Validate token using public key (extracted from private key)
        # In production, internal services should use JWKS endpoint
        # This is simplified for BFF-to-internal-service communication
        from zrun_bff.jwt import get_public_key_pem

        public_key_pem = get_public_key_pem(config.jwt_private_key)

        payload = jwt.decode(
            token=token,
            key=public_key_pem,
            algorithms=["RS256"],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
        )

        logger.debug("auth_success", sub=payload.get("sub"))
        return payload

    except JWTError as e:
        logger.warning("auth_invalid_token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_scope(
    *required_scopes: Scope,
) -> Callable[[dict], typing.Coroutine[typing.Any, typing.Any, dict]]:
    """Create a dependency that requires specific OAuth2 scopes.

    Args:
        *required_scopes: One or more required scopes (user needs at least one).

    Returns:
        Dependency function that validates scopes.

    Example:
        @app.get("/api/pda/inbound")
        async def pda_inbound(
            user: dict = Depends(require_scope(Scope.PDA_WRITE)),
        ):
            ...
    """

    async def check_scope(
        user: dict = Depends(get_current_user),
    ) -> dict:
        """Check if user has required scope."""
        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        # Check if user has at least one required scope
        if not any(s.value in user_scopes for s in required_scopes):
            logger.warning(
                "auth_insufficient_scope",
                required=[s.value for s in required_scopes],
                user_scopes=user_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return user

    return check_scope


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(security)] = None,
    config: BFFConfig = Depends(get_config),
) -> dict | None:
    """Optional authentication - returns user if token provided, None otherwise.

    Useful for endpoints that work with or without authentication.

    Args:
        credentials: HTTP Authorization header (optional).
        config: BFF configuration.

    Returns:
        Decoded JWT payload if token is valid, None otherwise.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials, config)
    except HTTPException:
        return None
