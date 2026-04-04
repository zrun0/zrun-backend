"""gRPC client utilities for authentication.

This module provides utilities for injecting authentication
and user context into gRPC calls made by the BFF.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

from structlog import get_logger

logger = get_logger()


# Type alias for gRPC metadata
Metadata = Sequence[tuple[str, str]]


# Context variable for storing current user information
USER_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("user_context")


def set_user_context(
    user_id: str,
    token: str,
    scopes: list[str] | None = None,
) -> Token[dict[str, Any]]:
    """Set user context for current request.

    This should be called after authentication to store user information
    for use in gRPC calls.

    Args:
        user_id: User ID from JWT token.
        token: JWT access token.
        scopes: List of OAuth scopes granted to the user.

    Returns:
        ContextVar token for later reset.
    """
    return USER_CONTEXT.set(
        {
            "user_id": user_id,
            "token": token,
            "scopes": scopes or [],
        }
    )


def get_user_context() -> dict[str, Any]:
    """Get user context for current request.

    Returns:
        Dictionary containing user_id, token, and scopes.
    """
    return USER_CONTEXT.get({})


@contextmanager
def user_context_scope(user_id: str, token: str, scopes: list[str] | None = None) -> Any:
    """Context manager for setting user context.

    Args:
        user_id: User ID from JWT token.
        token: JWT access token.
        scopes: List of OAuth scopes granted to the user.

    Yields:
        User context dictionary.

    Example:
        ```python
        with user_context_scope(user_id, token) as ctx:
            # gRPC calls made here will have user context
            stub = MyServiceStub(channel)
            response = await stub.MyMethod(request)
        ```
    """
    ctx_token = USER_CONTEXT.set({"user_id": user_id, "token": token, "scopes": scopes or []})
    try:
        yield get_user_context()
    finally:
        USER_CONTEXT.reset(ctx_token)


def build_auth_metadata() -> Metadata:
    """Build authentication metadata from current user context.

    Returns:
        List of metadata tuples for gRPC call.

    Example:
        ```python
        metadata = build_auth_metadata()
        response = await stub.MyMethod(request, metadata=metadata)
        ```
    """
    user_ctx = get_user_context()
    metadata: list[tuple[str, str]] = []

    # Add user ID to metadata
    user_id = user_ctx.get("user_id")
    if isinstance(user_id, str):
        metadata.append(("x-user-id", user_id))
        logger.debug("injecting_user_id", user_id=user_id)

    # Add authorization token to metadata
    token = user_ctx.get("token")
    if isinstance(token, str):
        metadata.append(("authorization", f"Bearer {token}"))
        logger.debug("injecting_auth_token")

    # Add scopes to metadata
    scopes = user_ctx.get("scopes", [])
    if isinstance(scopes, list) and scopes:
        metadata.append(("x-scopes", ",".join(scopes)))

    return metadata


async def call_with_auth(
    stub_method: Any,
    request: Any,
) -> Any:
    """Call a gRPC method with authentication metadata.

    This is a convenience wrapper that automatically adds authentication
    metadata from the current user context.

    Args:
        stub_method: The gRPC stub method to call.
        request: The request message.

    Returns:
        The response from the gRPC call.

    Example:
        ```python
        stub = MyServiceStub(channel)
        response = await call_with_auth(stub.MyMethod, request)
        ```
    """
    metadata = build_auth_metadata()
    return await stub_method(request, metadata=metadata)
