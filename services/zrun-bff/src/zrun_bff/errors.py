"""Error handling and mapping for Zrun BFF.

This module provides:
- gRPC status code to HTTP status code mapping
- Custom exception classes for BFF-specific errors
- Exception handlers for FastAPI

Architecture Note:
    BFF errors (HTTP layer) are separate from zrun-core errors (domain layer):
    - zrun_core.errors: Domain errors → gRPC status (for inter-service communication)
    - zrun_bff.errors: HTTP errors → HTTP responses (for frontend API)

    When BFF receives a gRPC error from a downstream service, it maps it to
    an appropriate HTTP error using the grpc_error_to_bff_error() function.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Self

from fastapi import HTTPException, status
from grpc import StatusCode
from pydantic import BaseModel, Field


class ErrorCode(IntEnum):
    """BFF-specific error codes."""

    VALIDATION_ERROR = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503


# gRPC status code to HTTP status code mapping
GRPC_TO_HTTP: dict[StatusCode, int] = {
    StatusCode.OK: status.HTTP_200_OK,
    StatusCode.CANCELLED: 499,  # Client Closed Request (Nginx-specific)
    StatusCode.UNKNOWN: status.HTTP_500_INTERNAL_SERVER_ERROR,
    StatusCode.INVALID_ARGUMENT: status.HTTP_400_BAD_REQUEST,
    StatusCode.DEADLINE_EXCEEDED: status.HTTP_504_GATEWAY_TIMEOUT,
    StatusCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    StatusCode.ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    StatusCode.PERMISSION_DENIED: status.HTTP_403_FORBIDDEN,
    StatusCode.UNAUTHENTICATED: status.HTTP_401_UNAUTHORIZED,
    StatusCode.RESOURCE_EXHAUSTED: status.HTTP_429_TOO_MANY_REQUESTS,
    StatusCode.FAILED_PRECONDITION: status.HTTP_400_BAD_REQUEST,
    StatusCode.ABORTED: status.HTTP_409_CONFLICT,
    StatusCode.OUT_OF_RANGE: status.HTTP_400_BAD_REQUEST,
    StatusCode.UNIMPLEMENTED: status.HTTP_501_NOT_IMPLEMENTED,
    StatusCode.INTERNAL: status.HTTP_500_INTERNAL_SERVER_ERROR,
    StatusCode.UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
    StatusCode.DATA_LOSS: status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def map_grpc_to_http(grpc_status: StatusCode) -> int:
    """Map gRPC status code to HTTP status code.

    Args:
        grpc_status: gRPC StatusCode.

    Returns:
        HTTP status code.
    """
    return GRPC_TO_HTTP.get(grpc_status, status.HTTP_500_INTERNAL_SERVER_ERROR)


class BFFError(HTTPException):
    """Base exception for BFF-specific errors.

    Attributes:
        status_code: HTTP status code.
        detail: Error detail message.
        error_code: Internal error code.
        context: Additional error context.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str = "BFF_ERROR",
        context: dict[str, str] | None = None,
    ) -> None:
        """Initialize BFF error.

        Args:
            status_code: HTTP status code.
            detail: Error detail message.
            error_code: Internal error code.
            context: Additional error context.
        """
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code
        self.context = context or {}


class ValidationError(BFFError):
    """Validation error (400).

    Corresponds to zrun_core.errors.ValidationError at the HTTP layer.
    """

    def __init__(self, detail: str, context: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            error_code="VALIDATION_ERROR",
            context=context,
        )


class UnauthorizedError(BFFError):
    """Unauthorized error (401).

    Corresponds to zrun_core.errors.AuthenticationError at the HTTP layer.
    """

    def __init__(self, detail: str = "Unauthorized", context: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            error_code="UNAUTHORIZED",
            context=context,
        )


class ForbiddenError(BFFError):
    """Forbidden error (403).

    Corresponds to zrun_core.errors.AuthorizationError at the HTTP layer.
    """

    def __init__(self, detail: str = "Forbidden", context: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            error_code="FORBIDDEN",
            context=context,
        )


class NotFoundError(BFFError):
    """Not found error (404).

    Corresponds to zrun_core.errors.NotFoundError at the HTTP layer.
    """

    def __init__(self, detail: str, context: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            error_code="NOT_FOUND",
            context=context,
        )


class ConflictError(BFFError):
    """Conflict error (409).

    Corresponds to zrun_core.errors.ConflictError at the HTTP layer.
    """

    def __init__(self, detail: str, context: dict[str, str] | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            error_code="CONFLICT",
            context=context,
        )


class InternalError(BFFError):
    """Internal server error (500)."""

    def __init__(
        self,
        detail: str = "Internal server error",
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            error_code="INTERNAL_ERROR",
            context=context,
        )


class ServiceUnavailableError(BFFError):
    """Service unavailable error (503)."""

    def __init__(
        self,
        detail: str = "Service unavailable",
        context: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
            error_code="SERVICE_UNAVAILABLE",
            context=context,
        )


def grpc_error_to_bff_error(grpc_error: Exception) -> BFFError:
    """Convert gRPC error to BFF error.

    Args:
        grpc_error: gRPC AioRpcError.

    Returns:
        Corresponding BFF error.
    """
    try:
        from grpc.aio import AioRpcError

        if isinstance(grpc_error, AioRpcError):
            grpc_status = grpc_error.code()
            http_status = map_grpc_to_http(grpc_status)
            detail = grpc_error.details() or f"gRPC error: {grpc_status.name}"

            # Map to specific BFF error types
            if http_status == status.HTTP_400_BAD_REQUEST:
                return ValidationError(detail=detail)
            if http_status == status.HTTP_401_UNAUTHORIZED:
                return UnauthorizedError(detail=detail)
            if http_status == status.HTTP_403_FORBIDDEN:
                return ForbiddenError(detail=detail)
            if http_status == status.HTTP_404_NOT_FOUND:
                return NotFoundError(detail=detail)
            if http_status == status.HTTP_409_CONFLICT:
                return ConflictError(detail=detail)
            if http_status == status.HTTP_503_SERVICE_UNAVAILABLE:
                return ServiceUnavailableError(detail=detail)
            return InternalError(detail=detail)

        return InternalError(detail=str(grpc_error))
    except Exception:
        return InternalError(detail="Unknown error")


# Error response schema
class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error_code: str = Field(..., description="Internal error code")
    message: str = Field(..., description="Error message")
    details: dict[str, str] | None = Field(default=None, description="Additional error details")

    @classmethod
    def from_bff_error(cls, error: BFFError) -> Self:
        """Create ErrorResponse from BFFError.

        Args:
            error: BFF error instance.

        Returns:
            ErrorResponse instance.
        """
        return cls(
            error_code=error.error_code,
            message=error.detail,
            details=error.context,
        )
