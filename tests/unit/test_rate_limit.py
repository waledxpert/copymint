import pytest

from app.infrastructure.queue.rate_limit import RedisRateLimiter


class FakePipeline:
    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.commands: list[tuple[object, ...]] = []

    def incr(self, key: str) -> "FakePipeline":
        self.commands.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, *, nx: bool) -> "FakePipeline":
        self.commands.append(("expire", key, seconds, nx))
        return self

    def ttl(self, key: str) -> "FakePipeline":
        self.commands.append(("ttl", key))
        return self

    async def execute(self) -> list[object]:
        return self.responses


class FakeRedis:
    def __init__(self, responses: list[object]) -> None:
        self.pipeline_instance = FakePipeline(responses)

    def pipeline(self, *, transaction: bool) -> FakePipeline:
        assert transaction
        return self.pipeline_instance


@pytest.mark.asyncio
async def test_rate_limit_allows_then_blocks_at_limit() -> None:
    allowed_redis = FakeRedis([2, True, 30])
    limiter = RedisRateLimiter(allowed_redis, environment="test")  # type: ignore[arg-type]
    allowed = await limiter.hit(scope="telegram", subject="99", limit=2, window_seconds=60)
    assert allowed.allowed
    assert allowed.count == 2
    assert allowed.retry_after_seconds == 30

    blocked_redis = FakeRedis([3, False, -1])
    limiter = RedisRateLimiter(blocked_redis, environment="test")  # type: ignore[arg-type]
    blocked = await limiter.hit(scope="telegram", subject="99", limit=2, window_seconds=60)
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 1


@pytest.mark.asyncio
async def test_rate_limit_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        RedisRateLimiter(FakeRedis([]), environment="")  # type: ignore[arg-type]
    limiter = RedisRateLimiter(FakeRedis([]), environment="test")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        await limiter.hit(scope="", subject="99", limit=1, window_seconds=60)
    with pytest.raises(ValueError):
        await limiter.hit(scope="telegram", subject="99", limit=0, window_seconds=60)
