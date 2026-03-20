"""Base gRPC server implementation."""

from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager, suppress
from typing import TYPE_CHECKING

import grpc.aio

from zrun_core.infra import LoggerMixin

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Sequence

    from grpc.aio import Server
    from sqlalchemy.ext.asyncio import AsyncEngine as Engine

    from zrun_core.infra import ServiceConfig


class BaseGRPCServer(LoggerMixin):
    """Base gRPC server with lifecycle management.

    This class provides a production-ready gRPC server with:
    - Graceful shutdown on SIGTERM/SIGINT
    - Interceptor chaining support
    - Lifecycle logging
    - Configurable worker threads
    - K8s health check support
    """

    def __init__(
        self,
        port: int,
        interceptors: list[grpc.aio.ServerInterceptor],
        max_workers: int = 10,
        service_config: ServiceConfig | None = None,
        enable_health_check: bool = True,
    ) -> None:
        """Initialize the server.

        Args:
            port: Port to listen on.
            interceptors: List of server interceptors.
            max_workers: Maximum number of worker threads.
            service_config: Optional service configuration.
            enable_health_check: Enable gRPC health check service for K8s.
        """
        self._port = port
        self._interceptors = interceptors
        self._max_workers = max_workers
        self._service_config = service_config
        self._enable_health_check = enable_health_check
        self._server: grpc.aio.Server | None = None
        self._shutdown_event = asyncio.Event()

        # Health check servicer (set during start if enabled)
        self._health_servicer: object | None = None

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

        # Register health check service if enabled
        if self._enable_health_check:
            from .health import (
                create_health_servicer,
                mark_healthy,
                register_health_service,
            )

            self._health_servicer = create_health_servicer()
            register_health_service(self._server, self._health_servicer)

        self._server.add_insecure_port(f"[::]:{self._port}")

        await self._server.start()

        # Mark as healthy after successful start
        if self._health_servicer is not None:
            mark_healthy(self._health_servicer)  # type: ignore[no-untyped-call]

        self.logger.info(
            "server_started",
            port=self._port,
            max_workers=self._max_workers,
            health_check_enabled=self._enable_health_check,
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
        self.logger.info("shutdown_signal_received")
        self._shutdown_event.set()

    async def stop(self, grace_period: float = 5.0) -> None:
        """Stop the gRPC server gracefully.

        Args:
            grace_period: Grace period in seconds for existing RPCs to complete.
        """
        if self._server is None:
            return

        # Mark as unhealthy before stopping
        if self._health_servicer is not None:
            from .health import mark_unhealthy

            mark_unhealthy(self._health_servicer)  # type: ignore[no-untyped-call]

        self.logger.info("server_stopping", grace_period=grace_period)

        try:
            await asyncio.wait_for(self._server.stop(grace_period), timeout=grace_period + 1)
            self.logger.info("server_stopped")
        except TimeoutError, asyncio.CancelledError:
            # Shutdown was interrupted, which is acceptable during forced termination
            self.logger.info("server_shutdown_interrupted")

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


async def run_service(
    servicers: Sequence[tuple[Callable[[object, Server], None], object]],  # type: ignore[name-defined]
    config: ServiceConfig,
    engine: Engine | None = None,  # type: ignore[name-defined]
    *,
    service_name: str = "zrun-service",
) -> int:
    """Run a gRPC service with full lifecycle management.

    This function handles:
    - Logging configuration
    - Server creation and servicer registration
    - Graceful shutdown on signals
    - Engine disposal if provided

    Args:
        servicers: Sequence of (register_fn, servicer_instance) tuples.
            register_fn is the gRPC add_*_servicer_to_server function.
        config: Service configuration.
        engine: Optional SQLAlchemy async engine to dispose on shutdown.
        service_name: Name of the service for logging context.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # Configure logging
    from zrun_core.infra import configure_structlog, get_logger

    configure_structlog(
        service_name=service_name,
        log_level=config.log_level,
        log_format=config.log_format,
    )
    service_logger = get_logger()

    service_logger.info(
        "service_starting",
        env=config.env,
        port=config.port,
    )

    # Create and start server
    server = BaseGRPCServer(
        port=config.port,
        interceptors=[],
        max_workers=config.max_workers,
        service_config=config,
    )

    # Start the server to get the underlying gRPC server
    await server.start()

    # Register servicers
    if server._server is not None:
        for register_fn, servicer_instance in servicers:
            register_fn(  # type: ignore[no-untyped-call]
                servicer_instance,
                server._server,
            )

    try:
        await server.wait_for_termination()
        return 0
    except KeyboardInterrupt:
        service_logger.info("service_interrupted")
        return 0
    except Exception:
        service_logger.exception("service_error")
        return 1
    finally:
        await server.stop()
        if engine is not None:
            await engine.dispose()
        service_logger.info("service_stopped")


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
