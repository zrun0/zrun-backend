"""ZRun core infrastructure library.

This package provides shared infrastructure components for all zrun services:
- BaseGrpcServer: Base class for gRPC servers
- AuthInterceptor: JWT authentication interceptor with JWKS caching
- RedisLock: Distributed lock implementation with watchdog
- DomainError hierarchy: Exception types for domain errors
- ServiceConfig: Configuration management
- SQLAlchemy 2.0 utilities: Database engine, session, and base models
"""

from __future__ import annotations

from zrun_core.auth import USER_ID_CTX_KEY, AuthInterceptor
from zrun_core.config import ServiceConfig
from zrun_core.database import (
    Base,
    TimestampMixin,
    create_async_engine,
    get_async_session,
    get_async_transaction,
)
from zrun_core.errors import (
    ConflictError,
    DomainError,
    NotFoundError,
    ValidationError,
    map_error_to_grpc_status,
)
from zrun_core.lock import RedisLock
from zrun_core.logging import configure_structlog, get_logger
from zrun_core.server import (
    BaseGrpcServer,
    configure_service_logging,
    create_auth_interceptor,
    run_service,
)

__all__ = [
    "BaseGrpcServer",
    "AuthInterceptor",
    "USER_ID_CTX_KEY",
    "RedisLock",
    "DomainError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "map_error_to_grpc_status",
    "ServiceConfig",
    "configure_structlog",
    "get_logger",
    "configure_service_logging",
    "create_auth_interceptor",
    "run_service",
    # SQLAlchemy 2.0 utilities
    "Base",
    "TimestampMixin",
    "create_async_engine",
    "get_async_session",
    "get_async_transaction",
]
