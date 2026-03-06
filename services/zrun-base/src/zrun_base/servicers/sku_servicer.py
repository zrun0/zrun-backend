"""gRPC servicer for SKU operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zrun_base.logic.sku import CreateSkuInput, SkuDomain, SkuLogic, UpdateSkuInput
from zrun_core import USER_ID_CTX_KEY, get_logger
from zrun_core.errors import abort_with_error

if TYPE_CHECKING:
    from grpc.aio import ServicerContext

logger = get_logger()


def _domain_to_proto(sku: SkuDomain) -> Any:
    """Convert a SkuDomain to protobuf SKU message.

    Args:
        sku: The SKU domain object.

    Returns:
        A protobuf SKU message.
    """
    # Import here to avoid circular imports
    from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

    return base_sku_pb2.Sku(  # type: ignore[attr-defined]
        id=sku.id,
        code=sku.code,
        name=sku.name,
        created_at=int(sku.created_at.timestamp() * 1000),
        updated_at=int(sku.updated_at.timestamp() * 1000) if sku.updated_at else 0,
    )


def _proto_to_timestamp(timestamp_ms: int) -> datetime:
    """Convert protobuf timestamp to datetime.

    Args:
        timestamp_ms: Timestamp in milliseconds.

    Returns:
        A datetime object.
    """
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


class SkuServicer:
    """gRPC servicer for SKU operations.

    This servicer handles gRPC requests and maps them to the logic layer.
    It is responsible for:
    - Extracting user context from the gRPC context
    - Converting between protobuf and domain objects
    - Handling gRPC-specific concerns (aborting, status codes)
    """

    def __init__(self, logic: SkuLogic) -> None:
        """Initialize the servicer.

        Args:
            logic: The SKU business logic instance.
        """
        self._logic = logic

    async def CreateSku(
        self,
        request: Any,
        context: ServicerContext,
    ) -> Any:
        """Create a new SKU.

        Args:
            request: The CreateSkuRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            The CreateSkuResponse protobuf message.
        """
        # Extract user ID from context
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "create_sku_request",
            code=request.code,
            name=request.name,
            user_id=user_id,
        )

        try:
            # Convert to domain input
            input = CreateSkuInput(
                code=request.code,
                name=request.name,
            )

            # Call logic layer
            sku = await self._logic.create_sku(input)

            logger.info("create_sku_success", sku_id=sku.id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            # Convert back to protobuf response
            return base_sku_pb2.CreateSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("create_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def GetSku(
        self,
        request: Any,
        context: ServicerContext,
    ) -> Any:
        """Get an existing SKU by ID.

        Args:
            request: The GetSkuRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            The GetSkuResponse protobuf message.
        """
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "get_sku_request",
            sku_id=request.sku_id,
            user_id=user_id,
        )

        try:
            sku = await self._logic.get_sku(request.sku_id)

            logger.info("get_sku_success", sku_id=sku.id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.GetSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("get_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def UpdateSku(
        self,
        request: Any,
        context: ServicerContext,
    ) -> Any:
        """Update an existing SKU.

        Args:
            request: The UpdateSkuRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            The UpdateSkuResponse protobuf message.
        """
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "update_sku_request",
            sku_id=request.sku_id,
            user_id=user_id,
        )

        try:
            input = UpdateSkuInput(
                id=request.sku_id,
                code=request.code if request.code else None,
                name=request.name if request.name else None,
            )

            sku = await self._logic.update_sku(input)

            logger.info("update_sku_success", sku_id=sku.id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.UpdateSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("update_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def DeleteSku(
        self,
        request: Any,
        context: ServicerContext,
    ) -> Any:
        """Delete an SKU.

        Args:
            request: The DeleteSkuRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            A DeleteSkuResponse message.
        """
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "delete_sku_request",
            sku_id=request.sku_id,
            user_id=user_id,
        )

        try:
            await self._logic.delete_sku(request.sku_id)

            logger.info("delete_sku_success", sku_id=request.sku_id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.DeleteSkuResponse()  # type: ignore[attr-defined]

        except Exception as e:
            logger.error("delete_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def ListSkus(
        self,
        request: Any,
        context: ServicerContext,
    ) -> Any:
        """List SKUs with pagination.

        Args:
            request: The ListSkusRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            The ListSkusResponse protobuf message.
        """
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "list_skus_request",
            page_size=request.page_size,
            page_token=request.page_token,
            user_id=user_id,
        )

        try:
            # For simplicity, we're not implementing full pagination
            # In production, use a proper token-based pagination

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.ListSkusResponse(  # type: ignore[attr-defined]
                skus=[],
                next_page_token="",
            )

        except Exception as e:
            logger.error("list_skus_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)
