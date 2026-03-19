"""gRPC servicer for SKU operations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from zrun_base.logic.domain import CreateSkuInput, SkuDomain, UpdateSkuInput
from zrun_core import USER_ID_CTX_KEY, get_async_transaction, get_logger
from zrun_core.domain import abort_with_error

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from grpc.aio import ServicerContext
    from sqlalchemy.ext.asyncio import AsyncSession

    from zrun_base.logic.sku import SkuLogic
    from zrun_base.repository.protocols import SkuRepositoryProtocol

logger = get_logger()


def _domain_to_proto(sku: SkuDomain) -> Any:  # type: ignore[no-any-return]
    """Convert a SkuDomain to protobuf SKU message.

    Args:
        sku: The SKU domain object.

    Returns:
        A protobuf SKU message.
    """
    # Import here to avoid circular imports
    from zrun_schema.generated.base import sku_pb2 as base_sku_pb2  # type: ignore[import]

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

    async def _with_repo(
        self,
        coro: Callable[[SkuRepositoryProtocol], Any],
    ) -> Any:
        """Execute a coroutine with a repository in a transaction.

        Args:
            coro: Coroutine that takes a repository and returns a result.

        Returns:
            The result of the coroutine.

        Raises:
            Exception: Any exception from the coroutine is propagated.
        """
        from zrun_base.repository.repos import SkuRepository

        async with self._session_factory() as session, get_async_transaction(session):
            repo = SkuRepository(session)
            return await coro(repo)

    async def CreateSku(
        self,
        request: Any,
        context: ServicerContext[Any, Any],  # type: ignore[misc]
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
            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            input = CreateSkuInput(
                code=request.code,
                name=request.name,
            )

            sku = await self._with_repo(lambda repo: self._create_sku(repo, input))

            logger.info("create_sku_success", sku_id=sku.id, user_id=user_id)

            return base_sku_pb2.CreateSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("create_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def _create_sku(
        self,
        repo: SkuRepositoryProtocol,
        input: CreateSkuInput,
    ) -> SkuDomain:
        """Create a SKU with the given repository.

        Args:
            repo: The SKU repository.
            input: The input data.

        Returns:
            The created SKU domain object.
        """
        # Temporarily replace the logic's repository
        original_repo = self._logic._repo
        self._logic._repo = repo
        try:
            return await self._logic.create_sku(input)
        finally:
            self._logic._repo = original_repo

    async def GetSku(
        self,
        request: Any,
        context: ServicerContext[Any, Any],  # type: ignore[misc]
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
            sku = await self._with_repo(lambda repo: self._get_sku(repo, request.sku_id))

            logger.info("get_sku_success", sku_id=sku.id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.GetSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("get_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def _get_sku(
        self,
        repo: SkuRepositoryProtocol,
        sku_id: str,
    ) -> SkuDomain:
        """Get a SKU with the given repository.

        Args:
            repo: The SKU repository.
            sku_id: The SKU ID.

        Returns:
            The SKU domain object.
        """
        original_repo = self._logic._repo
        self._logic._repo = repo
        try:
            return await self._logic.get_sku(sku_id)
        finally:
            self._logic._repo = original_repo

    async def UpdateSku(
        self,
        request: Any,
        context: ServicerContext[Any, Any],  # type: ignore[misc]
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

            sku = await self._with_repo(lambda repo: self._update_sku(repo, input))

            logger.info("update_sku_success", sku_id=sku.id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.UpdateSkuResponse(  # type: ignore[attr-defined]
                sku=_domain_to_proto(sku),
            )

        except Exception as e:
            logger.error("update_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def _update_sku(
        self,
        repo: SkuRepositoryProtocol,
        input: UpdateSkuInput,
    ) -> SkuDomain:
        """Update a SKU with the given repository.

        Args:
            repo: The SKU repository.
            input: The input data.

        Returns:
            The updated SKU domain object.
        """
        original_repo = self._logic._repo
        self._logic._repo = repo
        try:
            return await self._logic.update_sku(input)
        finally:
            self._logic._repo = original_repo

    async def DeleteSku(
        self,
        request: Any,
        context: ServicerContext[Any, Any],  # type: ignore[misc]
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
            await self._with_repo(lambda repo: self._delete_sku(repo, request.sku_id))

            logger.info("delete_sku_success", sku_id=request.sku_id, user_id=user_id)

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.DeleteSkuResponse()  # type: ignore[attr-defined]

        except Exception as e:
            logger.error("delete_sku_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def _delete_sku(
        self,
        repo: SkuRepositoryProtocol,
        sku_id: str,
    ) -> None:
        """Delete a SKU with the given repository.

        Args:
            repo: The SKU repository.
            sku_id: The SKU ID.
        """
        original_repo = self._logic._repo
        self._logic._repo = repo
        try:
            await self._logic.delete_sku(sku_id)
        finally:
            self._logic._repo = original_repo

    async def ListSkus(
        self,
        request: Any,
        context: ServicerContext[Any, Any],  # type: ignore[misc]
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
            # Parse page token as offset (default to 0)
            offset = 0
            if request.page_token:
                try:
                    offset = int(request.page_token)
                except ValueError:
                    offset = 0

            # Use page_size as limit (default to 100)
            limit = request.page_size if request.page_size > 0 else 100

            skus = await self._with_repo(
                lambda repo: self._list_skus(repo, limit, offset),
            )

            # Generate next page token
            next_offset = offset + len(skus)
            next_page_token = str(next_offset) if len(skus) == limit else ""

            logger.info(
                "list_skus_success",
                count=len(skus),
                next_page_token=next_page_token,
                user_id=user_id,
            )

            # Import here to avoid circular imports
            from zrun_schema.generated.base import sku_pb2 as base_sku_pb2

            return base_sku_pb2.ListSkusResponse(  # type: ignore[attr-defined]
                skus=[_domain_to_proto(sku) for sku in skus],
                next_page_token=next_page_token,
            )

        except Exception as e:
            logger.error("list_skus_failed", error=str(e), user_id=user_id)
            abort_with_error(context, e)

    async def _list_skus(
        self,
        repo: SkuRepositoryProtocol,
        limit: int,
        offset: int,
    ) -> list[SkuDomain]:
        """List SKUs with the given repository.

        Args:
            repo: The SKU repository.
            limit: Maximum number of results.
            offset: Number of results to skip.

        Returns:
            List of SKU domain objects.
        """
        return await repo.list(limit=limit, offset=offset)
