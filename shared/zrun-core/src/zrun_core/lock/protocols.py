"""Distributed lock protocols and exceptions."""

from __future__ import annotations

from typing import Protocol

from zrun_core.errors.errors import ConflictError, DomainError

# Lua script for safe lock release (prevents deleting locks owned by other clients)
# This script ensures only the lock owner can release it by checking the token
RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class LockError(DomainError):
    """Base exception for lock-related errors."""


class LockAcquisitionError(ConflictError):
    """Raised when lock acquisition fails due to conflict."""


class LockReleaseError(LockError):
    """Raised when lock release fails."""


class LockRenewalError(LockError):
    """Raised when lock renewal fails."""


class DistributedLock(Protocol):
    """Distributed lock abstract interface.

    This protocol defines the interface that all distributed lock
    implementations must follow.
    """

    async def acquire(self) -> bool:
        """Attempt to acquire the lock.

        Returns:
            True if the lock was acquired, False otherwise.
        """
        ...

    async def release(self) -> bool:
        """Release the lock.

        Returns:
            True if the lock was released, False otherwise.
        """
        ...

    @property
    def acquired(self) -> bool:
        """Check if the lock is currently held."""
        ...

    async def __aenter__(self) -> DistributedLock:
        """Acquire the lock when entering the context."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Release the lock when exiting the context."""
        ...
