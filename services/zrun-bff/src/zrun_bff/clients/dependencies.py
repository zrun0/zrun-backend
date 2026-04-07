"""FastAPI dependencies for gRPC clients.

This module provides FastAPI dependency functions for injecting
gRPC clients into route handlers.

Note:
    User context is automatically set by UserContextMiddleware in main.py.
    The client dependencies below rely on the middleware for authentication
    context propagation to gRPC services.

Architecture:
    Request → UserContextMiddleware → set_user_context()
                                        ↓
    Route Handler → Depends(get_sku_client) → BaseSkuClient
                                            ↓
    gRPC Call → build_auth_metadata() → [user_id, token, scopes]
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003

from fastapi import Depends
from grpc.aio import Channel
from structlog import get_logger

from zrun_bff.clients.base import BaseSkuClient, create_sku_client
from zrun_bff.clients.factory import get_client_manager
from zrun_bff.clients.interceptors import get_user_context
from zrun_bff.config import BFFConfig, get_config

logger = get_logger()


async def get_base_channel(
    config: BFFConfig = Depends(get_config),
) -> AsyncGenerator[Channel]:
    """Dependency that provides gRPC channel for Base service.

    Args:
        config: BFF configuration.

    Yields:
        Active gRPC channel for zrun-base service.

    Example:
        ```python
        @router.get("/api/skus/{sku_id}")
        async def get_sku(
            sku_id: int,
            channel: Channel = Depends(get_base_channel),
        ) -> dict[str, Any]:
            client = BaseSkuClient(channel)
            return await client.get_sku(sku_id)
        ```
    """
    manager = get_client_manager()
    channel = await manager.get_base_channel()
    try:
        yield channel
    finally:
        await manager.release_channel(config.base_service_url)


async def get_sku_client(
    channel: Channel = Depends(get_base_channel),
) -> AsyncGenerator[BaseSkuClient]:
    """Dependency that provides Base SKU service client.

    Note:
        User context should be set by UserContextMiddleware before
        this dependency is called. The client will automatically
        use the context for gRPC metadata injection.

    Args:
        channel: gRPC channel injected by get_base_channel.

    Yields:
        Configured BaseSkuClient instance.

    Example:
        ```python
        @router.get("/api/skus/{sku_id}")
        async def get_sku(
            sku_id: int,
            client: BaseSkuClient = Depends(get_sku_client),
        ) -> dict[str, Any]:
            return await client.get_sku(sku_id)
        ```
    """
    client = create_sku_client(channel)

    # Log if user context is available (for debugging)
    user_ctx = get_user_context()
    if user_ctx:
        logger.debug("sku_client_with_context", user_id=user_ctx.get("user_id", "")[:8] + "...")

    try:
        yield client
    finally:
        # Client doesn't own the channel, so no cleanup needed
        pass


# Type alias for commonly used dependencies
BaseChannelDep = Channel
SkuClientDep = BaseSkuClient
