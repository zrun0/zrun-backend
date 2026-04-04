"""Factory for creating distributed lock instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from zrun_core.lock.distributed import Redlock
from zrun_core.lock.single import SingleNodeLock

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

    from zrun_core.lock.protocols import DistributedLock

# Minimum Redis clients required for Redlock algorithm
_REDLOCK_MIN_CLIENTS = 3


def create_lock(
    key: str,
    mode: Literal["single", "redlock"] = "single",
    *,
    redis_client: AsyncRedis | None = None,
    redis_clients: list[AsyncRedis] | None = None,
    ttl: int = 30,
    **kwargs: object,
) -> DistributedLock:
    """Create a distributed lock instance.

    Args:
        key: Lock key in Redis.
        mode: Lock mode - "single" for single node, "redlock" for multi-node.
        redis_client: Single Redis client (required for "single" mode).
        redis_clients: List of Redis clients (required for "redlock" mode).
        ttl: Lock TTL in seconds.
        **kwargs: Additional arguments passed to the lock implementation.

    Returns:
        A distributed lock instance.

    Raises:
        ValueError: If required parameters are missing for the selected mode.

    Examples:
        Single node:
        ```python
        from redis.asyncio import Redis as AsyncRedis
        redis = AsyncRedis.from_url("redis://localhost:6379")
        lock = create_lock("my_lock", mode="single", redis_client=redis)
        async with lock:
            pass
        ```

        Multi-node Redlock:
        ```python
        clients = [
            AsyncRedis.from_url("redis://node1:6379"),
            AsyncRedis.from_url("redis://node2:6379"),
            AsyncRedis.from_url("redis://node3:6379"),
        ]
        lock = create_lock("my_lock", mode="redlock", redis_clients=clients)
        async with lock:
            pass
        ```
    """
    if mode == "single":
        if redis_client is None:
            msg = "redis_client is required for 'single' mode"
            raise ValueError(msg)
        return SingleNodeLock(redis_client, key, ttl=ttl, **kwargs)  # type: ignore[arg-type]

    if mode == "redlock":
        if redis_clients is None:
            msg = "redis_clients is required for 'redlock' mode"
            raise ValueError(msg)
        if len(redis_clients) < _REDLOCK_MIN_CLIENTS:
            msg = f"redlock requires at least {_REDLOCK_MIN_CLIENTS} Redis clients"
            raise ValueError(msg)
        return Redlock(redis_clients, key, ttl=ttl, **kwargs)  # type: ignore[arg-type]

    msg = f"Invalid mode: {mode!r}. Must be 'single' or 'redlock'"
    raise ValueError(msg)
