"""Repository layer for SKU persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import asyncpg

from zrun_base.logic.sku import SkuDomain


class SkuRepository(Protocol):
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
    ) -> list[SkuDomain]:
        """List SKUs with pagination.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of SKU domain objects.
        """
        ...


@dataclass
class PostgresSkuRepository:
    """PostgreSQL implementation of SKU repository.

    This implementation uses asyncpg for async database operations.
    """

    pool: asyncpg.Pool

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a new SKU in the database.

        Args:
            sku: The SKU domain object to create.

        Returns:
            The created SKU domain object.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO skus (id, code, name, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, code, name, created_at, updated_at
                """,
                sku.id,
                sku.code,
                sku.name,
                sku.created_at,
                sku.updated_at,
            )

            return self._row_to_domain(row)

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID from the database.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, code, name, created_at, updated_at
                FROM skus
                WHERE id = $1
                """,
                sku_id,
            )

            if row is None:
                return None

            return self._row_to_domain(row)

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code from the database.

        Args:
            code: The SKU code.

        Returns:
            The SKU domain object or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, code, name, created_at, updated_at
                FROM skus
                WHERE code = $1
                """,
                code,
            )

            if row is None:
                return None

            return self._row_to_domain(row)

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update an existing SKU in the database.

        Args:
            sku: The SKU domain object to update.

        Returns:
            The updated SKU domain object.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE skus
                SET code = $2, name = $3, updated_at = $4
                WHERE id = $1
                RETURNING id, code, name, created_at, updated_at
                """,
                sku.id,
                sku.code,
                sku.name,
                sku.updated_at,
            )

            if row is None:
                msg = f"SKU with ID {sku.id} not found"
                raise ValueError(msg)

            return self._row_to_domain(row)

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU from the database.

        Args:
            sku_id: The SKU ID.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM skus
                WHERE id = $1
                """,
                sku_id,
            )

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[SkuDomain]:
        """List SKUs from the database with pagination.

        Args:
            limit: Maximum number of results to return.
            offset: Number of results to skip.

        Returns:
            List of SKU domain objects.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, code, name, created_at, updated_at
                FROM skus
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )

            return [self._row_to_domain(row) for row in rows]

    @staticmethod
    def _row_to_domain(row: asyncpg.Record) -> SkuDomain:
        """Convert a database row to a SkuDomain object.

        Args:
            row: The database row.

        Returns:
            A SkuDomain object.
        """
        return SkuDomain(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


async def create_sku_table(pool: asyncpg.Pool) -> None:
    """Create the skus table if it doesn't exist.

    Args:
        pool: The database connection pool.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skus (
                id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ
            );

            CREATE INDEX IF NOT EXISTS idx_skus_code ON skus(code);
            CREATE INDEX IF NOT EXISTS idx_skus_created_at ON skus(created_at DESC);
            """
        )
