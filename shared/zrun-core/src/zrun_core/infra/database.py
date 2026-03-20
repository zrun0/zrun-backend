"""Shared SQLAlchemy 2.0 utilities for zrun services."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as sqlalchemy_create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models.

    All service models should inherit from this class to get:
    - Automatic table name generation
    - Common metadata registry
    - Declarative mapping with SQLAlchemy 2.0 syntax
    """


class TimestampMixin:
    """Add timestamp columns to models.

    This mixin provides automatic timestamp management for all models.
    All timestamps are stored in UTC timezone as required by CLAUDE.md.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )


def create_async_engine(
    database_url: str,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    Args:
        database_url: Database connection URL with async driver:
            - PostgreSQL: "postgresql+asyncpg://..."
            - SQLite: "sqlite+aiosqlite://..."
        pool_size: Connection pool size (PostgreSQL only).
        max_overflow: Maximum overflow connections (PostgreSQL only).

    Returns:
        Configured async engine.
    """

    if database_url.startswith("sqlite"):
        # SQLite doesn't support connection pooling
        return sqlalchemy_create_async_engine(
            database_url,
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )

    # PostgreSQL with connection pooling
    return sqlalchemy_create_async_engine(
        database_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,  # Verify connections before using
    )


@asynccontextmanager
async def get_async_session(
    engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession]:
    """Get a managed async session.

    This context manager handles session lifecycle and ensures proper cleanup.
    Transactions should be managed in the Servicer layer using session.begin().

    Args:
        engine: SQLAlchemy async engine.

    Yields:
        Async session instance.

    Example:
        async with get_async_session(engine) as session:
            async with session.begin():
                result = await session.execute(...)
    """
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        yield session


@asynccontextmanager
async def get_async_transaction(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSessionTransaction]:
    """Get a managed async transaction.

    This is a convenience wrapper for transaction management.

    Args:
        session: Async session.

    Yields:
        Active transaction.

    Example:
        async with get_async_session(engine) as session:
            async with get_async_transaction(session):
                # Perform database operations
                pass
    """
    async with session.begin() as transaction:
        yield transaction
