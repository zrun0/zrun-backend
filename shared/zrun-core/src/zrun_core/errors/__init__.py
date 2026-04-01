"""Error handling - domain errors and gRPC mapping."""

from __future__ import annotations

from zrun_core.errors.errors import (
    AuthenticationError,
    AuthorizationError,
    BusinessError,
    ConflictError,
    DomainError,
    InternalError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    abort_with_error,
    map_error_to_grpc_status,
)

__all__ = [
    # Domain errors
    "DomainError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "AuthenticationError",
    "AuthorizationError",
    "BusinessError",
    "RateLimitError",
    "InternalError",
    # Error utilities
    "map_error_to_grpc_status",
    "abort_with_error",
]
