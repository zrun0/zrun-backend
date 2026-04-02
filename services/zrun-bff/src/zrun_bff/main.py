"""FastAPI application entry point for zrun-bff service."""

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from structlog import get_logger

from zrun_bff.auth.router import router as auth_router
from zrun_bff.config import BFFConfig

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger()


@lru_cache
def get_config() -> BFFConfig:
    """Get cached BFF configuration.

    Returns:
        BFF configuration instance.
    """
    return BFFConfig()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    config = get_config()
    # Fail fast if JWT private key is configured but not found
    if config.jwt_private_key_path:
        # Access the property to trigger validation (may raise FileNotFoundError)
        _key = config.jwt_private_key  # noqa: F841
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
    app.add_middleware(
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
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

    # Register routers
    app.include_router(auth_router, tags=["Authentication"])

    # TODO: Register additional routers
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
