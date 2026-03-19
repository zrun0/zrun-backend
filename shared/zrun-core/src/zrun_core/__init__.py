"""ZRun core infrastructure library.

This package provides shared infrastructure components for all zrun services.

Modules:
- infra: Configuration and logging
- auth: JWT authentication interceptor with JWKS caching
- domain: Domain error hierarchy with gRPC status mapping
- database: SQLAlchemy 2.0 async engine, session, and base models
- grpc: gRPC server with lifecycle management and health checks
- lock: Distributed lock with single-node and Redlock support
"""

from __future__ import annotations

# =============================================================================
# Authentication
# =============================================================================
from zrun_core.auth import USER_ID_CTX_KEY, AuthInterceptor

# =============================================================================
# Database
# =============================================================================
from zrun_core.database import (
    Base,
    TimestampMixin,
    create_async_engine,
    get_async_session,
    get_async_transaction,
)

# =============================================================================
# Domain
# =============================================================================
from zrun_core.domain import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
    abort_with_error,
    map_error_to_grpc_status,
)

# =============================================================================
# gRPC Server
# =============================================================================
from zrun_core.grpc import (
    BaseGRPCServer,
    configure_service_logging,
    create_auth_interceptor,
    create_health_servicer,
    create_test_server,
    mark_healthy,
    mark_unhealthy,
    register_health_service,
    run_service,
)

# =============================================================================
# Infrastructure
# =============================================================================
from zrun_core.infra import (
    LoggerMixin,
    ServiceConfig,
    configure_structlog,
    get_config,
    get_logger,
)

# =============================================================================
# Distributed Lock
# =============================================================================
from zrun_core.lock import (
    DistributedLock,
    LockAcquisitionError,
    LockError,
    LockReleaseError,
    LockRenewalError,
    RedisLock,  # Backward compatibility alias
    Redlock,
    SingleNodeLock,
    create_lock,
    redis_lock,
)

__all__ = [
    # =========================================================================
    # Infrastructure
    # =========================================================================
    "ServiceConfig",
    "get_config",
    "configure_structlog",
    "get_logger",
    "LoggerMixin",
    # =========================================================================
    # Authentication
    # =========================================================================
    "AuthInterceptor",
    "USER_ID_CTX_KEY",
    # =========================================================================
    # Domain
    # =========================================================================
    "DomainError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "map_error_to_grpc_status",
    "abort_with_error",
    # =========================================================================
    # Database
    # =========================================================================
    "Base",
    "TimestampMixin",
    "create_async_engine",
    "get_async_session",
    "get_async_transaction",
    # =========================================================================
    # gRPC Server
    # =========================================================================
    "BaseGRPCServer",
    "configure_service_logging",
    "create_auth_interceptor",
    "run_service",
    "create_test_server",
    # Health
    "create_health_servicer",
    "register_health_service",
    "mark_healthy",
    "mark_unhealthy",
    # =========================================================================
    # Distributed Lock
    # =========================================================================
    # Factory & Protocol
    "create_lock",
    "DistributedLock",
    # Single-node implementation
    "SingleNodeLock",
    "RedisLock",  # Backward compatibility
    "redis_lock",  # Context manager
    # Multi-node implementation
    "Redlock",
    # Exceptions
    "LockError",
    "LockAcquisitionError",
    "LockReleaseError",
    "LockRenewalError",
]
