"""FastAPI application entry point for zrun-bff service."""

import httpx
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from zrun_bff.api.pda.sku import router as sku_router
from zrun_bff.auth.middleware import SessionMiddleware, UserContextMiddleware
from zrun_bff.auth.router import router as auth_router
from zrun_bff.config import BFFConfig, get_config
from zrun_bff.errors import (
    BFFError,
    ErrorResponse,
    grpc_error_to_bff_error,
)
from zrun_core.infra.logging import configure_structlog, get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    config = get_config()

    # Configure structlog
    configure_structlog(
        service_name="zrun-bff",
        log_level=config.log_level,
        log_format="json" if config.env == "prod" else "console",
    )

    # Fail fast if JWT private key is configured but not found
    if config.jwt_private_key_path:
        # Access the property to trigger validation (may raise FileNotFoundError)
        _key = config.jwt_private_key  # noqa: F841

    # Create shared HTTP client for OAuth token exchanges
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    )

    logger.info(
        "bff_starting",
        service="zrun-bff",
        version="0.1.0-dev",
        env=config.env,
    )
    yield
    # Cleanup shared HTTP client
    await app.state.http_client.aclose()
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

    # Session middleware for OAuth state storage
    app.add_middleware(
        SessionMiddleware,  # type: ignore[arg-type]
        secret_key=config.session_secret_key,
        session_cookie="zrun_session",
        max_age=14 * 24 * 60 * 60,  # 14 days
        same_site="lax",
        https_only=config.env == "production",
    )

    # User context middleware for automatic gRPC auth propagation
    app.add_middleware(UserContextMiddleware, config=config)  # type: ignore[arg-type]

    # Exception handlers
    from starlette.responses import JSONResponse

    @app.exception_handler(BFFError)
    async def bff_error_handler(_: object, exc: BFFError) -> JSONResponse:
        """Handle BFF-specific errors."""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse.from_bff_error(exc).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(_: object, exc: Exception) -> JSONResponse:
        """Handle generic exceptions."""
        logger.error("unhandled_exception", error=str(exc), error_type=type(exc).__name__)
        error = grpc_error_to_bff_error(exc)
        return JSONResponse(
            status_code=error.status_code,
            content=ErrorResponse.from_bff_error(error).model_dump(),
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
    app.include_router(sku_router, tags=["PDA", "SKU"])

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
