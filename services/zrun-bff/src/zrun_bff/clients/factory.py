"""gRPC client factory for BFF service.

This module provides a factory for creating gRPC client instances
to communicate with downstream microservices.

Refactored to use zrun_core.grpc utilities for consistent
channel management across all services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from structlog import get_logger

if TYPE_CHECKING:
    import grpc.aio

from zrun_bff.config import BFFConfig, get_config
from zrun_core.grpc import GrpcClientManager as CoreGrpcClientManager
from zrun_core.grpc import GrpcChannelConfig

logger = get_logger()


class GrpcClientManager:
    """Manager for gRPC client connections to downstream services.

    This manager wraps zrun_core.grpc.GrpcClientManager and provides
    BFF-specific convenience methods for accessing service channels.

    Example:
        ```python
        manager = GrpcClientManager()
        base_channel = await manager.get_base_channel()
        ```
    """

    def __init__(self) -> None:
        """Initialize the gRPC client manager."""
        # Create core manager with standard configuration
        config = GrpcChannelConfig(
            max_receive_message_length=128 * 1024 * 1024,  # 128MB
            max_send_message_length=128 * 1024 * 1024,  # 128MB
            keepalive_time_ms=30000,  # 30s
            keepalive_timeout_ms=5000,  # 5s
            keepalive_permit_without_calls=True,
        )
        self._core_manager = CoreGrpcClientManager(config)

    async def get_base_channel(self) -> grpc.aio.Channel:
        """Get gRPC channel for Base service.

        Returns:
            Active gRPC channel for zrun-base service.
        """
        config = get_config()
        return await self._core_manager.get_channel(config.base_service_url)

    async def get_ops_channel(self) -> grpc.aio.Channel:
        """Get gRPC channel for Ops service.

        Returns:
            Active gRPC channel for zrun-ops service.
        """
        config = get_config()
        return await self._core_manager.get_channel(config.ops_service_url)

    async def get_stock_channel(self) -> grpc.aio.Channel:
        """Get gRPC channel for Stock service.

        Returns:
            Active gRPC channel for zrun-stock service.
        """
        config = get_config()
        return await self._core_manager.get_channel(config.stock_service_url)

    async def release_channel(self, target: str) -> None:
        """Release a gRPC channel back to the pool.

        Args:
            target: Target address of the channel to release.
        """
        await self._core_manager.release_channel(target)

    async def close_all(self) -> None:
        """Close all gRPC channels."""
        await self._core_manager.close_all()


# Global client manager instance
_client_manager: GrpcClientManager | None = None


def get_client_manager() -> GrpcClientManager:
    """Get or create global gRPC client manager.

    Returns:
        Global GrpcClientManager instance.
    """
    global _client_manager
    if _client_manager is None:
        _client_manager = GrpcClientManager()
    return _client_manager
