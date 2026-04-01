"""SQLAlchemy 2.0 implementation of SKU repository."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from zrun_core.errors import ConflictError, NotFoundError

if TYPE_CHECKING:
    import builtins

    from sqlalchemy.ext.asyncio import AsyncSession

    from zrun_base.logic.domain import SkuDomain


class SkuRepository:
    """SQLAlchemy 2.0 async implementation of SKU repository.

    This implementation works with both PostgreSQL (asyncpg) and
    SQLite (aiosqlite) using SQLAlchemy's unified async API.

    Architecture Note:
        - Receives AsyncSession from Servicer layer
        - Converts between SkuModel and SkuDomain
        - Maps database exceptions to domain errors
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            session: SQLAlchemy async session (managed by caller).
        """
        self._session = session

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a new SKU.

        Args:
            sku: The SKU domain object to create.

        Returns:
            The created SKU domain object with database defaults.

        Raises:
            ConflictError: If SKU code already exists.
        """
        from zrun_base.repository.models import SkuModel

        model = SkuModel.from_domain(sku)

        self._session.add(model)

        try:
            await self._session.flush()
        except IntegrityError as e:
            msg = f"SKU with code '{sku.code}' already exists"
            raise ConflictError(msg) from e

        return model.to_domain()

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object or None if not found.
        """
        from zrun_base.repository.models import SkuModel

        stmt = select(SkuModel).where(SkuModel.id == sku_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return model.to_domain() if model else None

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code.

        Args:
            code: The SKU code.

        Returns:
            The SKU domain object or None if not found.
        """
        from zrun_base.repository.models import SkuModel

        stmt = select(SkuModel).where(SkuModel.code == code)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        return model.to_domain() if model else None

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update an existing SKU.

        Args:
            sku: The SKU domain object to update.

        Returns:
            The updated SKU domain object.

        Raises:
            NotFoundError: If SKU doesn't exist.
            ConflictError: If new code conflicts with another SKU.
        """
        from zrun_base.repository.models import SkuModel

        stmt = select(SkuModel).where(SkuModel.id == sku.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            msg = f"SKU with ID '{sku.id}' not found"
            raise NotFoundError(msg)

        # Update fields
        model.code = sku.code
        model.name = sku.name
        model.updated_at = sku.updated_at

        try:
            await self._session.flush()
        except IntegrityError as e:
            msg = f"SKU with code '{sku.code}' already exists"
            raise ConflictError(msg) from e

        return model.to_domain()

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.

        Raises:
            NotFoundError: If SKU doesn't exist.
        """
        from zrun_base.repository.models import SkuModel

        stmt = select(SkuModel).where(SkuModel.id == sku_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if model is None:
            msg = f"SKU with ID '{sku_id}' not found"
            raise NotFoundError(msg)

        await self._session.delete(model)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> builtins.list[SkuDomain]:
        """List SKUs with pagination.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of SKU domain objects.
        """
        from zrun_base.repository.models import SkuModel

        stmt = select(SkuModel).order_by(SkuModel.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        models = result.scalars().all()

        return [model.to_domain() for model in models]
