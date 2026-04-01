"""Single-node distributed lock implementation using Redis."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import TYPE_CHECKING

from zrun_core.infra.logging import get_logger
from zrun_core.lock.protocols import RELEASE_SCRIPT

if TYPE_CHECKING:
    from redis.asyncio import Redis as AsyncRedis

logger = get_logger()


class SingleNodeLock:
    """Single-node distributed lock using Redis.

    This lock uses the SET NX PX command for acquisition and a Lua script
    for safe release. It also includes a background watchdog task that
    periodically renews the TTL to prevent lock expiration during long operations.

    Usage:
        ```python
        async with SingleNodeLock(redis, "my_lock", ttl=30) as lock:
            if lock.acquired:
                # Critical section
                pass
        ```
    """

    def __init__(
        self,
        redis: AsyncRedis,
        key: str,
        ttl: int = 30,
        auto_renewal: bool = True,
        renewal_interval: float = 0.8,
    ) -> None:
        """Initialize the lock.

        Args:
            redis: Redis client instance.
            key: Lock key in Redis.
            ttl: Lock TTL in seconds.
            auto_renewal: Whether to automatically renew the lock.
            renewal_interval: Fraction of TTL to wait before renewing (e.g., 0.8 = 80%).
        """
        self._redis = redis
        self._key = f"lock:{key}"
        self._ttl = ttl
        self._auto_renewal = auto_renewal
        self._renewal_interval = renewal_interval
        self._token: str | None = None
        self._acquired = False
        self._watchdog_task: asyncio.Task[None] | None = None
        self._stop_watchdog = asyncio.Event()

    async def acquire(self) -> bool:
        """Attempt to acquire the lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        self._token = str(uuid.uuid4())

        result = await self._redis.set(
            self._key,
            self._token,
            nx=True,
            px=self._ttl * 1000,  # Convert to milliseconds
        )

        self._acquired = bool(result)

        if self._acquired:
            logger.debug("lock_acquired", key=self._key, ttl=self._ttl)
            if self._auto_renewal:
                self._start_watchdog()

        return self._acquired

    async def release(self) -> bool:
        """Release the lock.

        Returns:
            True if the lock was released, False if it wasn't held by this instance.
        """
        if self._token is None:
            return False

        self._stop_watchdog.set()
        if self._watchdog_task is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._watchdog_task, timeout=1.0)
            self._watchdog_task = None

        result = await self._redis.eval(  # type: ignore[no-any-await]
            RELEASE_SCRIPT,
            1,
            self._key,
            self._token,
        )

        released = bool(result)

        if released:
            logger.debug("lock_released", key=self._key)
        else:
            logger.warning("lock_release_failed", key=self._key)

        self._acquired = False
        self._token = None
        self._stop_watchdog.clear()

        return released

    def _start_watchdog(self) -> None:
        """Start the background watchdog task for TTL renewal."""
        self._watchdog_task = asyncio.create_task(self._watchdog())

    async def _watchdog(self) -> None:
        """Watchdog task that periodically renews the lock TTL."""
        renewal_delay = self._ttl * self._renewal_interval

        while self._acquired:
            try:
                await asyncio.wait_for(
                    self._stop_watchdog.wait(),
                    timeout=renewal_delay,
                )
                break
            except TimeoutError:
                if self._acquired and self._token:
                    renewed = await self._renew()
                    if not renewed:
                        logger.warning("lock_renewal_failed", key=self._key)
                        break

    async def _renew(self) -> bool:
        """Renew the lock TTL.

        Returns:
            True if the TTL was renewed, False otherwise.
        """
        if self._token is None:
            return False

        result = await self._redis.expire(
            self._key,
            self._ttl,
        )

        return bool(result)

    @property
    def acquired(self) -> bool:
        """Check if the lock is currently held."""
        return self._acquired

    async def __aenter__(self) -> SingleNodeLock:
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


# Alias for backward compatibility
RedisLock = SingleNodeLock
