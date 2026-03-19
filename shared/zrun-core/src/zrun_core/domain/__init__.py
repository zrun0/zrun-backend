"""Domain layer - shared business concepts and error handling."""

from __future__ import annotations

from zrun_core.domain.errors import (
    AuthenticationError,
    AuthorizationError,
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
    "RateLimitError",
    "InternalError",
    # Error utilities
    "map_error_to_grpc_status",
    "abort_with_error",
]
