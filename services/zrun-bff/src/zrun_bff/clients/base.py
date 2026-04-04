"""Base SKU service client for BFF.

This module provides a high-level client wrapper for the zrun-base
SKU service gRPC API.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from structlog import get_logger

if TYPE_CHECKING:
    from grpc.aio import Channel

from zrun_bff.clients.interceptors import build_auth_metadata
from zrun_bff.clients.utils import handle_grpc_error

logger = get_logger()


class BaseSkuClient:
    """Client for Base SKU service gRPC API.

    Provides a high-level interface for calling SKU service methods
    with automatic authentication metadata injection.

    Args:
        channel: gRPC channel for communication.
    """

    def __init__(self, channel: Channel) -> None:
        self._channel = channel

        # Import generated gRPC stubs
        from zrun_schema.generated.base import sku_pb2, sku_pb2_grpc

        self._sku_pb2 = sku_pb2
        self._stub = sku_pb2_grpc.SkuServiceStub(channel)

    @handle_grpc_error
    async def create_sku(
        self,
        code: str,
        name: str,
    ) -> dict[str, Any]:
        """Create a new SKU.

        Args:
            code: Unique SKU code.
            name: SKU display name.

        Returns:
            Created SKU data.

        Raises:
            ValidationError: If request validation fails.
            ConflictError: If SKU already exists.
            InternalError: If SKU creation fails.
        """
        request = self._sku_pb2.CreateSkuRequest(  # type: ignore[attr-defined]
            code=code,
            name=name,
        )

        metadata = build_auth_metadata()
        response = await self._stub.CreateSku(request, metadata=metadata)

        logger.info("sku_created", id=response.sku.id, code=code)

        return {
            "id": response.sku.id,
            "code": response.sku.code,
            "name": response.sku.name,
        }

    @handle_grpc_error
    async def get_sku(self, sku_id: str) -> dict[str, Any] | None:
        """Get SKU by ID.

        Args:
            sku_id: SKU internal ID.

        Returns:
            SKU data or None if not found.

        Raises:
            ValidationError: If SKU ID is invalid.
            NotFoundError: If SKU not found.
            InternalError: If SKU fetch fails.
        """
        request = self._sku_pb2.GetSkuRequest(sku_id=sku_id)  # type: ignore[attr-defined]

        metadata = build_auth_metadata()
        response = await self._stub.GetSku(request, metadata=metadata)

        if not response.sku.id:
            return None

        return {
            "id": response.sku.id,
            "code": response.sku.code,
            "name": response.sku.name,
        }

    @handle_grpc_error
    async def list_skus(
        self,
        page_size: int = 50,
        page_token: str = "",
    ) -> dict[str, Any]:
        """List SKUs with pagination.

        Args:
            page_size: Number of items per page.
            page_token: Pagination token.

        Returns:
            Paginated SKU list.

        Raises:
            ValidationError: If pagination parameters are invalid.
            ServiceUnavailableError: If SKU service is unavailable.
            InternalError: If SKU list fails.
        """
        request = self._sku_pb2.ListSkusRequest(  # type: ignore[attr-defined]
            page_size=page_size,
            page_token=page_token,
        )

        metadata = build_auth_metadata()
        response = await self._stub.ListSkus(request, metadata=metadata)

        return {
            "items": [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                }
                for item in response.skus
            ],
            "next_page_token": response.next_page_token,
        }

    @handle_grpc_error
    async def update_sku(
        self,
        sku_id: str,
        code: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Update SKU.

        Args:
            sku_id: SKU internal ID.
            code: New SKU code.
            name: New display name.

        Returns:
            Updated SKU data.

        Raises:
            ValidationError: If request validation fails.
            NotFoundError: If SKU not found.
            ConflictError: If SKU code conflicts.
            InternalError: If SKU update fails.
        """
        request = self._sku_pb2.UpdateSkuRequest(  # type: ignore[attr-defined]
            sku_id=sku_id,
            code=code or "",
            name=name or "",
        )

        metadata = build_auth_metadata()
        response = await self._stub.UpdateSku(request, metadata=metadata)

        logger.info("sku_updated", id=response.sku.id)

        return {
            "id": response.sku.id,
            "code": response.sku.code,
            "name": response.sku.name,
        }

    @handle_grpc_error
    async def delete_sku(self, sku_id: str) -> None:
        """Delete SKU by ID.

        Args:
            sku_id: SKU internal ID.

        Raises:
            ValidationError: If SKU ID is invalid.
            NotFoundError: If SKU not found.
            InternalError: If SKU deletion fails.
        """
        request = self._sku_pb2.DeleteSkuRequest(sku_id=sku_id)  # type: ignore[attr-defined]

        metadata = build_auth_metadata()
        await self._stub.DeleteSku(request, metadata=metadata)

        logger.info("sku_deleted", id=sku_id)


async def create_sku_client(channel: Channel) -> BaseSkuClient:
    """Create a Base SKU service client.

    Factory function for creating a SKU client with the given channel.

    Args:
        channel: gRPC channel for communication.

    Returns:
        Configured BaseSkuClient instance.

    Example:
        ```python
        from zrun_bff.clients.factory import get_client_manager

        manager = get_client_manager()
        async with manager.base_channel_context() as channel:
            client = await create_sku_client(channel)
            sku = await client.get_sku(123)
        ```
    """
    return BaseSkuClient(channel)
