"""Main entry point for the zrun-base service."""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from zrun_base.config import DatabaseBackend, get_base_config
from zrun_base.logic.sku import SkuLogic
from zrun_base.repository.sku import (
    PostgresSkuRepository,
)
from zrun_base.repository.sku import (
    create_sku_table as create_postgres_sku_table,
)
from zrun_base.repository.sqlite import (
    SqliteSkuRepository,
    get_in_memory_connection,
)
from zrun_base.repository.sqlite import (
    create_sku_table as create_sqlite_sku_table,
)
from zrun_base.servicers.sku_servicer import SkuServicer
from zrun_core.server import BaseGrpcServer


async def create_db_pool(dsn: str) -> Any:
    """Create a database connection pool.

    Args:
        dsn: Database connection string.

    Returns:
        The connection pool.
    """
    import asyncpg

    return await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=10,
    )


async def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, non-zero for failure).
    """
    # Load configuration
    config = get_base_config()

    # Configure logging
    from zrun_core.logging import configure_structlog

    configure_structlog(
        service_name="zrun-base",
        log_level=config.log_level,
        log_format=config.log_format,
    )

    from zrun_core.logging import get_logger

    logger = get_logger()

    logger.info(
        "service_starting",
        env=config.env,
        port=config.port,
        database_backend=config.database_backend.value,
    )

    # Create repository based on configuration
    if config.database_backend == DatabaseBackend.SQLITE:
        # SQLite for testing/development
        logger.info("using_sqlite_backend", path=config.sqlite_path)

        conn = get_in_memory_connection()
        await create_sqlite_sku_table(conn)
        sku_repo: Any = SqliteSkuRepository(conn)
        pool: Any = None
    else:
        # PostgreSQL for production
        try:
            pool = await create_db_pool(config.database_url)
            await create_postgres_sku_table(pool)
            logger.info("database_connected", backend="postgresql")
            sku_repo = PostgresSkuRepository(pool=pool)
        except Exception as e:
            logger.error(
                "database_connection_failed",
                error=str(e),
                hint="Make sure PostgreSQL is running and the connection URL is correct",
            )
            logger.info("service_exiting")
            return 1

    # Create logic
    sku_logic = SkuLogic(repo=sku_repo)

    # Create servicers
    sku_servicer = SkuServicer(logic=sku_logic)

    # Create server
    interceptors = []

    # Add auth interceptor if enabled
    if config.enable_auth:
        from zrun_core.auth import AuthInterceptor

        auth_interceptor = AuthInterceptor(
            jwks_url=config.jwks_url,
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
        )
        interceptors.append(auth_interceptor)

    server = BaseGrpcServer(
        port=config.port,
        interceptors=interceptors,
        max_workers=config.max_workers,
        service_config=config,
    )

    # Register servicers
    from grpc.aio import Server

    if isinstance(server._server, Server):
        from zrun_schema.generated.base import sku_pb2_grpc as base_sku_pb2_grpc

        base_sku_pb2_grpc.add_SkuServiceServicer_to_server(  # type: ignore[no-untyped-call]
            sku_servicer,
            server._server,
        )

    try:
        await server.serve_forever()
    except KeyboardInterrupt:
        logger.info("service_interrupted")
    except Exception:
        logger.exception("service_error")
        return 1
    finally:
        await server.stop()
        if pool is not None:
            await pool.close()
        logger.info("service_stopped")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
