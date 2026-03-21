"""Repository protocol interfaces for zrun-base service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import builtins

    from zrun_base.logic.domain import SkuDomain


class SkuRepositoryProtocol(Protocol):
    """Protocol for SKU repository implementations.

    This protocol defines the interface that any SKU repository
    implementation must follow.
    """

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a new SKU.

        Args:
            sku: The SKU domain object to create.

        Returns:
            The created SKU domain object.
        """
        ...

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object or None if not found.
        """
        ...

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code.

        Args:
            code: The SKU code.

        Returns:
            The SKU domain object or None if not found.
        """
        ...

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update an existing SKU.

        Args:
            sku: The SKU domain object to update.

        Returns:
            The updated SKU domain object.
        """
        ...

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.
        """
        ...

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
        ...
