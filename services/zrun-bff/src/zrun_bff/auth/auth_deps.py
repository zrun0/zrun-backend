"""FastAPI Security dependencies for JWT authentication.

Provides dependency injection functions for protecting API endpoints
with JWT authentication and scope-based authorization.

Scope Validation Modes:
    - OR mode (default): User needs at least one of the required scopes
    - AND mode: User needs all of the required scopes

Usage:
    # OR mode - user needs pda:read OR pda:write
    @app.get("/api/pda/items")
    async def list_items(
        user: dict = Depends(require_any(Scope.PDA_READ, Scope.PDA_WRITE)),
    ):
        ...

    # AND mode - user needs both pda:read AND pda:write
    @app.post("/api/pda/items")
    async def create_item(
        user: dict = Depends(require_all(Scope.PDA_READ, Scope.PDA_WRITE)),
    ):
        ...

    # Backward compatible - single scope (OR mode)
    @app.get("/api/pda/items")
    async def list_items(
        user: dict = Depends(require_scope(Scope.PDA_READ)),
    ):
        ...
"""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from structlog import get_logger

from zrun_bff.auth.constants import Scope
from zrun_bff.auth.verification import verify_jwt_with_config
from zrun_bff.config import BFFConfig, get_config

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger()

security = HTTPBearer(auto_error=False)


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
        payload = verify_jwt_with_config(token, config)
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

    This function uses OR mode by default: user needs at least one
    of the required scopes. For AND mode (user needs all scopes),
    use require_all() instead.

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
    if not required_scopes:
        msg = "At least one scope must be specified"
        raise ValueError(msg)

    # Backward compatibility: single scope or multiple with OR logic
    return require_any(*required_scopes)


def require_any(
    *required_scopes: Scope,
) -> Callable[[dict], typing.Coroutine[typing.Any, typing.Any, dict]]:
    """Create a dependency that requires at least one of the specified scopes.

    User needs to have at least one scope from the required list.

    Args:
        *required_scopes: One or more required scopes.

    Returns:
        Dependency function that validates scopes (OR mode).

    Example:
        @app.get("/api/pda/items")
        async def list_items(
            user: dict = Depends(require_any(Scope.PDA_READ, Scope.PDA_WRITE)),
        ):
            ...
    """
    if not required_scopes:
        msg = "At least one scope must be specified"
        raise ValueError(msg)

    async def check_scope_any(
        user: dict = Depends(get_current_user),
    ) -> dict:
        """Check if user has at least one required scope."""
        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        # Check if user has at least one required scope (OR mode)
        if not any(s.value in user_scopes for s in required_scopes):
            logger.warning(
                "auth_insufficient_scope",
                mode="OR",
                required=[s.value for s in required_scopes],
                user_scopes=user_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        logger.debug(
            "auth_scope_granted",
            mode="OR",
            required=[s.value for s in required_scopes],
        )
        return user

    return check_scope_any


def require_all(
    *required_scopes: Scope,
) -> Callable[[dict], typing.Coroutine[typing.Any, typing.Any, dict]]:
    """Create a dependency that requires all of the specified scopes.

    User needs to have all scopes from the required list.

    Args:
        *required_scopes: One or more required scopes.

    Returns:
        Dependency function that validates scopes (AND mode).

    Example:
        @app.post("/api/pda/items")
        async def create_item(
            user: dict = Depends(require_all(Scope.PDA_READ, Scope.PDA_WRITE)),
        ):
            ...
    """
    if not required_scopes:
        msg = "At least one scope must be specified"
        raise ValueError(msg)

    async def check_scope_all(
        user: dict = Depends(get_current_user),
    ) -> dict:
        """Check if user has all required scopes."""
        token_scopes = user.get("scope", "")
        user_scopes = token_scopes.split() if isinstance(token_scopes, str) else []

        # Check if user has all required scopes (AND mode)
        missing = [s.value for s in required_scopes if s.value not in user_scopes]
        if missing:
            logger.warning(
                "auth_insufficient_scope",
                mode="AND",
                required=[s.value for s in required_scopes],
                missing=missing,
                user_scopes=user_scopes,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Missing scopes: {', '.join(missing)}",
            )

        logger.debug(
            "auth_scope_granted",
            mode="AND",
            required=[s.value for s in required_scopes],
        )
        return user

    return check_scope_all


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
