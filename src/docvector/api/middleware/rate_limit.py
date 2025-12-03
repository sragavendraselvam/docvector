"""Rate limiting middleware using Redis."""

import time
from typing import Optional

from fastapi import HTTPException, Request, status

from docvector.core import get_logger, settings

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.redis_url
        self._redis = None

    async def get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            import redis.asyncio as redis
            self._redis = redis.from_url(self.redis_url)
        return self._redis

    async def check_rate_limit(
        self,
        key: str,
        limit_per_second: int = 5,
        limit_per_day: Optional[int] = None,
    ) -> tuple[bool, dict]:
        """Check if request is within rate limits.

        Args:
            key: Unique identifier for rate limiting (e.g., api_key_id, user_id, ip)
            limit_per_second: Requests per second limit
            limit_per_day: Requests per day limit (optional)

        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        redis = await self.get_redis()
        now = time.time()
        second_key = f"ratelimit:second:{key}"
        day_key = f"ratelimit:day:{key}"

        # Check per-second limit using sliding window
        pipe = redis.pipeline()
        pipe.zremrangebyscore(second_key, 0, now - 1)  # Remove old entries
        pipe.zcard(second_key)  # Count current entries
        pipe.zadd(second_key, {str(now): now})  # Add current request
        pipe.expire(second_key, 2)  # Expire after 2 seconds

        results = await pipe.execute()
        current_second = results[1]

        if current_second >= limit_per_second:
            return False, {
                "limit": limit_per_second,
                "remaining": 0,
                "reset": int(now) + 1,
                "type": "second",
            }

        # Check per-day limit if specified
        if limit_per_day:
            pipe = redis.pipeline()
            pipe.incr(day_key)
            pipe.ttl(day_key)
            results = await pipe.execute()

            current_day = results[0]
            ttl = results[1]

            # Set expiry if new key
            if ttl == -1:
                await redis.expire(day_key, 86400)  # 24 hours
                ttl = 86400

            if current_day > limit_per_day:
                return False, {
                    "limit": limit_per_day,
                    "remaining": 0,
                    "reset": int(now) + ttl,
                    "type": "day",
                }

            return True, {
                "limit": limit_per_second,
                "remaining": limit_per_second - current_second - 1,
                "day_limit": limit_per_day,
                "day_remaining": limit_per_day - current_day,
                "reset": int(now) + 1,
            }

        return True, {
            "limit": limit_per_second,
            "remaining": limit_per_second - current_second - 1,
            "reset": int(now) + 1,
        }

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def rate_limit(request: Request):
    """Rate limiting dependency.

    Rate limits are determined by IP address for OSS version.
    Enterprise version adds API key and user-based rate limiting.
    """
    limiter = get_rate_limiter()

    # Use IP address for rate limiting (OSS version)
    client_ip = request.client.host if request.client else "unknown"
    key = f"ip:{client_ip}"
    limit_per_second = 5  # Base limit
    limit_per_day = 1000  # Daily limit

    try:
        is_allowed, info = await limiter.check_rate_limit(
            key=key,
            limit_per_second=limit_per_second,
            limit_per_day=limit_per_day,
        )

        # Add rate limit headers to response
        request.state.rate_limit_info = info

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": info.get("limit"),
                    "reset": info.get("reset"),
                    "type": info.get("type", "second"),
                },
                headers={
                    "X-RateLimit-Limit": str(info.get("limit", 0)),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(info.get("reset", 0)),
                    "Retry-After": str(info.get("reset", 0) - int(time.time())),
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        # If Redis fails, allow request but log error
        logger.error("Rate limiting error", error=str(e))


def add_rate_limit_headers(request: Request, response):
    """Add rate limit headers to response (call from route or middleware)."""
    info = getattr(request.state, "rate_limit_info", None)
    if info:
        response.headers["X-RateLimit-Limit"] = str(info.get("limit", 0))
        response.headers["X-RateLimit-Remaining"] = str(info.get("remaining", 0))
        response.headers["X-RateLimit-Reset"] = str(info.get("reset", 0))
        if "day_limit" in info:
            response.headers["X-RateLimit-Day-Limit"] = str(info.get("day_limit", 0))
            response.headers["X-RateLimit-Day-Remaining"] = str(info.get("day_remaining", 0))
    return response
