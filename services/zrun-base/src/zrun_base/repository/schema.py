"""Database schema creation and management for zrun-base."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


async def create_sku_table(engine: AsyncEngine) -> None:
    """Create the skus table if it doesn't exist.

    This function uses SQLAlchemy's metadata to create the table
    with the correct schema for both PostgreSQL and SQLite.

    Args:
        engine: SQLAlchemy async engine.
    """
    from zrun_base.repository.models import SkuModel

    async with engine.begin() as conn:
        await conn.run_sync(SkuModel.metadata.create_all)
