"""Distributed lock protocol and exceptions."""

from __future__ import annotations

from typing import Protocol


class LockError(Exception):
    """Base exception for lock-related errors."""


class LockAcquisitionError(LockError):
    """Raised when lock acquisition fails."""


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
