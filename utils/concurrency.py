"""Concurrency control for MCP Server.

Provides asyncio-based concurrency limiting to prevent resource exhaustion
when handling multiple simultaneous requests.

Features:
    - Semaphore-based request limiting
    - Lazy initialization (works with any event loop)
    - Configurable via MAX_CONCURRENT_REQUESTS setting
    - Context manager for easy usage

Usage:
    from utils.concurrency import acquire_slot, ConcurrencyLimitExceededError

    try:
        async with acquire_slot():
            # Process request
            result = await some_operation()
    except ConcurrencyLimitExceededError:
        # Return 429 Too Many Requests
        pass
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Lazy-initialized semaphore (created on first use to avoid event loop issues)
_concurrency_semaphore: asyncio.Semaphore | None = None


class ConcurrencyLimitExceededError(Exception):
    """Raised when concurrency limit is reached and request cannot be processed."""

    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        super().__init__(
            f"Service temporarily unavailable. Max concurrent requests: {max_concurrent}"
        )


# Alias for backward compatibility
ConcurrencyLimitExceeded = ConcurrencyLimitExceededError


def _get_semaphore() -> asyncio.Semaphore:
    """Get or create the concurrency semaphore.

    Lazily initializes the semaphore on first call to ensure it's created
    in the correct event loop context.

    Returns:
        asyncio.Semaphore configured with MAX_CONCURRENT_REQUESTS limit.
    """
    global _concurrency_semaphore
    if _concurrency_semaphore is None:
        _concurrency_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_REQUESTS)
        logger.debug(
            f"Initialized concurrency semaphore with limit: {settings.MAX_CONCURRENT_REQUESTS}"
        )
    return _concurrency_semaphore


def get_available_slots() -> int:
    """Get the number of available concurrent request slots.

    Returns:
        Number of available slots, or max if semaphore not initialized.
    """
    if _concurrency_semaphore is None:
        return settings.MAX_CONCURRENT_REQUESTS
    return _concurrency_semaphore._value


def is_at_capacity() -> bool:
    """Check if the server is at maximum capacity.

    Returns:
        True if all slots are in use, False otherwise.
    """
    if _concurrency_semaphore is None:
        return False
    return _concurrency_semaphore._value == 0


@asynccontextmanager
async def acquire_slot(timeout: float = 0.01) -> AsyncGenerator[None, None]:
    """Acquire a concurrency slot for processing a request.

    Context manager that acquires a slot from the semaphore. If all slots
    are in use and timeout expires, raises ConcurrencyLimitExceeded.

    Args:
        timeout: Maximum time to wait for a slot (default: 10ms for non-blocking).

    Yields:
        None when slot is acquired.

    Raises:
        ConcurrencyLimitExceeded: If no slots available within timeout.

    Example:
        async with acquire_slot():
            result = await process_request()
    """
    semaphore = _get_semaphore()

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=timeout)
    except asyncio.TimeoutError as err:
        logger.warning(
            f"Concurrency limit exceeded: {settings.MAX_CONCURRENT_REQUESTS} concurrent requests"
        )
        raise ConcurrencyLimitExceededError(settings.MAX_CONCURRENT_REQUESTS) from err

    try:
        yield
    finally:
        semaphore.release()


async def try_acquire_slot() -> bool:
    """Try to acquire a slot without blocking.

    Returns:
        True if slot was acquired, False if at capacity.

    Note:
        If True is returned, caller MUST release the slot by calling release_slot().
    """
    semaphore = _get_semaphore()

    if semaphore.locked() and semaphore._value == 0:
        return False

    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.001)
        return True
    except asyncio.TimeoutError:
        return False


def release_slot() -> None:
    """Release a previously acquired slot.

    Only call this if try_acquire_slot() returned True.
    """
    if _concurrency_semaphore is not None:
        _concurrency_semaphore.release()


def reset_semaphore() -> None:
    """Reset the semaphore (useful for testing).

    Warning: Only use in tests, never in production.
    """
    global _concurrency_semaphore
    _concurrency_semaphore = None
