"""gRPC client factory and manager for zrun services.

This module provides reusable gRPC client utilities for inter-service communication,
including channel pooling, connection management, and configuration standardization.

Features:
- Channel pooling with reference counting
- Keepalive settings for long-lived connections
- Message size limits configuration
- Automatic channel cleanup on shutdown
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import grpc
import structlog


logger = structlog.get_logger()


@dataclass(frozen=True)
class GrpcChannelConfig:
    """Configuration for gRPC channel creation.

    Attributes:
        max_receive_message_length: Max message size in bytes (default: 128MB).
        max_send_message_length: Max send message size in bytes (default: 128MB).
        keepalive_time_ms: Keepalive ping interval in ms (default: 30s).
        keepalive_timeout_ms: Keepalive timeout in ms (default: 5s).
        keepalive_permit_without_calls: Allow keepalive without calls (default: False).
    """

    max_receive_message_length: int = 128 * 1024 * 1024  # 128MB
    max_send_message_length: int = 128 * 1024 * 1024  # 128MB
    keepalive_time_ms: int = 30000  # 30 seconds
    keepalive_timeout_ms: int = 5000  # 5 seconds
    keepalive_permit_without_calls: bool = False

    def to_options(self) -> list[tuple[str, Any]]:
        """Convert config to gRPC channel options.

        Returns:
            List of (name, value) tuples for grpc.insecure_channel.
        """
        return [
            ("grpc.max_receive_message_length", self.max_receive_message_length),
            ("grpc.max_send_message_length", self.max_send_message_length),
            ("grpc.keepalive_time_ms", self.keepalive_time_ms),
            ("grpc.keepalive_timeout_ms", self.keepalive_timeout_ms),
            ("grpc.keepalive_permit_without_calls", self.keepalive_permit_without_calls),
        ]


class GrpcClientFactory:
    """Factory for creating gRPC channels with standard configuration.

    This factory creates gRPC channels with consistent configuration
    across all services, including message size limits and keepalive settings.

    Example:
        >>> factory = GrpcClientFactory(GrpcChannelConfig())
        >>> channel = factory.create_channel("localhost:50051")
        >>> stub = MyServiceStub(channel)
    """

    def __init__(self, config: GrpcChannelConfig | None = None) -> None:
        """Initialize the gRPC client factory.

        Args:
            config: Channel configuration. If None, uses defaults.
        """
        self._config = config or GrpcChannelConfig()

    def create_channel(self, target: str) -> grpc.aio.Channel:
        """Create a new gRPC channel with standard configuration.

        Args:
            target: Target address (e.g., "localhost:50051").

        Returns:
            Configured gRPC aio channel.
        """
        options = self._config.to_options()
        logger.debug("grpc_channel_created", target=target, options_count=len(options))
        return grpc.insecure_channel(target, options)

    def create_secure_channel(
        self,
        target: str,
        credentials: grpc.ChannelCredentials,
    ) -> grpc.aio.Channel:
        """Create a new secure gRPC channel with standard configuration.

        Args:
            target: Target address (e.g., "example.com:443").
            credentials: Channel credentials for TLS.

        Returns:
            Configured gRPC aio channel.
        """
        options = self._config.to_options()
        logger.debug("grpc_secure_channel_created", target=target, options_count=len(options))
        return grpc.secure_channel(target, credentials, options)


class GrpcClientManager:
    """Manager for pooled gRPC channels with reference counting.

    This manager maintains a pool of gRPC channels keyed by target address,
    with automatic cleanup when reference count reaches zero.

    Example:
        >>> manager = GrpcClientManager()
        >>> async with manager.get_channel("localhost:50051") as channel:
        ...     stub = MyServiceStub(channel)
        ...     response = await stub.MyMethod(request)
    """

    def __init__(
        self,
        config: GrpcChannelConfig | None = None,
    ) -> None:
        """Initialize the gRPC client manager.

        Args:
            config: Channel configuration. If None, uses defaults.
        """
        self._config = config or GrpcChannelConfig()
        self._channels: dict[str, grpc.aio.Channel] = {}
        self._ref_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._factory = GrpcClientFactory(self._config)

    async def get_channel(self, target: str) -> grpc.aio.Channel:
        """Get a gRPC channel from the pool or create a new one.

        Increments reference count for the target.

        Args:
            target: Target address (e.g., "localhost:50051").

        Returns:
            gRPC channel (may be newly created or reused).
        """
        async with self._lock:
            if target in self._channels:
                self._ref_counts[target] += 1
                logger.debug(
                    "grpc_channel_reused",
                    target=target,
                    ref_count=self._ref_counts[target],
                )
                return self._channels[target]

            # Create new channel
            channel = self._factory.create_channel(target)
            self._channels[target] = channel
            self._ref_counts[target] = 1
            logger.info("grpc_channel_created", target=target)
            return channel

    async def release_channel(self, target: str) -> None:
        """Release a gRPC channel back to the pool.

        Decrements reference count and closes channel if count reaches zero.

        Args:
            target: Target address of the channel to release.
        """
        async with self._lock:
            if target not in self._channels:
                logger.warning("grpc_channel_release_not_found", target=target)
                return

            self._ref_counts[target] -= 1
            logger.debug(
                "grpc_channel_released",
                target=target,
                ref_count=self._ref_counts[target],
            )

            if self._ref_counts[target] <= 0:
                # Close and remove channel
                channel = self._channels.pop(target)
                self._ref_counts.pop(target)
                await channel.close()
                logger.info("grpc_channel_closed", target=target)

    async def close_all(self) -> None:
        """Close all managed channels.

        Should be called when shutting down the service.
        """
        async with self._lock:
            # Close all channels (grpc.aio.Channel.close() is synchronous)
            for channel in self._channels.values():
                channel.close()  # type: ignore[unused-awaitable]  # close() is synchronous
            self._channels.clear()
            self._ref_counts.clear()
            logger.info("grpc_all_channels_closed")


async def get_client_manager(
    config: GrpcChannelConfig | None = None,
) -> GrpcClientManager:
    """Get or create a global gRPC client manager.

    This function provides a singleton pattern for accessing
    the gRPC client manager across the application.

    Args:
        config: Optional channel configuration.

    Returns:
        Global or new gRPC client manager.
    """
    # For now, return a new instance each time
    # In the future, this could be a singleton
    return GrpcClientManager(config)
