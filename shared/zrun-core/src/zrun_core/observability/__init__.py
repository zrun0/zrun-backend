"""Sentry observability integration for zrun services.

This module provides Sentry initialization and utilities for error tracking
and performance monitoring across all zrun microservices.

Example:
    >>> from zrun_core.observability import init_sentry, configure_sentry_from_env
    >>> # Initialize with explicit parameters
    >>> init_sentry(
    ...     dsn="https://xxx@o0.ingest.sentry.io/xxx",
    ...     environment="production",
    ...     service_name="zrun-base",
    ...     traces_sample_rate=0.1,
    ... )
    >>> # Or configure from environment variables
    >>> configure_sentry_from_env(service_name="zrun-base")
"""

from __future__ import annotations

from zrun_core.observability.sentry import (
    SENTRY_DSN_ENV_KEY,
    SENTRY_ENVIRONMENT_ENV_KEY,
    SENTRY_TRACES_SAMPLE_RATE_ENV_KEY,
    configure_sentry_from_env,
    init_sentry,
)

__all__ = [
    "init_sentry",
    "configure_sentry_from_env",
    "SENTRY_DSN_ENV_KEY",
    "SENTRY_ENVIRONMENT_ENV_KEY",
    "SENTRY_TRACES_SAMPLE_RATE_ENV_KEY",
]
