"""gRPC health check utilities for Kubernetes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from grpc_health.v1 import health, health_pb2, health_pb2_grpc

if TYPE_CHECKING:
    from grpc.aio import Server


def create_health_servicer() -> health.HealthServicer:
    """Create a health servicer for K8s probes.

    Returns:
        Configured health servicer instance.
    """
    return health.HealthServicer()


def register_health_service(
    server: Server,
    health_servicer: health.HealthServicer,
) -> None:
    """Register health service to the gRPC server.

    Args:
        server: The gRPC server instance.
        health_servicer: The health servicer to register.
    """
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)


def mark_healthy(
    health_servicer: health.HealthServicer,
    service: str = "",
) -> None:
    """Mark service as healthy (ready to serve).

    Args:
        health_servicer: The health servicer instance.
        service: Service name (empty string = overall server health).
    """
    health_servicer.set(service, health_pb2.HealthCheckResponse.SERVING)


def mark_unhealthy(
    health_servicer: health.HealthServicer,
    service: str = "",
) -> None:
    """Mark service as unhealthy (not ready).

    Args:
        health_servicer: The health servicer instance.
        service: Service name (empty string = overall server health).
    """
    health_servicer.set(service, health_pb2.HealthCheckResponse.NOT_SERVING)
