"""gRPC servicer for SKU operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from zrun_base.logic.domain import CreateSkuInput, SkuDomain, UpdateSkuInput
from zrun_core import USER_ID_CTX_KEY, get_async_transaction, get_logger
from zrun_core.errors import abort_with_error
from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from contextlib import AbstractAsyncContextManager

    from grpc.aio import ServicerContext
    from sqlalchemy.ext.asyncio import AsyncSession

    from zrun_base.logic.sku import SkuLogic
    from zrun_base.repository.protocols import SkuRepositoryProtocol

logger = get_logger()


def _domain_to_proto(sku: SkuDomain) -> Any:
    """Convert a SkuDomain to protobuf SKU message.

    Args:
        sku: The SKU domain object.

    Returns:
        A protobuf SKU message.
    """
    return base_sku_pb2.Sku(
        id=sku.id,
        code=sku.code,
        name=sku.name,
        created_at=int(sku.created_at.timestamp() * 1000),
        updated_at=int(sku.updated_at.timestamp() * 1000) if sku.updated_at else 0,
    )


class SkuServicer:
    """gRPC servicer for SKU operations.

    This servicer handles gRPC requests and maps them to the logic layer.
    It is responsible for:
    - Extracting user context from the gRPC context
    - Managing database transactions (one per request)
    - Converting between protobuf and domain objects
    - Handling gRPC-specific concerns (aborting, status codes)
    """

    def __init__(
        self,
        logic: SkuLogic,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    ) -> None:
        """Initialize the servicer.

        Args:
            logic: The SKU business logic instance.
            session_factory: Factory function to create database sessions.
        """
        self._logic = logic
        self._session_factory = session_factory

    async def _with_repo[R](
        self,
        coro: Callable[[SkuRepositoryProtocol], Awaitable[R]],
    ) -> R:
        """Execute a coroutine with a request-scoped repository in a transaction.

        Temporarily replaces the logic's repository to ensure transaction
        isolation per request.

        Args:
            coro: Coroutine that takes a repository and returns a result.

        Returns:
            The result of the coroutine.
        """
        from zrun_base.repository.repos import SkuRepository

        original_repo = self._logic._repo
        async with self._session_factory() as session, get_async_transaction(session):
            repo = SkuRepository(session)
            self._logic._repo = repo
            try:
                return await coro(repo)
            finally:
                self._logic._repo = original_repo

    async def CreateSku(
        self,
        request: base_sku_pb2.CreateSkuRequest,
        context: ServicerContext,
    ) -> base_sku_pb2.CreateSkuResponse:
        """Create a new SKU.

        Args:
            request: The CreateSkuRequest protobuf message.
            context: The gRPC servicer context.

        Returns:
            The CreateSkuResponse protobuf message.
        """
        user_id = USER_ID_CTX_KEY.get()

        logger.info(
            "create_sku_request",
            code=request.code,
            name=request.name,
            user_id=user_id,
        )

        try:
            input = CreateSkuInput(
                code=request.code,
                name=request.name,
            )

            sku = await self._with_repo(lambda _: self._logic.create_sku(input))

            logger.info("create_sku_success", sku_id=sku.id, user_id=user_id)

            return base_sku_pb2.CreateSkuResponse(
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("create_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def GetSku(
        self,
        request: base_sku_pb2.GetSkuRequest,
        context: ServicerContext,
    ) -> base_sku_pb2.GetSkuResponse:
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
            sku = await self._with_repo(lambda _: self._logic.get_sku(request.sku_id))

            logger.info("get_sku_success", sku_id=sku.id, user_id=user_id)

            return base_sku_pb2.GetSkuResponse(
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("get_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def UpdateSku(
        self,
        request: base_sku_pb2.UpdateSkuRequest,
        context: ServicerContext,
    ) -> base_sku_pb2.UpdateSkuResponse:
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

            sku = await self._with_repo(lambda _: self._logic.update_sku(input))

            logger.info("update_sku_success", sku_id=sku.id, user_id=user_id)

            return base_sku_pb2.UpdateSkuResponse(
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("update_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def DeleteSku(
        self,
        request: base_sku_pb2.DeleteSkuRequest,
        context: ServicerContext,
    ) -> base_sku_pb2.DeleteSkuResponse:
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
            await self._with_repo(lambda _: self._logic.delete_sku(request.sku_id))

            logger.info("delete_sku_success", sku_id=request.sku_id, user_id=user_id)

            return base_sku_pb2.DeleteSkuResponse()

        except Exception as e:
            logger.error("delete_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def ListSkus(
        self,
        request: base_sku_pb2.ListSkusRequest,
        context: ServicerContext,
    ) -> base_sku_pb2.ListSkusResponse:
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
            offset = int(request.page_token) if request.page_token else 0
            limit = request.page_size if request.page_size > 0 else 100

            skus = await self._with_repo(lambda repo: repo.list(limit=limit, offset=offset))

            next_offset = offset + len(skus)
            next_page_token = str(next_offset) if len(skus) == limit else ""

            logger.info(
                "list_skus_success",
                count=len(skus),
                next_page_token=next_page_token,
                user_id=user_id,
            )

            return base_sku_pb2.ListSkusResponse(
                skus=[_domain_to_proto(sku) for sku in skus],
                next_page_token=next_page_token,
            )

        except Exception as e:
            logger.error("list_skus_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)
