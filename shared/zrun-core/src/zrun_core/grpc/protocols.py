"""Protocol interfaces for gRPC client management.

This module defines Protocol interfaces for gRPC client components,
enabling dependency injection and improved testability.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import grpc.aio


class GrpcChannelFactoryProtocol(Protocol):
    """Protocol for gRPC channel factories.

    A channel factory is responsible for creating gRPC channels with
    standard configuration.

    Implementations can use different strategies:
    - Insecure channel for local development
    - Secure channel with TLS for production
    - Mock channel for testing
    """

    def create_channel(self, target: str) -> grpc.aio.Channel:
        """Create a new gRPC channel.

        Args:
            target: Target address (e.g., "localhost:50051").

        Returns:
            Configured gRPC aio channel.
        """
        ...

    def create_secure_channel(
        self,
        target: str,
        credentials: grpc.ChannelCredentials,
    ) -> grpc.aio.Channel:
        """Create a new secure gRPC channel.

        Args:
            target: Target address (e.g., "example.com:443").
            credentials: Channel credentials for TLS.

        Returns:
            Configured gRPC aio channel.
        """
        ...


class GrpcClientManagerProtocol(Protocol):
    """Protocol for gRPC client managers.

    A client manager is responsible for managing a pool of gRPC channels
    with reference counting and automatic cleanup.

    Implementations can use different strategies:
    - In-memory pool for single-instance services
    - Distributed pool for multi-instance deployments
    - Mock manager for testing
    """

    async def get_channel(self, target: str) -> grpc.aio.Channel:
        """Get a gRPC channel from the pool or create a new one.

        Increments reference count for the target.

        Args:
            target: Target address (e.g., "localhost:50051").

        Returns:
            gRPC channel (may be newly created or reused).
        """
        ...

    async def release_channel(self, target: str) -> None:
        """Release a gRPC channel back to the pool.

        Decrements reference count and closes channel if count reaches zero.

        Args:
            target: Target address of the channel to release.
        """
        ...

    async def close_all(self) -> None:
        """Close all managed channels.

        Should be called when shutting down the service.
        """
        ...
