"""Unit tests for Redis distributed lock."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zrun_core.lock import RedisLock


class TestRedisLock:
    """Tests for RedisLock class."""

    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        """Create a mock Redis client."""
        redis = AsyncMock()
        redis.set = AsyncMock(return_value=True)
        redis.expire = AsyncMock(return_value=True)
        redis.eval = AsyncMock(return_value=1)
        return redis

    @pytest.fixture
    def lock(self, mock_redis: MagicMock) -> RedisLock:
        """Create a RedisLock instance with mock Redis."""
        return RedisLock(redis=mock_redis, key="test_lock", ttl=30, auto_renewal=False)

    def test_lock_initialization(self, mock_redis: MagicMock) -> None:
        """Test lock initialization."""
        lock = RedisLock(
            redis=mock_redis,
            key="my_lock",
            ttl=60,
            auto_renewal=True,
            renewal_interval=0.9,
        )
        assert lock._key == "lock:my_lock"
        assert lock._ttl == 60
        assert lock._auto_renewal is True
        assert lock._renewal_interval == 0.9
        assert lock._acquired is False

    @pytest.mark.asyncio
    async def test_acquire_lock_success(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test successful lock acquisition."""
        mock_redis.set.return_value = True

        acquired = await lock.acquire()

        assert acquired is True
        assert lock.acquired is True
        assert lock._token is not None
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lock_failure(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test failed lock acquisition."""
        mock_redis.set.return_value = None

        acquired = await lock.acquire()

        assert acquired is False
        assert lock.acquired is False

    @pytest.mark.asyncio
    async def test_acquire_lock_sets_correct_params(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test lock acquisition sets correct Redis parameters."""
        mock_redis.set.return_value = True

        await lock.acquire()

        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "lock:test_lock"
        assert call_args[1]["nx"] is True
        assert call_args[1]["px"] == 30000  # 30 seconds in milliseconds

    @pytest.mark.asyncio
    async def test_release_lock_success(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test successful lock release."""
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1

        await lock.acquire()
        released = await lock.release()

        assert released is True
        assert lock.acquired is False
        mock_redis.eval.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lock_not_owned(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test releasing a lock that is not owned."""
        mock_redis.eval.return_value = 0

        released = await lock.release()

        assert released is False

    @pytest.mark.asyncio
    async def test_release_lock_without_token(self, lock: RedisLock) -> None:
        """Test releasing a lock when token is None."""
        lock._token = None

        released = await lock.release()

        assert released is False

    @pytest.mark.asyncio
    async def test_renew_lock_success(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test successful lock renewal."""
        lock._token = "test_token"
        mock_redis.expire.return_value = 1

        renewed = await lock._renew()

        assert renewed is True
        mock_redis.expire.assert_called_once_with("lock:test_lock", 30)

    @pytest.mark.asyncio
    async def test_renew_lock_failure(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test failed lock renewal."""
        lock._token = "test_token"
        mock_redis.expire.return_value = 0

        renewed = await lock._renew()

        assert renewed is False

    @pytest.mark.asyncio
    async def test_renew_lock_without_token(self, lock: RedisLock) -> None:
        """Test renewing a lock when token is None."""
        lock._token = None

        renewed = await lock._renew()

        assert renewed is False

    @pytest.mark.asyncio
    async def test_context_manager(self, lock: RedisLock, mock_redis: MagicMock) -> None:
        """Test using lock as a context manager."""
        mock_redis.set.return_value = True
        mock_redis.eval.return_value = 1

        async with lock:
            assert lock.acquired is True

        assert lock.acquired is False


class TestRedisLockScript:
    """Tests for Redis lock Lua script."""

    def test_release_script_format(self) -> None:
        """Test release script is valid Lua."""
        script = RedisLock.RELEASE_SCRIPT
        assert "redis.call" in script
        assert "get" in script
        assert "del" in script
