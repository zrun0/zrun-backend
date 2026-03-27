"""FastAPI application entry point for zrun-bff service."""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from structlog import get_logger

from zrun_bff.config import BFFConfig

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger()


def get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    from functools import lru_cache

    @lru_cache
    def _get_config() -> BFFConfig:
        return BFFConfig()

    return _get_config()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    config = get_config()
    logger.info(
        "bff_starting",
        service="zrun-bff",
        version="0.1.0-dev",
        env=config.env,
    )
    yield
    logger.info("bff_shutting_down")


def create_app(config: BFFConfig | None = None) -> FastAPI:
    """Create and configure FastAPI application.

    Args:
        config: BFF configuration. If None, loads from environment.

    Returns:
        Configured FastAPI application.
    """
    if config is None:
        config = get_config()

    app = FastAPI(
        title="Zrun BFF",
        description="Backend For Frontend service for zrun WMS",
        version="0.1.0-dev",
        lifespan=lifespan,
    )

    # CORS middleware
    from fastapi.middleware.cors import CORSMiddleware

    CORSMiddleware(  # Workaround for ty type checker issue
        app,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint.

        Returns:
            Health status response.
        """
        return {"status": "healthy", "service": "zrun-bff"}

    # TODO: Register routers
    # - OAuth2 routes (/auth/login, /auth/callback)
    # - JWKS endpoint (/.well-known/jwks.json)
    # - PDA routes (/api/pda/*)
    # - Web admin routes (/api/web/*)
    # - Mini app routes (/api/mini/*)

    return app


# Global app instance for uvicorn
app = create_app()


async def main() -> None:
    """Main entry point for running the service.

    This is called by the `zrun-bff` console script.
    """
    import uvicorn

    config = get_config()
    logger.info(
        "bff_running",
        host="0.0.0.0",
        port=config.port,
    )
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=config.port,
            log_level=config.log_level.lower(),
        )
    )
    await server.serve()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
