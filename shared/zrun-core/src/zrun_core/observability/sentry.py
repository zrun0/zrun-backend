"""Sentry SDK initialization and configuration.

This module provides Sentry integration for error tracking and performance
monitoring in zrun microservices.
"""

from __future__ import annotations

import os
from typing import Literal

import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.grpc import GRPCIntegration
from sentry_sdk.integrations.redis import RedisIntegration

# =============================================================================
# Environment Variable Keys
# =============================================================================

SENTRY_DSN_ENV_KEY: str = "SENTRY_DSN"
SENTRY_ENVIRONMENT_ENV_KEY: str = "SENTRY_ENVIRONMENT"
SENTRY_TRACES_SAMPLE_RATE_ENV_KEY: str = "SENTRY_TRACES_SAMPLE_RATE"


# =============================================================================
# Configuration Constants
# =============================================================================

DEFAULT_ENVIRONMENT: Literal["development", "production", "staging"] = "development"
DEFAULT_TRACES_SAMPLE_RATE: float = 0.1
SENTRY_RELEASE_KEY: str = "SENTRY_RELEASE"


# =============================================================================
# Public API
# =============================================================================


def init_sentry(
    dsn: str,
    *,
    environment: str = DEFAULT_ENVIRONMENT,
    service_name: str,
    traces_sample_rate: float = DEFAULT_TRACES_SAMPLE_RATE,
    release: str | None = None,
) -> None:
    """Initialize Sentry SDK for error tracking and performance monitoring.

    This function sets up Sentry with integrations optimized for zrun services:
    - AsyncioIntegration: For async/await code
    - GRPCIntegration: For gRPC server/client tracing
    - RedisIntegration: For Redis operation monitoring

    Args:
        dsn: The Sentry Data Source Name (DSN) URL
        environment: Environment name (development, staging, production)
        service_name: Identifier for this service (e.g., "zrun-base", "zrun-ops")
        traces_sample_rate: Fraction of transactions to sample (0.0 to 1.0)
        release: Optional release version string

    Example:
        >>> init_sentry(
        ...     dsn="https://xxx@o0.ingest.sentry.io/xxx",
        ...     environment="production",
        ...     service_name="zrun-base",
        ...     traces_sample_rate=0.1,
        ... )
    """
    if not dsn or dsn == "https://dummy_dsn@localhost":
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        server_name=service_name,
        traces_sample_rate=traces_sample_rate,
        release=release,
        integrations=[
            AsyncioIntegration(),
            GRPCIntegration(),
            RedisIntegration(),
        ],
        # Set service name for better grouping in Sentry
        _experiments={
            "max_spans": 1000,
        },
    )


def configure_sentry_from_env(
    service_name: str,
    *,
    dsn_env_key: str = SENTRY_DSN_ENV_KEY,
    environment_env_key: str = SENTRY_ENVIRONMENT_ENV_KEY,
    traces_sample_rate_env_key: str = SENTRY_TRACES_SAMPLE_RATE_ENV_KEY,
) -> None:
    """Configure Sentry from environment variables.

    Reads configuration from the following environment variables:
    - SENTRY_DSN: Required. The Sentry Data Source Name
    - SENTRY_ENVIRONMENT: Optional. Defaults to "development"
    - SENTRY_TRACES_SAMPLE_RATE: Optional. Defaults to 0.1
    - SENTRY_RELEASE: Optional. Release version string

    Args:
        service_name: Identifier for this service
        dsn_env_key: Environment variable key for DSN
        environment_env_key: Environment variable key for environment name
        traces_sample_rate_env_key: Environment variable key for trace sampling rate

    Example:
        >>> # In .env file:
        >>> # SENTRY_DSN=https://xxx@o0.ingest.sentry.io/xxx
        >>> # SENTRY_ENVIRONMENT=production
        >>> configure_sentry_from_env(service_name="zrun-base")
    """
    dsn = os.getenv(dsn_env_key, "")
    if not dsn:
        return

    environment = os.getenv(environment_env_key, DEFAULT_ENVIRONMENT)

    traces_sample_rate_str = os.getenv(traces_sample_rate_env_key, str(DEFAULT_TRACES_SAMPLE_RATE))
    try:
        traces_sample_rate = float(traces_sample_rate_str)
    except ValueError:
        traces_sample_rate = DEFAULT_TRACES_SAMPLE_RATE

    release = os.getenv(SENTRY_RELEASE_KEY)

    init_sentry(
        dsn=dsn,
        environment=environment,
        service_name=service_name,
        traces_sample_rate=traces_sample_rate,
        release=release,
    )
