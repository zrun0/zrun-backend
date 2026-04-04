"""Unit tests for gRPC clients."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from typing import Any

import pytest


class TestAuthMetadataInterceptor:
    """Test authentication metadata interceptor."""

    @pytest.mark.asyncio
    async def test_set_user_context(self) -> None:
        """Test setting user context."""
        from zrun_bff.clients.interceptors import set_user_context, get_user_context

        set_user_context("user123", "token456", ["read", "write"])
        ctx = get_user_context()

        assert ctx["user_id"] == "user123"
        assert ctx["token"] == "token456"
        assert ctx["scopes"] == ["read", "write"]

    @pytest.mark.asyncio
    async def test_build_auth_metadata(self) -> None:
        """Test building authentication metadata."""
        from zrun_bff.clients.interceptors import set_user_context, build_auth_metadata

        set_user_context("user123", "token456", ["read", "write"])
        metadata = build_auth_metadata()

        # Convert to list for assertion
        metadata_list = list(metadata)

        assert ("x-user-id", "user123") in metadata_list
        assert ("authorization", "Bearer token456") in metadata_list
        assert ("x-scopes", "read,write") in metadata_list


class TestGrpcClientFactory:
    """Test gRPC client factory."""

    @pytest.mark.asyncio
    async def test_get_client_manager_singleton(self) -> None:
        """Test that client manager is a singleton."""
        from zrun_bff.clients.factory import get_client_manager, GrpcClientManager

        manager1 = get_client_manager()
        manager2 = get_client_manager()

        assert manager1 is manager2
        assert isinstance(manager1, GrpcClientManager)


class TestBaseSkuClient:
    """Test Base SKU client."""

    @pytest.mark.asyncio
    async def test_create_sku_client(self) -> None:
        """Test creating SKU client."""
        from zrun_bff.clients.base import create_sku_client

        mock_channel = MagicMock()

        client = await create_sku_client(mock_channel)

        assert client is not None
        assert client._channel is mock_channel

    @pytest.mark.asyncio
    async def test_create_sku_method(self) -> None:
        """Test SKU creation method."""
        from zrun_bff.clients.base import BaseSkuClient
        from zrun_bff.clients.interceptors import set_user_context

        # Set user context
        set_user_context("test-user", "test-token")

        # Mock the gRPC stub
        mock_channel = MagicMock()
        mock_stub = MagicMock()

        async def mock_create(*args: Any, **kwargs: Any) -> MagicMock:
            response = MagicMock()
            response.sku.id = "123"
            response.sku.code = "SKU001"
            response.sku.name = "Test SKU"
            return response

        mock_stub.CreateSku = mock_create

        patch_path = "zrun_schema.generated.base.sku_pb2_grpc.SkuServiceStub"
        with patch(patch_path, return_value=mock_stub):
            client = BaseSkuClient(mock_channel)

            result = await client.create_sku(
                code="SKU001",
                name="Test SKU",
            )

            assert result["id"] == "123"
            assert result["code"] == "SKU001"
            assert result["name"] == "Test SKU"


class TestDependencies:
    """Test FastAPI dependencies."""

    @pytest.mark.asyncio
    async def test_get_sku_client_dependency(self) -> None:
        """Test SKU client dependency."""
        from zrun_bff.clients.dependencies import get_sku_client

        async def mock_get_channel():
            mock_channel = MagicMock()
            yield mock_channel

        # This is a basic test to ensure the dependency is importable
        assert callable(get_sku_client)


class TestSessionMiddleware:
    """Test session middleware."""

    def test_session_middleware_init(self) -> None:
        """Test session middleware initialization."""
        from zrun_bff.middleware.session import SessionMiddleware

        app = MagicMock()
        middleware = SessionMiddleware(
            app=app,
            secret_key="test-secret-key",
        )

        assert middleware is not None
        assert middleware._session_cookie == "session"
