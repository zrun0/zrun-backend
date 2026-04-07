"""Unit tests for gRPC clients.

Tests verify:
- gRPC client initialization
- Authentication metadata injection
- Error handling and mapping
- User context propagation
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from grpc.aio import Channel

from zrun_bff.clients.base import BaseSkuClient
from zrun_bff.clients.factory import get_client_manager
from zrun_bff.clients.interceptors import (
    build_auth_metadata,
    get_user_context,
    set_user_context,
)
from zrun_bff.clients.utils import handle_grpc_error


class TestGrpcClientFactory:
    """Tests for gRPC client factory."""

    def test_get_client_manager_returns_singleton(self) -> None:
        """Test that get_client_manager returns the same instance."""
        manager1 = get_client_manager()
        manager2 = get_client_manager()

        assert manager1 is manager2


class TestUserContextManagement:
    """Tests for user context management."""

    def test_set_and_get_user_context(self) -> None:
        """Test setting and getting user context."""
        set_user_context(
            user_id="test_user",
            token="test_token",
            scopes=["pda:read", "pda:write"],
        )

        context = get_user_context()

        assert context["user_id"] == "test_user"
        assert context["token"] == "test_token"
        assert context["scopes"] == ["pda:read", "pda:write"]


class TestAuthenticationMetadata:
    """Tests for authentication metadata injection."""

    def test_build_auth_metadata_with_full_context(self) -> None:
        """Test building auth metadata with full user context."""
        set_user_context(
            user_id="test_user",
            token="test_token",
            scopes=["pda:read", "pda:write"],
        )

        metadata = build_auth_metadata()
        metadata_list = list(metadata)

        assert ("x-user-id", "test_user") in metadata_list
        assert ("authorization", "Bearer test_token") in metadata_list
        assert ("x-scopes", "pda:read,pda:write") in metadata_list


class TestBaseSkuClient:
    """Tests for BaseSkuClient."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create a mock gRPC channel."""
        return MagicMock(spec=Channel)

    @pytest.fixture
    def sku_client(self, mock_channel: MagicMock) -> BaseSkuClient:
        """Create a BaseSkuClient with mock channel."""
        return BaseSkuClient(mock_channel)

    def test_create_sku_client_initializes_stub(self, mock_channel: MagicMock) -> None:
        """Test that create_sku_client initializes the gRPC stub."""
        client = BaseSkuClient(mock_channel)

        assert client._channel == mock_channel
        assert client._stub is not None

    def test_create_sku_injects_auth_metadata(self, sku_client: BaseSkuClient) -> None:
        """Test that create_sku injects authentication metadata."""
        set_user_context(user_id="test_user", token="test_token", scopes=["pda:write"])

        with patch.object(sku_client._stub, "CreateSku", new_callable=AsyncMock) as mock_method:
            mock_response = MagicMock()
            mock_response.sku.id = "123"
            mock_response.sku.code = "TEST001"
            mock_response.sku.name = "Test SKU"
            mock_method.return_value = mock_response

            import asyncio

            result = asyncio.run(sku_client.create_sku(code="TEST001", name="Test SKU"))

            # Verify metadata was injected
            call_args = mock_method.call_args
            metadata = call_args.kwargs.get("metadata")
            metadata_list = list(metadata)
            assert ("x-user-id", "test_user") in metadata_list


class TestGrpcErrorHandling:
    """Tests for gRPC error handling."""

    def test_handle_grpc_error_returns_result_on_success(self) -> None:
        """Test that handle_grpc_error returns result on success."""

        @handle_grpc_error
        async def success_func() -> dict[str, str]:
            return {"id": "123"}

        import asyncio

        result = asyncio.run(success_func())
        assert result == {"id": "123"}

    def test_handle_grpc_error_raises_on_exception(self) -> None:
        """Test that handle_grpc_error raises on generic exception."""
        from zrun_bff.errors import InternalError

        @handle_grpc_error
        async def failing_func() -> dict[str, str]:
            raise ValueError("Test error")

        import asyncio

        with pytest.raises(InternalError):
            asyncio.run(failing_func())
