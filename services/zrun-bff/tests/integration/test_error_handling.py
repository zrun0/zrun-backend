"""Integration tests for error handling module."""

from __future__ import annotations


from grpc import StatusCode
from grpc.aio import AioRpcError
from zrun_bff.errors import (
    ConflictError,
    InternalError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    ValidationError,
    grpc_error_to_bff_error,
    map_grpc_to_http,
)


class TestGrpcToHttpMapping:
    """Tests for gRPC to HTTP status code mapping."""

    def test_ok_maps_to_200(self) -> None:
        """Test OK status maps to 200."""
        assert map_grpc_to_http(StatusCode.OK) == 200

    def test_not_found_maps_to_404(self) -> None:
        """Test NOT_FOUND maps to 404."""
        assert map_grpc_to_http(StatusCode.NOT_FOUND) == 404

    def test_unauthenticated_maps_to_401(self) -> None:
        """Test UNAUTHENTICATED maps to 401."""
        assert map_grpc_to_http(StatusCode.UNAUTHENTICATED) == 401

    def test_permission_denied_maps_to_403(self) -> None:
        """Test PERMISSION_DENIED maps to 403."""
        assert map_grpc_to_http(StatusCode.PERMISSION_DENIED) == 403

    def test_invalid_argument_maps_to_400(self) -> None:
        """Test INVALID_ARGUMENT maps to 400."""
        assert map_grpc_to_http(StatusCode.INVALID_ARGUMENT) == 400

    def test_already_exists_maps_to_409(self) -> None:
        """Test ALREADY_EXISTS maps to 409."""
        assert map_grpc_to_http(StatusCode.ALREADY_EXISTS) == 409

    def test_unavailable_maps_to_503(self) -> None:
        """Test UNAVAILABLE maps to 503."""
        assert map_grpc_to_http(StatusCode.UNAVAILABLE) == 503

    def test_unknown_maps_to_500(self) -> None:
        """Test UNKNOWN maps to 500."""
        assert map_grpc_to_http(StatusCode.UNKNOWN) == 500

    def test_cancelled_maps_to_499(self) -> None:
        """Test CANCELLED maps to 499."""
        assert map_grpc_to_http(StatusCode.CANCELLED) == 499


class TestBFFErrors:
    """Tests for BFF-specific error classes."""

    def test_validation_error_has_correct_status(self) -> None:
        """Test ValidationError has status 400."""
        error = ValidationError(detail="Invalid input")
        assert error.status_code == 400
        assert error.error_code == "VALIDATION_ERROR"

    def test_unauthorized_error_has_correct_status(self) -> None:
        """Test UnauthorizedError has status 401."""
        error = UnauthorizedError()
        assert error.status_code == 401
        assert error.error_code == "UNAUTHORIZED"

    def test_not_found_error_has_correct_status(self) -> None:
        """Test NotFoundError has status 404."""
        error = NotFoundError(detail="Resource not found")
        assert error.status_code == 404
        assert error.error_code == "NOT_FOUND"

    def test_conflict_error_has_correct_status(self) -> None:
        """Test ConflictError has status 409."""
        error = ConflictError(detail="Resource already exists")
        assert error.status_code == 409
        assert error.error_code == "CONFLICT"

    def test_internal_error_has_correct_status(self) -> None:
        """Test InternalError has status 500."""
        error = InternalError()
        assert error.status_code == 500
        assert error.error_code == "INTERNAL_ERROR"

    def test_service_unavailable_error_has_correct_status(self) -> None:
        """Test ServiceUnavailableError has status 503."""
        error = ServiceUnavailableError()
        assert error.status_code == 503
        assert error.error_code == "SERVICE_UNAVAILABLE"

    def test_bff_error_includes_context(self) -> None:
        """Test BFFError includes context in detail."""
        error = ValidationError(
            detail="Invalid input",
            context={"field": "email", "reason": "invalid format"},
        )
        assert error.context == {"field": "email", "reason": "invalid format"}


class TestGrpcErrorConversion:
    """Tests for gRPC error to BFF error conversion."""

    def test_not_found_status_maps_correctly(self) -> None:
        """Test NOT_FOUND status maps to 404 via map function."""
        http_status = map_grpc_to_http(StatusCode.NOT_FOUND)
        assert http_status == 404

    def test_unauthenticated_status_maps_correctly(self) -> None:
        """Test UNAUTHENTICATED status maps to 401 via map function."""
        http_status = map_grpc_to_http(StatusCode.UNAUTHENTICATED)
        assert http_status == 401

    def test_permission_denied_status_maps_correctly(self) -> None:
        """Test PERMISSION_DENIED status maps to 403 via map function."""
        http_status = map_grpc_to_http(StatusCode.PERMISSION_DENIED)
        assert http_status == 403

    def test_invalid_argument_status_maps_correctly(self) -> None:
        """Test INVALID_ARGUMENT status maps to 400 via map function."""
        http_status = map_grpc_to_http(StatusCode.INVALID_ARGUMENT)
        assert http_status == 400

    def test_already_exists_status_maps_correctly(self) -> None:
        """Test ALREADY_EXISTS status maps to 409 via map function."""
        http_status = map_grpc_to_http(StatusCode.ALREADY_EXISTS)
        assert http_status == 409

    def test_unavailable_status_maps_correctly(self) -> None:
        """Test UNAVAILABLE status maps to 503 via map function."""
        http_status = map_grpc_to_http(StatusCode.UNAVAILABLE)
        assert http_status == 503

    def test_unknown_status_maps_correctly(self) -> None:
        """Test UNKNOWN status maps to 500 via map function."""
        http_status = map_grpc_to_http(StatusCode.UNKNOWN)
        assert http_status == 500

    def test_generic_exception_converts_to_internal_error(self) -> None:
        """Test generic exception converts to InternalError."""
        generic_error = Exception("Something went wrong")

        bff_error = grpc_error_to_bff_error(generic_error)

        assert isinstance(bff_error, InternalError)
        assert bff_error.status_code == 500

    def _create_mock_grpc_error(self, code: StatusCode, details: str) -> AioRpcError:
        """Create a mock gRPC error for testing.

        Args:
            code: gRPC status code.
            details: Error details.

        Returns:
            Mock AioRpcError instance.
        """

        # Create a mock error that has the same interface as AioRpcError
        class MockRpcError(Exception):
            def __init__(self, code: StatusCode, details: str) -> None:
                self._code = code
                self._details = details
                super().__init__(details)

            def code(self) -> StatusCode:  # type: ignore[override]
                return self._code

            def details(self) -> str:  # type: ignore[override]
                return self._details

        return MockRpcError(code, details)


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_from_bff_error_creates_correct_response(self) -> None:
        """Test ErrorResponse from BFFError has correct fields."""
        error = ValidationError(
            detail="Invalid input",
            context={"field": "email"},
        )

        from zrun_bff.errors import ErrorResponse

        response = ErrorResponse.from_bff_error(error)

        assert response.error_code == "VALIDATION_ERROR"
        assert response.message == "Invalid input"
        assert response.details == {"field": "email"}

    def test_from_bff_error_without_context(self) -> None:
        """Test ErrorResponse from BFFError without context."""
        error = NotFoundError(detail="Resource not found")

        from zrun_bff.errors import ErrorResponse

        response = ErrorResponse.from_bff_error(error)

        assert response.error_code == "NOT_FOUND"
        assert response.message == "Resource not found"
        # Empty dict when context is None (due to Pydantic default)
        assert response.details in (None, {})
