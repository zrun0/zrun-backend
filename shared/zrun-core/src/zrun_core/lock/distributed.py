"""Multi-node Redlock implementation using Redis."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = structlog.get_logger()


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

    # Lua script for safe lock release
    RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        redis_clients: list[AsyncRedis],
        key: str,
        ttl: int = 30,
        drift_factor: float = 0.01,
        retry_times: int = 3,
        retry_delay: float = 0.2,
    ) -> None:
        """Initialize the Redlock.

        Args:
            redis_clients: List of Redis client instances.
            key: Lock key in Redis (will be prefixed with "lock:").
            ttl: Lock TTL in seconds.
            drift_factor: Clock drift factor to compensate for time drift.
            retry_times: Number of retries for lock acquisition.
            retry_delay: Delay between retries in seconds.
        """
        if len(redis_clients) < 3:
            logger.warning(
                "redlock_few_nodes",
                nodes=len(redis_clients),
                message="Redlock requires at least 3 nodes for reliability",
            )

        self._clients = redis_clients
        self._key = f"lock:{key}"
        self._ttl = ttl
        self._ttl_ms = ttl * 1000
        self._drift_factor = drift_factor
        self._retry_times = retry_times
        self._retry_delay = retry_delay
        self._quorum = len(redis_clients) // 2 + 1
        self._token: str | None = None
        self._acquired = False

    async def acquire(self) -> bool:
        """Attempt to acquire the lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        import asyncio

        token = str(uuid.uuid4())

        for attempt in range(self._retry_times):
            acquired_count = 0
            start_time = asyncio.get_event_loop().time()

            # Try to acquire lock on all nodes
            for client in self._clients:
                try:
                    result = await client.set(
                        self._key,
                        token,
                        nx=True,
                        px=self._ttl_ms,
                    )
                    if result:
                        acquired_count += 1
                except Exception as e:
                    node_id = (
                        await client.client_id() if hasattr(client, "client_id") else "unknown"
                    )
                    logger.warning(
                        "redlock_node_error",
                        node=node_id,
                        error=str(e),
                    )

            # Calculate elapsed time and validity
            elapsed = (asyncio.get_event_loop().time() - start_time) / 1000  # Convert to seconds
            drift = self._drift_factor * self._ttl
            validity = self._ttl - elapsed - drift

            # Check if we acquired lock on majority and it's still valid
            if acquired_count >= self._quorum and validity > 0:
                self._token = token
                self._acquired = True
                logger.debug(
                    "redlock_acquired",
                    key=self._key,
                    nodes=acquired_count,
                    quorum=self._quorum,
                    validity=validity,
                )
                return True

            # Failed to acquire, release any locks we got
            await self._unlock_all_nodes(token)

            # Retry if not the last attempt
            if attempt < self._retry_times - 1:
                await asyncio.sleep(self._retry_delay)

        logger.warning("redlock_acquire_failed", key=self._key)
        return False

    async def release(self) -> bool:
        """Release the lock.

        Returns:
            True if the lock was released, False otherwise.
        """
        if self._token is None:
            return False

        released_count = 0

        # Send release command to all nodes
        for client in self._clients:
            try:
                result = await client.eval(  # type: ignore[misc]
                    self.RELEASE_SCRIPT,
                    1,
                    self._key,
                    self._token,
                )
                if result:
                    released_count += 1
            except Exception as e:
                node_id = await client.client_id() if hasattr(client, "client_id") else "unknown"
                logger.warning(
                    "redlock_release_error",
                    node=node_id,
                    error=str(e),
                )

        success = released_count >= self._quorum

        if success:
            logger.debug(
                "redlock_released",
                key=self._key,
                nodes=released_count,
            )
        else:
            logger.warning(
                "redlock_release_partial",
                key=self._key,
                nodes=released_count,
                quorum=self._quorum,
            )

        self._acquired = False
        self._token = None

        return success

    async def _unlock_all_nodes(self, token: str) -> None:
        """Unlock all nodes with the given token.

        Args:
            token: The lock token to release.
        """
        import asyncio

        # Release in parallel for speed
        tasks = []
        for client in self._clients:
            tasks.append(
                client.eval(
                    self.RELEASE_SCRIPT,
                    1,
                    self._key,
                    token,
                )
            )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @property
    def acquired(self) -> bool:
        """Check if the lock is currently held."""
        return self._acquired

    async def __aenter__(self) -> Redlock:
        """Acquire the lock when entering the context.

        Returns:
            Self.
        """
        await self.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Release the lock when exiting the context."""
        await self.release()
