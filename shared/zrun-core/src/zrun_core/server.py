"""Base gRPC server implementation."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

import grpc.aio
import structlog

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from grpc.aio import Server

    from zrun_core.config import ServiceConfig


logger = structlog.get_logger()


class BaseGrpcServer:
    """Base gRPC server with lifecycle management.

    This class provides a production-ready gRPC server with:
    - Graceful shutdown on SIGTERM/SIGINT
    - Interceptor chaining support
    - Lifecycle logging
    - Configurable worker threads
    """

    def __init__(
        self,
        port: int,
        interceptors: list[grpc.aio.ServerInterceptor],
        max_workers: int = 10,
        service_config: ServiceConfig | None = None,
    ) -> None:
        """Initialize the server.

        Args:
            port: Port to listen on.
            interceptors: List of server interceptors.
            max_workers: Maximum number of worker threads.
            service_config: Optional service configuration.
        """
        self._port = port
        self._interceptors = interceptors
        self._max_workers = max_workers
        self._service_config = service_config
        self._server: grpc.aio.Server | None = None
        self._shutdown_event = asyncio.Event()

    def _create_server(self) -> Server:
        """Create and configure the gRPC server.

        Returns:
            Configured gRPC server instance.
        """
        return grpc.aio.server(
            interceptors=self._interceptors,
            maximum_concurrent_rpcs=self._max_workers,
        )

    async def start(self) -> None:
        """Start the gRPC server.

        This will block until the server is stopped.
        """
        self._server = self._create_server()
        self._server.add_insecure_port(f"[::]:{self._port}")

        await self._server.start()

        logger.info(
            "server_started",
            port=self._port,
            max_workers=self._max_workers,
        )

        # Set up signal handlers
        self._setup_signal_handlers()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        try:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, self._handle_signal)
        except NotImplementedError:
            # Signal handlers not supported on this platform
            pass

    def _handle_signal(self) -> None:
        """Handle termination signals."""
        logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    async def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC server gracefully.

        Args:
            grace_period: Grace period in seconds for existing RPCs to complete.
        """
        if self._server is None:
            return

        logger.info("server_stopping", grace_period=grace_period)

        try:
            await asyncio.wait_for(self._server.stop(grace_period), timeout=grace_period + 1)
            logger.info("server_stopped")
        except TimeoutError, asyncio.CancelledError:
            # Shutdown was interrupted, which is acceptable during forced termination
            logger.info("server_shutdown_interrupted")

    async def wait_for_termination(self) -> None:
        """Wait for the server to terminate."""
        if self._server is None:
            return

        # Wait for shutdown signal or server termination
        tasks = [
            asyncio.create_task(self._shutdown_event.wait()),
            asyncio.create_task(self._server.wait_for_termination()),
        ]

        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks
        for task in pending:
            with suppress(asyncio.CancelledError):
                task.cancel()
                await task

    async def serve_forever(self) -> None:
        """Start the server and serve until termination."""
        await self.start()
        await self.wait_for_termination()


@asynccontextmanager
async def create_test_server(
    port: int,
    interceptors: list[grpc.aio.ServerInterceptor],
) -> AsyncIterator[grpc.aio.Server]:
    """Create a test server for testing purposes.

    Args:
        port: Port to listen on.
        interceptors: List of server interceptors.

    Yields:
        The running server instance.
    """
    server = grpc.aio.server(interceptors=interceptors)
    server.add_insecure_port(f"[::]:{port}")

    await server.start()

    try:
        yield server
    finally:
        with suppress(asyncio.CancelledError):
            await server.stop(0.1)
