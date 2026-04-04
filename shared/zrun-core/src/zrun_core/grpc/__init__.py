"""gRPC server, client, and health check utilities."""

from __future__ import annotations

from zrun_core.grpc.client import (
    GrpcChannelConfig,
    GrpcClientFactory,
    GrpcClientManager,
    get_client_manager,
)
from zrun_core.grpc.health import (
    create_health_servicer,
    mark_healthy,
    mark_unhealthy,
    register_health_service,
)
from zrun_core.grpc.protocols import GrpcChannelFactoryProtocol, GrpcClientManagerProtocol
from zrun_core.grpc.server import (
    BaseGRPCServer,
    create_test_server,
    run_service,
)

__all__ = [
    # Server
    "BaseGRPCServer",
    "run_service",
    "create_test_server",
    # Health
    "create_health_servicer",
    "register_health_service",
    "mark_healthy",
    "mark_unhealthy",
    # Client
    "GrpcChannelConfig",
    "GrpcClientFactory",
    "GrpcClientManager",
    "GrpcClientManagerProtocol",
    "GrpcChannelFactoryProtocol",
    "get_client_manager",
]
