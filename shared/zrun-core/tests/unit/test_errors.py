"""Unit tests for error handling."""

from __future__ import annotations

import grpc

from zrun_core.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InternalError,
    NotFoundError,
    RateLimitError,
    ValidationError,
    abort_with_error,
    map_error_to_grpc_status,
)


class TestDomainError:
    """Tests for DomainError base class."""

    def test_domain_error_with_message(self) -> None:
        """Test DomainError with custom message."""
        msg = "Something went wrong"
        error = DomainError(message=msg)
        assert str(error) == msg
        assert error.message == msg

    def test_domain_error_with_code(self) -> None:
        """Test DomainError with custom code."""
        msg = "Custom error"
        code = "CUSTOM_CODE"
        error = DomainError(message=msg, code=code)
        assert error.code == code

    def test_domain_error_default_code(self) -> None:
        """Test DomainError uses class name as default code."""
        error = ValidationError(message="Invalid input")
        assert error.code == "ValidationError"


class TestErrorSubclasses:
    """Tests for error subclasses."""

    def test_validation_error(self) -> None:
        """Test ValidationError."""
        error = ValidationError(message="Validation failed")
        assert isinstance(error, DomainError)
        assert error.message == "Validation failed"

    def test_not_found_error(self) -> None:
        """Test NotFoundError."""
        error = NotFoundError(message="Resource not found")
        assert isinstance(error, DomainError)

    def test_conflict_error(self) -> None:
        """Test ConflictError."""
        error = ConflictError(message="Resource already exists")
        assert isinstance(error, DomainError)

    def test_authentication_error(self) -> None:
        """Test AuthenticationError."""
        error = AuthenticationError(message="Invalid credentials")
        assert isinstance(error, DomainError)

    def test_authorization_error(self) -> None:
        """Test AuthorizationError."""
        from zrun_core.errors import AuthorizationError

        error = AuthorizationError(message="Access denied")
        assert isinstance(error, DomainError)

    def test_rate_limit_error(self) -> None:
        """Test RateLimitError."""
        error = RateLimitError(message="Too many requests")
        assert isinstance(error, DomainError)

    def test_internal_error(self) -> None:
        """Test InternalError."""
        error = InternalError(message="Internal server error")
        assert isinstance(error, DomainError)


class TestMapErrorToGrpcStatus:
    """Tests for map_error_to_grpc_status function."""

    def test_validation_error_maps_to_invalid_argument(self) -> None:
        """Test ValidationError maps to INVALID_ARGUMENT."""
        status = map_error_to_grpc_status(ValidationError(message="Invalid"))
        assert status == grpc.StatusCode.INVALID_ARGUMENT

    def test_not_found_error_maps_to_not_found(self) -> None:
        """Test NotFoundError maps to NOT_FOUND."""
        status = map_error_to_grpc_status(NotFoundError(message="Not found"))
        assert status == grpc.StatusCode.NOT_FOUND

    def test_conflict_error_maps_to_already_exists(self) -> None:
        """Test ConflictError maps to ALREADY_EXISTS."""
        status = map_error_to_grpc_status(ConflictError(message="Conflict"))
        assert status == grpc.StatusCode.ALREADY_EXISTS

    def test_authentication_error_maps_to_unauthenticated(self) -> None:
        """Test AuthenticationError maps to UNAUTHENTICATED."""
        status = map_error_to_grpc_status(AuthenticationError(message="Auth failed"))
        assert status == grpc.StatusCode.UNAUTHENTICATED

    def test_authorization_error_maps_to_permission_denied(self) -> None:
        """Test AuthorizationError maps to PERMISSION_DENIED."""
        from zrun_core.errors import AuthorizationError

        status = map_error_to_grpc_status(AuthorizationError(message="Denied"))
        assert status == grpc.StatusCode.PERMISSION_DENIED

    def test_rate_limit_error_maps_to_resource_exhausted(self) -> None:
        """Test RateLimitError maps to RESOURCE_EXHAUSTED."""
        status = map_error_to_grpc_status(RateLimitError(message="Rate limited"))
        assert status == grpc.StatusCode.RESOURCE_EXHAUSTED

    def test_generic_domain_error_maps_to_failed_precondition(self) -> None:
        """Test generic DomainError maps to FAILED_PRECONDITION."""
        status = map_error_to_grpc_status(DomainError(message="Generic"))
        assert status == grpc.StatusCode.FAILED_PRECONDITION

    def test_unknown_exception_maps_to_internal(self) -> None:
        """Test unknown exception maps to INTERNAL."""
        status = map_error_to_grpc_status(Exception("Unknown"))
        assert status == grpc.StatusCode.INTERNAL


class TestAbortWithError:
    """Tests for abort_with_error function."""

    def test_abort_with_domain_error(self) -> None:
        """Test abort_with_domain_error includes error code."""
        mock_context = _MockContext()
        error = ValidationError(message="Invalid input", code="VALIDATION")

        try:
            abort_with_error(mock_context, error)
        except AssertionError:
            pass  # Expected due to unreachable code

        assert mock_context.aborted
        assert mock_context.status_code == grpc.StatusCode.INVALID_ARGUMENT
        assert "VALIDATION" in mock_context.details
        assert "Invalid input" in mock_context.details

    def test_abort_with_generic_exception(self) -> None:
        """Test abort_with_generic_exception."""
        mock_context = _MockContext()
        error = ValueError("Something broke")

        try:
            abort_with_error(mock_context, error)
        except AssertionError:
            pass  # Expected due to unreachable code

        assert mock_context.aborted
        assert mock_context.status_code == grpc.StatusCode.INTERNAL
        assert "Something broke" in mock_context.details


class _MockContext:
    """Mock gRPC context for testing."""

    def __init__(self) -> None:
        self.aborted = False
        self.status_code: grpc.StatusCode | None = None
        self.details: str = ""

    def abort(self, code: grpc.StatusCode, details: str) -> None:
        """Mock abort method."""
        self.aborted = True
        self.status_code = code
        self.details = details
        # In real gRPC, this would terminate the RPC
