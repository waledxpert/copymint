"""Per-user and per-workspace Telegram rate limiting."""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.application.access.context import RequestContext, TelegramIdentity
from app.infrastructure.queue.rate_limit import RateLimitDecision


class RateLimiter(Protocol):
    async def hit(
        self, *, scope: str, subject: str, limit: int, window_seconds: int
    ) -> RateLimitDecision: ...


class TelegramRateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        limiter: RateLimiter,
        *,
        user_limit_per_minute: int,
        workspace_limit_per_minute: int,
    ) -> None:
        self._limiter = limiter
        self._user_limit = user_limit_per_minute
        self._workspace_limit = workspace_limit_per_minute

    @staticmethod
    async def _reject(event: TelegramObject, retry_after: int) -> None:
        text = f"Too many requests. Try again in {retry_after} seconds."
        if isinstance(event, Message):
            await event.answer(text)
        elif isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity: TelegramIdentity | None = data.get("telegram_identity")
        if identity is None:
            return await handler(event, data)

        user_decision = await self._limiter.hit(
            scope="telegram_user",
            subject=str(identity.telegram_user_id),
            limit=self._user_limit,
            window_seconds=60,
        )
        if not user_decision.allowed:
            await self._reject(event, user_decision.retry_after_seconds)
            return None

        context: RequestContext | None = data.get("request_context")
        if context is not None and context.workspace_id is not None:
            workspace_decision = await self._limiter.hit(
                scope="workspace",
                subject=str(context.workspace_id),
                limit=self._workspace_limit,
                window_seconds=60,
            )
            if not workspace_decision.allowed:
                await self._reject(event, workspace_decision.retry_after_seconds)
                return None
        return await handler(event, data)
