"""Exception hierarchy and error mapping for zrun services."""

from __future__ import annotations

from typing import Any, NoReturn

import grpc


class DomainError(Exception):
    """Base exception for domain errors.

    Domain errors represent business logic violations that are
    expected and recoverable (e.g., validation errors, not found errors).
    """

    message: str
    code: str

    def __init__(
        self,
        message: str,
        code: str | None = None,
    ) -> None:
        """Initialize the domain error.

        Args:
            message: Human-readable error message.
            code: Machine-readable error code.
        """
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(message)

    def to_grpc_status(self) -> grpc.StatusCode:
        """Convert this error to a gRPC status code.

        Returns:
            The corresponding gRPC status code.
        """
        return map_error_to_grpc_status(self)


class ValidationError(DomainError):
    """Raised when input validation fails."""


class NotFoundError(DomainError):
    """Raised when a requested resource is not found."""


class ConflictError(DomainError):
    """Raised when there's a conflict with existing state."""


class AuthenticationError(DomainError):
    """Raised when authentication fails."""


class AuthorizationError(DomainError):
    """Raised when a user is not authorized for an action."""


class RateLimitError(DomainError):
    """Raised when a rate limit is exceeded."""


class InternalError(DomainError):
    """Raised when an internal error occurs."""


def map_error_to_grpc_status(error: Exception) -> grpc.StatusCode:
    """Map a domain error to the appropriate gRPC status code.

    Args:
        error: The exception to map.

    Returns:
        The corresponding gRPC status code.
    """
    if isinstance(error, ValidationError):
        return grpc.StatusCode.INVALID_ARGUMENT
    if isinstance(error, NotFoundError):
        return grpc.StatusCode.NOT_FOUND
    if isinstance(error, ConflictError):
        return grpc.StatusCode.ALREADY_EXISTS
    if isinstance(error, AuthenticationError):
        return grpc.StatusCode.UNAUTHENTICATED
    if isinstance(error, AuthorizationError):
        return grpc.StatusCode.PERMISSION_DENIED
    if isinstance(error, RateLimitError):
        return grpc.StatusCode.RESOURCE_EXHAUSTED
    if isinstance(error, DomainError):
        return grpc.StatusCode.FAILED_PRECONDITION
    if isinstance(error, grpc.RpcError):
        return error.code()

    # Default to internal error for unknown exceptions
    return grpc.StatusCode.INTERNAL


def abort_with_error(
    context: Any,
    error: Exception,
) -> NoReturn:
    """Abort the gRPC call with the appropriate error status.

    Args:
        context: The gRPC context to abort.
        error: The exception that caused the error.

    Raises:
        grpc.aio.AioRpcError: Always raises to abort the call.
    """
    status_code = map_error_to_grpc_status(error)
    message = str(error)

    # Create the error details
    details = f"[{error.code}] {error.message}" if isinstance(error, DomainError) else message

    # Abort the context
    context.abort(status_code, details)

    # This is unreachable but type checkers need it
    msg = "unreachable"
    raise AssertionError(msg)
