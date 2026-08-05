from typing import Any

import pytest
from aiogram.types import TelegramObject

from app.application.access.context import RequestContext, TelegramIdentity
from app.bot.middleware.rate_limit import TelegramRateLimitMiddleware
from app.domain.ids import uuid7
from app.infrastructure.queue.rate_limit import RateLimitDecision


class FakeLimiter:
    def __init__(self, decisions: list[bool]) -> None:
        self.decisions = decisions
        self.calls: list[tuple[str, str]] = []

    async def hit(self, **values: Any) -> RateLimitDecision:
        self.calls.append((values["scope"], values["subject"]))
        allowed = self.decisions.pop(0)
        return RateLimitDecision(allowed, 1, values["limit"], 17)


async def handled(event: TelegramObject, data: dict[str, Any]) -> str:
    return "handled"


def data_with_workspace() -> dict[str, Any]:
    workspace_id = uuid7()
    return {
        "telegram_identity": TelegramIdentity(99, 99, "private"),
        "request_context": RequestContext(
            telegram_user_id=99,
            chat_id=99,
            chat_type="private",
            correlation_id=uuid7(),
            workspace_id=workspace_id,
        ),
    }


@pytest.mark.asyncio
async def test_rate_limit_checks_user_and_workspace() -> None:
    limiter = FakeLimiter([True, True])
    middleware = TelegramRateLimitMiddleware(
        limiter,  # type: ignore[arg-type]
        user_limit_per_minute=30,
        workspace_limit_per_minute=120,
    )
    result = await middleware(handled, TelegramObject(), data_with_workspace())
    assert result == "handled"
    assert [scope for scope, _ in limiter.calls] == ["telegram_user", "workspace"]


@pytest.mark.asyncio
async def test_rate_limit_rejects_before_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = FakeLimiter([False])
    middleware = TelegramRateLimitMiddleware(
        limiter,  # type: ignore[arg-type]
        user_limit_per_minute=30,
        workspace_limit_per_minute=120,
    )
    rejected: list[int] = []

    async def reject(event: TelegramObject, retry_after: int) -> None:
        rejected.append(retry_after)

    monkeypatch.setattr(TelegramRateLimitMiddleware, "_reject", staticmethod(reject))
    result = await middleware(handled, TelegramObject(), data_with_workspace())
    assert result is None
    assert rejected == [17]
