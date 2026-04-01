"""Multi-node Redlock implementation using Redis."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import TYPE_CHECKING

from zrun_core.infra.logging import get_logger
from zrun_core.lock.protocols import RELEASE_SCRIPT

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = get_logger()


class Redlock:
    """Redlock algorithm implementation - distributed lock across multiple Redis nodes.

    This implements the Redlock algorithm as described in the Redis documentation:
    https://redis.io/docs/reference/patterns/distributed-locks/

    Algorithm steps:
    1. Get the current timestamp
    2. Try to acquire the lock in all N instances sequentially
    3. Compute the elapsed time
    4. If the lock was acquired in majority (N/2 + 1) and elapsed < TTL, success
    5. Release by sending unlock command to all nodes

    Usage:
        ```python
        clients = [redis1, redis2, redis3, redis4, redis5]
        async with Redlock(clients, "my_lock", ttl=30) as lock:
            if lock.acquired:
                # Critical section
                pass
        ```
    """

    def __init__(
        self,
        clients: list[AsyncRedis],
        key: str,
        ttl: int = 30,
    ) -> None:
        """Initialize the Redlock.

        Args:
            clients: List of Redis client instances (must be at least 3 for quorum).
            key: Lock key in Redis.
            ttl: Lock TTL in seconds.
        """
        self._clients = clients
        self._key = f"lock:{key}"
        self._ttl = ttl
        self._token: str | None = None

    async def acquire(self) -> bool:
        """Attempt to acquire the lock across the majority of Redis nodes.

        Returns:
            True if the lock was acquired on a quorum of nodes, False otherwise.
        """
        token = str(uuid.uuid4())
        quorum = len(self._clients) // 2 + 1
        ttl_ms = self._ttl * 1000

        start_ms = time.monotonic() * 1000
        acquired_count = 0

        for client in self._clients:
            try:
                result = await client.set(
                    self._key,
                    token,
                    nx=True,
                    px=ttl_ms,
                )
                if result:
                    acquired_count += 1
            except Exception:
                logger.warning("redlock_node_acquire_failed", key=self._key)

        elapsed_ms = time.monotonic() * 1000 - start_ms
        validity_ms = ttl_ms - elapsed_ms

        if acquired_count >= quorum and validity_ms > 0:
            self._token = token
            logger.debug(
                "redlock_acquired",
                key=self._key,
                nodes=acquired_count,
                validity_ms=validity_ms,
            )
            return True

        # Failed to acquire quorum — release any partial locks
        await self._release_all(token)
        return False

    async def release(self) -> bool:
        """Release the lock on all Redis nodes.

        Returns:
            True if the lock was released, False if it was not held.
        """
        if self._token is None:
            return False

        token = self._token
        self._token = None

        await self._release_all(token)
        logger.debug("redlock_released", key=self._key)
        return True

    async def _release_all(self, token: str) -> None:
        """Send unlock command to all Redis nodes in parallel.

        Args:
            token: The unique token used during acquisition.
        """
        results = await asyncio.gather(  # type: ignore[no-matching-overload]
            *[client.eval(RELEASE_SCRIPT, 1, self._key, token) for client in self._clients],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.warning("redlock_node_release_failed", key=self._key)

    @property
    def acquired(self) -> bool:
        """Check if the lock is currently held."""
        return self._token is not None

    async def __aenter__(self) -> Redlock:
        """Acquire the lock when entering the context."""
        await self.acquire()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_val: BaseException | None,
        _exc_tb: object,
    ) -> None:
        """Release the lock when exiting the context."""
        await self.release()
