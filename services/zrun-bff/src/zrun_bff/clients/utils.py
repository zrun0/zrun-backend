"""Utility functions for gRPC clients.

This module provides:
- Error handling decorator for gRPC calls
- Retry mechanism with exponential backoff
"""

from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, TYPE_CHECKING

from grpc import StatusCode
from grpc.aio import AioRpcError
from structlog import get_logger

from zrun_bff.errors import grpc_error_to_bff_error

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = get_logger()


# Transient gRPC errors that should be retrried
RETRYABLE_STATUS_CODES = {
    StatusCode.UNAVAILABLE,
    StatusCode.DEADLINE_EXCEEDED,
    StatusCode.RESOURCE_EXHAUSTED,
    StatusCode.ABORTED,
}


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable.

    Args:
        error: Exception to check.

    Returns:
        True if error is retryable.
    """
    if isinstance(error, AioRpcError):
        return error.code() in RETRYABLE_STATUS_CODES
    return False


def handle_grpc_error[T](
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Decorator to handle gRPC errors and convert to BFF errors.

    Args:
        func: Async function to decorate.

    Returns:
        Decorated function.
    """
    func_name = getattr(func, "__name__", "<unknown>")

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except AioRpcError as e:
            logger.warning(
                "grpc_error",
                code=e.code().name,
                details=e.details(),
                function=func_name,
            )
            raise grpc_error_to_bff_error(e) from e
        except Exception as e:
            logger.error(
                "unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
                function=func_name,
            )
            raise grpc_error_to_bff_error(e) from e

    return wrapper


async def retry_with_backoff[T](
    func: Callable[..., Coroutine[Any, Any, T]],
    max_retries: int = 3,
    initial_delay: float = 0.1,
    max_delay: float = 2.0,
    backoff_factor: float = 2.0,
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: Async function to retry.
        max_retries: Maximum number of retries.
        initial_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        backoff_factor: Multiplier for delay after each retry.

    Returns:
        Function result.

    Raises:
        BFFError: If all retries fail.
    """
    delay = initial_delay
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_error = e

            if attempt == max_retries or not is_retryable_error(e):
                logger.warning(
                    "retry_failed",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e),
                )
                raise grpc_error_to_bff_error(e) from e

            logger.info(
                "retrying",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
            )

            await asyncio.sleep(min(delay, max_delay))
            delay *= backoff_factor

    # This should never be reached, but mypy needs it
    raise grpc_error_to_bff_error(last_error or Exception("Retry failed"))
