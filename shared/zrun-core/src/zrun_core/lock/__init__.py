"""Distributed lock implementations.

This module provides distributed lock implementations with support for:
- Single-node locks using redis-py
- Multi-node Redlock algorithm
- Configuration-based switching between modes
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from zrun_core.lock.distributed import Redlock
from zrun_core.lock.factory import create_lock
from zrun_core.lock.interface import (
    DistributedLock,
    LockAcquisitionError,
    LockError,
    LockReleaseError,
    LockRenewalError,
)
from zrun_core.lock.single import RedisLock, SingleNodeLock

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from redis.asyncio import Redis as AsyncRedis


@asynccontextmanager
async def redis_lock(
    redis: AsyncRedis,
    key: str,
    ttl: int = 30,
    auto_renewal: bool = True,
) -> AsyncIterator[SingleNodeLock]:
    """Context manager for acquiring a Redis lock.

    Args:
        redis: Redis client instance.
        key: Lock key in Redis.
        ttl: Lock TTL in seconds.
        auto_renewal: Whether to automatically renew the lock.

    Yields:
        The RedisLock instance.
    """
    lock = SingleNodeLock(redis, key, ttl, auto_renewal)
    await lock.acquire()

    try:
        yield lock
    finally:
        await lock.release()


__all__ = [
    # Factory
    "create_lock",
    # Protocol
    "DistributedLock",
    # Exceptions
    "LockError",
    "LockAcquisitionError",
    "LockReleaseError",
    "LockRenewalError",
    # Implementations
    "SingleNodeLock",
    "RedisLock",  # Alias for backward compatibility
    "Redlock",
    # Context manager
    "redis_lock",
]
