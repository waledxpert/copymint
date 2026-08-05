"""Fixed-window Redis rate limiting for Telegram and workspace actions."""

from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    count: int
    limit: int
    retry_after_seconds: int


class RedisRateLimiter:
    def __init__(self, redis: Redis, *, environment: str) -> None:
        if not environment:
            raise ValueError("rate-limit environment prefix is required")
        self._redis = redis
        self._prefix = f"copymint:{environment}:rate"

    async def hit(
        self,
        *,
        scope: str,
        subject: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        if not scope or not subject:
            raise ValueError("rate-limit scope and subject are required")
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate-limit and window must be positive")

        key = f"{self._prefix}:{scope}:{subject}"
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.incr(key)
        pipeline.expire(key, window_seconds, nx=True)
        pipeline.ttl(key)
        count_value, _, ttl_value = await pipeline.execute()
        count = int(count_value)
        ttl = max(int(ttl_value), 1)
        return RateLimitDecision(
            allowed=count <= limit,
            count=count,
            limit=limit,
            retry_after_seconds=ttl,
        )
