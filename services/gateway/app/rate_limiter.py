"""Redis-based sliding window rate limiter for the API Gateway.

Implements a sliding window algorithm using Redis sorted sets to track
request counts per client IP address.
"""

import redis.asyncio as redis
from datetime import datetime, timezone
from typing import Tuple
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Async sliding-window rate limiter using Redis sorted sets.

    Uses a sliding window log algorithm where each request is stored as a
    sorted set member with its timestamp as the score. Old entries outside
    the window are removed before counting.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        requests_per_window: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            redis_client: Async Redis client instance.
            requests_per_window: Max requests allowed per window.
            window_seconds: Window duration in seconds.
        """
        self._redis = redis_client
        self._limit = requests_per_window or settings.RATE_LIMIT_REQUESTS
        self._window = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS

    async def is_allowed(self, client_ip: str) -> Tuple[bool, int, int]:
        """Check if a request from the given IP is allowed under the rate limit.

        Uses a sliding window: removes expired entries, then checks count.

        Args:
            client_ip: Client IP address to rate limit.

        Returns:
            Tuple of (allowed: bool, remaining: int, reset_in_seconds: int).
            allowed is True if request is within limit, False if rate limited.
            remaining is how many requests are left in the current window.
            reset_in_seconds is seconds until the oldest entry expires.
        """
        key = f"ratelimit:{client_ip}"
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        window_start_ms = now_ms - (self._window * 1000)

        # Use pipeline for atomic operations
        async with self._redis.pipeline(transaction=True) as pipe:
            # Remove entries older than window
            await pipe.zremrangebyscore(key, 0, window_start_ms)
            # Count current entries in window
            await pipe.zcard(key)
            # Add current request with timestamp as score
            await pipe.zadd(key, {f"{now_ms}:{id(self)}": now_ms})
            # Set expiry on the key
            await pipe.expire(key, self._window + 1)
            results = await pipe.execute()

        current_count = results[1]  # zcard result before adding current request

        if current_count >= self._limit:
            # Rate limited - remove the entry we just added
            await self._redis.zremrangebyscore(key, now_ms, now_ms)
            oldest = await self._redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                oldest_ts = oldest[0][1]
            else:
                oldest_ts = now_ms
            reset_in = max(1, int((oldest_ts + (self._window * 1000) - now_ms) / 1000))
            return False, 0, reset_in

        remaining = max(0, self._limit - current_count - 1)
        reset_in = self._window

        return True, remaining, reset_in

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()