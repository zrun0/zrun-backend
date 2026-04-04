"""FastAPI dependencies for gRPC clients.

This module provides FastAPI dependency functions for injecting
gRPC clients into route handlers.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator  # noqa: TC003
from functools import lru_cache

from fastapi import Depends
from grpc.aio import Channel
from structlog import get_logger

from zrun_bff.clients.base import BaseSkuClient, create_sku_client
from zrun_bff.clients.factory import get_client_manager
from zrun_bff.config import BFFConfig

logger = get_logger()


@lru_cache
def _get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    return BFFConfig()


async def get_base_channel() -> AsyncGenerator[Channel]:
    """Dependency that provides gRPC channel for Base service.

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
    config = _get_config()
    channel = await manager.get_base_channel()
    try:
        yield channel
    finally:
        await manager.release_channel(config.base_service_url)


async def get_sku_client(
    channel: Channel = Depends(get_base_channel),
) -> AsyncGenerator[BaseSkuClient]:
    """Dependency that provides Base SKU service client.

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
    try:
        yield client
    finally:
        # Client doesn't own the channel, so no cleanup needed
        pass


# Type alias for commonly used dependencies
BaseChannelDep = Channel
SkuClientDep = BaseSkuClient
