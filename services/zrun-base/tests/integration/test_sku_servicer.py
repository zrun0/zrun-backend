"""Integration tests for SKU servicer."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import grpc
import pytest

from zrun_base.logic.domain import CreateSkuInput
from zrun_core import USER_ID_CTX_KEY

if TYPE_CHECKING:
    from zrun_base.logic.sku import SkuLogic
    from zrun_base.servicers.sku_servicer import SkuServicer


class MockRpcError(Exception):
    """Mock RPC error for testing."""

    def __init__(self, code: grpc.StatusCode, details: str) -> None:
        self._code = code
        self._details = details
        super().__init__(f"RPC error: {code} - {details}")


class MockServicerContext:
    """Mock servicer context for testing."""

    def __init__(self) -> None:
        self._aborted = False
        self._abort_code: grpc.StatusCode | None = None
        self._abort_message: str | None = None
        self._metadata: list[tuple[str, str]] = []

    def abort(self, code: grpc.StatusCode, message: str) -> None:
        """Abort the context."""
        self._aborted = True
        self._abort_code = code
        self._abort_message = message
        # Raise exception to simulate real gRPC behavior
        raise MockRpcError(code, message)

    def invocation_metadata(self) -> list[tuple[str, str]]:
        """Get invocation metadata."""
        return self._metadata


@pytest.fixture
def mock_context() -> Any:
    """Create a mock servicer context."""
    return MockServicerContext()


class TestSkuServicer:
    """Integration tests for SKU servicer."""

    async def test_create_sku_success(
        self,
        sku_servicer: SkuServicer,
        mock_context: Any,
    ) -> None:
        """Test successful SKU creation via gRPC."""
        from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

        # Set user context
        token = USER_ID_CTX_KEY.set("test-user")
        try:
            # Create request
            request = base_sku_pb2.CreateSkuRequest(
                code="TEST-SKU-001",
                name="Test SKU",
            )

            # Call the servicer
            response = await sku_servicer.CreateSku(request, mock_context)

            # Verify response - response is now CreateSkuResponse
            assert response.sku.id is not None
            assert response.sku.code == "TEST-SKU-001"
            assert response.sku.name == "Test SKU"
            assert response.sku.created_at > 0

            # Verify no abort
            assert not mock_context._aborted

        finally:
            USER_ID_CTX_KEY.reset(token)

    async def test_create_sku_empty_code_raises_error(
        self,
        sku_servicer: SkuServicer,
        mock_context: Any,
    ) -> None:
        """Test that empty code raises an error."""
        from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

        token = USER_ID_CTX_KEY.set("test-user")
        try:
            request = base_sku_pb2.CreateSkuRequest(
                code="",
                name="Test SKU",
            )

            with pytest.raises(MockRpcError):
                await sku_servicer.CreateSku(request, mock_context)

            # Verify abort was called
            assert mock_context._aborted

        finally:
            USER_ID_CTX_KEY.reset(token)

    async def test_get_sku_success(
        self,
        sku_servicer: SkuServicer,
        sku_logic: SkuLogic,
        mock_context: Any,
    ) -> None:
        """Test successful SKU retrieval via gRPC."""
        from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

        token = USER_ID_CTX_KEY.set("test-user")
        try:
            # Create a SKU first
            input = CreateSkuInput(
                code="TEST-SKU-001",
                name="Test SKU",
            )
            sku = await sku_logic.create_sku(input)

            # Get the SKU
            request = base_sku_pb2.GetSkuRequest(sku_id=sku.id)
            response = await sku_servicer.GetSku(request, mock_context)

            # Verify response - response is now GetSkuResponse
            assert response.sku.id == sku.id
            assert response.sku.code == "TEST-SKU-001"
            assert response.sku.name == "Test SKU"

            # Verify no abort
            assert not mock_context._aborted

        finally:
            USER_ID_CTX_KEY.reset(token)

    async def test_get_sku_not_found_aborts(
        self,
        sku_servicer: SkuServicer,
        mock_context: Any,
    ) -> None:
        """Test that getting non-existent SKU aborts."""
        from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

        token = USER_ID_CTX_KEY.set("test-user")
        try:
            request = base_sku_pb2.GetSkuRequest(sku_id="non-existent-id")

            with pytest.raises(MockRpcError):
                await sku_servicer.GetSku(request, mock_context)

            # Verify abort was called
            assert mock_context._aborted

        finally:
            USER_ID_CTX_KEY.reset(token)
