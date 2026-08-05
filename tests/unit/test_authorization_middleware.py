from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.types import Chat, Message, TelegramObject, User

from app.application.access.context import AccessDenied, RequestContext, TelegramIdentity
from app.bot.middleware.authorization import RequestContextMiddleware, identity_from_event
from app.domain.ids import uuid7


def message(*, chat_type: str = "private", text: str | None = None) -> Message:
    user_id = 99
    return Message(
        message_id=1,
        date=datetime(2026, 8, 5, tzinfo=UTC),
        chat=Chat(id=user_id if chat_type == "private" else -1001, type=chat_type),
        from_user=User(
            id=user_id,
            is_bot=False,
            first_name="Test",
            last_name="User",
            username="tester",
        ),
        text=text,
    )


class FakeAccessService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    async def resolve_context(self, identity: TelegramIdentity) -> RequestContext:
        if self.error:
            raise self.error
        return RequestContext(
            telegram_user_id=identity.telegram_user_id,
            chat_id=identity.chat_id,
            chat_type=identity.chat_type,
            correlation_id=uuid7(),
            user_id=uuid7(),
            workspace_id=uuid7(),
        )


async def passthrough(event: TelegramObject, data: dict[str, Any]) -> dict[str, Any]:
    return data


def test_identity_is_derived_from_telegram_objects() -> None:
    identity = identity_from_event(message())
    assert identity == TelegramIdentity(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        username="tester",
        display_name="Test User",
    )
    assert identity_from_event(TelegramObject()) is None


@pytest.mark.asyncio
async def test_middleware_attaches_server_derived_context() -> None:
    middleware = RequestContextMiddleware(FakeAccessService())  # type: ignore[arg-type]
    result = await middleware(passthrough, message(), {})
    assert result["telegram_identity"].telegram_user_id == 99
    assert result["request_context"].workspace_id is not None
    assert result["access_error"] is None


@pytest.mark.asyncio
async def test_middleware_preserves_safe_access_error_for_public_handlers() -> None:
    middleware = RequestContextMiddleware(  # type: ignore[arg-type]
        FakeAccessService(error=AccessDenied("not approved"))
    )
    handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]] = passthrough
    result = await middleware(handler, message(), {})
    assert result["request_context"] is None
    assert isinstance(result["access_error"], AccessDenied)


@pytest.mark.asyncio
async def test_protected_unauthorized_attempt_is_audited() -> None:
    class FakeAudit:
        def __init__(self) -> None:
            self.codes: list[str] = []

        async def unauthorized_attempt(self, **values: Any) -> None:
            self.codes.append(values["code"])

    audit = FakeAudit()
    middleware = RequestContextMiddleware(  # type: ignore[arg-type]
        FakeAccessService(error=AccessDenied("not approved")),
        audit,  # type: ignore[arg-type]
    )
    await middleware(passthrough, message(text="/admin_requests"), {})
    assert audit.codes == ["access_denied"]

    await middleware(passthrough, message(text="/start"), {})
    assert audit.codes == ["access_denied"]
