"""Main entry point for the zrun-base service."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from zrun_base.config import DatabaseBackend, get_base_config
from zrun_base.logic.sku import SkuLogic
from zrun_base.repository.repos import SkuRepository
from zrun_base.repository.schema import create_sku_table
from zrun_base.servicers.sku_servicer import SkuServicer
from zrun_core import create_async_engine, get_async_session, run_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


def create_session_factory(
    engine: AsyncEngine,
) -> SessionFactory:
    """Create a session factory for servicers.

    Args:
        engine: SQLAlchemy async engine.

    Returns:
        A factory function that yields sessions.
    """

    @asynccontextmanager
    async def _factory():
        async with get_async_session(engine) as session:
            yield session

    return _factory


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    config = get_base_config()

    # Configure database
    db_url = (
        f"sqlite+aiosqlite:///{config.sqlite_path.lstrip(':')}"
        if config.database_backend == DatabaseBackend.SQLITE
        else config.database_url
    )

    engine = create_async_engine(
        db_url,
        pool_size=config.database_pool_size,
        max_overflow=config.database_max_overflow,
    )

    await create_sku_table(engine)

    # Create servicers
    async with get_async_session(engine) as session:
        sku_repo = SkuRepository(session=session)
        sku_logic = SkuLogic(repo=sku_repo)

        session_factory = create_session_factory(engine)
        sku_servicer = SkuServicer(logic=sku_logic, session_factory=session_factory)

        # Register servicers with their gRPC classes
        from zrun_schema.generated.base import sku_pb2_grpc as base_sku_pb2_grpc

        servicers = [
            (base_sku_pb2_grpc.add_SkuServiceServicer_to_server, sku_servicer),
        ]

        # Run service (handles logging, server, lifecycle)
        return await run_service(
            servicers=servicers,
            config=config,
            engine=engine,
            service_name="zrun-base",
        )


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
