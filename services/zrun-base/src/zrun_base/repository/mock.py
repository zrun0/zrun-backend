"""Mock SKU repository for testing without a database."""

from __future__ import annotations

from zrun_base.logic.sku import SkuDomain


class MockSkuRepository:
    """In-memory mock SKU repository for testing.

    This implementation stores SKUs in memory and is useful for
    testing without requiring a database connection.
    """

    def __init__(self) -> None:
        """Initialize the mock repository."""
        self._skus: dict[str, SkuDomain] = {}
        self._code_index: dict[str, SkuDomain] = {}

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a new SKU.

        Args:
            sku: The SKU domain object to create.

        Returns:
            The created SKU domain object.
        """
        self._skus[sku.id] = sku
        self._code_index[sku.code] = sku
        return sku

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object or None if not found.
        """
        return self._skus.get(sku_id)

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code.

        Args:
            code: The SKU code.

        Returns:
            The SKU domain object or None if not found.
        """
        return self._code_index.get(code)

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update an existing SKU.

        Args:
            sku: The SKU domain object to update.

        Returns:
            The updated SKU domain object.
        """
        if sku.id not in self._skus:
            msg = f"SKU {sku.id} not found"
            raise ValueError(msg)

        # Update code index if code changed
        old_sku = self._skus[sku.id]
        if old_sku.code != sku.code:
            del self._code_index[old_sku.code]
            self._code_index[sku.code] = sku

        self._skus[sku.id] = sku
        return sku

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.
        """
        sku = self._skus.pop(sku_id, None)
        if sku:
            self._code_index.pop(sku.code, None)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuDomain]:
        """List SKUs with pagination.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of SKU domain objects.
        """
        skus = list(self._skus.values())
        return skus[offset : offset + limit]
