"""SQLite repository for testing and development."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from zrun_base.logic.sku import SkuDomain

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class SkuRow:
    """SKU database row representation."""

    id: str
    code: str
    name: str
    created_at: str
    updated_at: str | None = None


class SqliteSkuRepository:
    """SQLite implementation of SKU repository.

    This implementation uses SQLite for testing and development.
    It stores data in memory for tests or in a file for development.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Initialize the SQLite repository.

        Args:
            connection: SQLite connection.
        """
        self._conn = connection

    async def create(self, sku: SkuDomain) -> SkuDomain:
        """Create a new SKU.

        Args:
            sku: The SKU domain object to create.

        Returns:
            The created SKU domain object.
        """
        cursor = self._conn.cursor()

        created_at_ts = int(sku.created_at.timestamp() * 1000)
        updated_at_ts = int(sku.updated_at.timestamp() * 1000) if sku.updated_at else None

        cursor.execute(
            """
            INSERT INTO skus (id, code, name, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (sku.id, sku.code, sku.name, created_at_ts, updated_at_ts),
        )
        self._conn.commit()

        return sku

    async def get_by_id(self, sku_id: str) -> SkuDomain | None:
        """Get a SKU by ID.

        Args:
            sku_id: The SKU ID.

        Returns:
            The SKU domain object or None if not found.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, code, name, created_at, updated_at
            FROM skus
            WHERE id = ?
            """,
            (sku_id,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_domain(row)

    async def get_by_code(self, code: str) -> SkuDomain | None:
        """Get a SKU by code.

        Args:
            code: The SKU code.

        Returns:
            The SKU domain object or None if not found.
        """
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, code, name, created_at, updated_at
            FROM skus
            WHERE code = ?
            """,
            (code,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_domain(row)

    async def update(self, sku: SkuDomain) -> SkuDomain:
        """Update an existing SKU.

        Args:
            sku: The SKU domain object to update.

        Returns:
            The updated SKU domain object.
        """
        cursor = self._conn.cursor()

        updated_at_ts = int(sku.updated_at.timestamp() * 1000) if sku.updated_at else None

        cursor.execute(
            """
            UPDATE skus
            SET code = ?, name = ?, updated_at = ?
            WHERE id = ?
            """,
            (sku.code, sku.name, updated_at_ts, sku.id),
        )
        self._conn.commit()

        return sku

    async def delete(self, sku_id: str) -> None:
        """Delete a SKU.

        Args:
            sku_id: The SKU ID.
        """
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM skus WHERE id = ?", (sku_id,))
        self._conn.commit()

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
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT id, code, name, created_at, updated_at
            FROM skus
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )

        rows = cursor.fetchall()
        return [self._row_to_domain(row) for row in rows]

    @staticmethod
    def _row_to_domain(row: tuple[str, str, str, int, int | None]) -> SkuDomain:
        """Convert a database row to a SkuDomain object.

        Args:
            row: The database row.

        Returns:
            A SkuDomain object.
        """
        return SkuDomain(
            id=row[0],
            code=row[1],
            name=row[2],
            created_at=datetime.fromtimestamp(row[3] / 1000, tz=UTC),
            updated_at=datetime.fromtimestamp(row[4] / 1000, tz=UTC) if row[4] else None,
        )


async def create_sku_table(conn: sqlite3.Connection) -> None:
    """Create the skus table if it doesn't exist.

    Args:
        conn: SQLite connection.
    """
    cursor = conn.cursor()

    # Execute each statement separately (SQLite limitation)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS skus (
            id TEXT PRIMARY KEY,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER
        );
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_skus_code ON skus(code);
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_skus_created_at ON skus(created_at DESC);
        """
    )

    conn.commit()


def get_in_memory_connection() -> sqlite3.Connection:
    """Get an in-memory SQLite connection for testing.

    Returns:
        SQLite connection.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_file_connection(db_path: str | Path) -> sqlite3.Connection:
    """Get a file-based SQLite connection.

    Args:
        db_path: Path to the database file.

    Returns:
        SQLite connection.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
