"""
Rate Limiter - Prevents abuse of MCP tools.

Implements in-memory rate limiting following MCP security best practices:
"Servers MUST rate limit tool invocations" - MCP Specification

Usage:
    from utils.rate_limiter import RateLimiter

    # Create limiter: 30 calls per 60 seconds
    search_limiter = RateLimiter(max_calls=30, period_seconds=60)

    # Check before operation
    if not search_limiter.check(session_key):
        raise RateLimitError("Too many requests")

Author: Odiseo Team
Version: 2.0.0
"""

from collections import defaultdict
from time import time

from utils.logger import get_logger

logger = get_logger("rate_limiter")


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 0):
        self.message = message
        self.retry_after = retry_after
        super().__init__(self.message)


class RateLimiter:
    """
    In-memory rate limiter with sliding window.

    Thread-safe for single-process deployments.
    For multi-process, consider Redis-based implementation.
    """

    def __init__(self, max_calls: int, period_seconds: int):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in the period
            period_seconds: Time window in seconds
        """
        self.max_calls = max_calls
        self.period_seconds = period_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """
        Check if a call is allowed for the given key.

        Args:
            key: Identifier (e.g., email, IP, user_id, session_id)

        Returns:
            True if call is allowed, False if rate limited
        """
        now = time()
        window_start = now - self.period_seconds

        # Clean old entries
        self._calls[key] = [t for t in self._calls[key] if t > window_start]

        # Check limit
        if len(self._calls[key]) >= self.max_calls:
            logger.warning(f"Rate limit exceeded for key: {key[:20]}...")
            return False

        # Record this call
        self._calls[key].append(now)
        return True

    def get_retry_after(self, key: str) -> int:
        """
        Get seconds until next call is allowed.

        Args:
            key: Identifier

        Returns:
            Seconds to wait, 0 if not rate limited
        """
        if not self._calls[key]:
            return 0

        now = time()
        window_start = now - self.period_seconds
        oldest_call = min(t for t in self._calls[key] if t > window_start)

        return max(0, int(oldest_call + self.period_seconds - now))

    def reset(self, key: str) -> None:
        """Reset rate limit for a specific key."""
        self._calls.pop(key, None)

    def clear_all(self) -> None:
        """Clear all rate limit data."""
        self._calls.clear()
