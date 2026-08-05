from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.access.context import AccessError, RequestContext, TelegramIdentity
from app.application.access.ports import AccessDecisionResult, AccessRequestOutcome
from app.bot.handlers.access import (
    build_access_router,
    callback_data,
    require_context,
    require_identity,
)
from app.domain.enums import AccessRequestStatus, ChallengeAction
from app.domain.ids import uuid7


def handler(router: Any, observer: str, name: str) -> Any:
    handlers = getattr(router, observer).handlers
    return next(item.callback for item in handlers if item.callback.__name__ == name)


@dataclass
class FakeMessage:
    text: str = "/start"
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None) -> None:
        self.answers.append((text, reply_markup))


@dataclass
class FakeBot:
    sent: list[tuple[int, str, Any]] = field(default_factory=list)
    edits: list[tuple[int, int, str]] = field(default_factory=list)

    async def send_message(self, chat_id: int, text: str, reply_markup: Any = None) -> None:
        self.sent.append((chat_id, text, reply_markup))

    async def edit_message_text(self, *, chat_id: int, message_id: int, text: str) -> None:
        self.edits.append((chat_id, message_id, text))


class FakeChallengeService:
    def __init__(self) -> None:
        self.issued: list[tuple[ChallengeAction, dict[str, Any]]] = []
        self.resource_id = uuid7()

    async def issue(self, actor: RequestContext, **values: Any) -> Any:
        self.issued.append((values["action"], values))
        return SimpleNamespace(token=f"token-{len(self.issued)}")

    async def consume(self, actor: RequestContext, **values: Any) -> Any:
        return SimpleNamespace(resource_id=self.resource_id, authoritative_payload={})


class FakeAccessService:
    def __init__(self, request_id: Any) -> None:
        self.request_id = request_id
        self.approved = False

    async def request_access(self, identity: TelegramIdentity) -> AccessRequestOutcome:
        return AccessRequestOutcome(state="pending", request_id=self.request_id, created=True)

    async def approve(self, context: RequestContext, request_id: Any) -> AccessDecisionResult:
        self.approved = True
        return AccessDecisionResult(
            request_id=request_id,
            telegram_user_id=99,
            status=AccessRequestStatus.APPROVED,
        )


def owner_context() -> RequestContext:
    return RequestContext.platform_owner(
        TelegramIdentity(telegram_user_id=7, chat_id=7, chat_type="private")
    )


def test_callback_data_and_context_guards() -> None:
    identity = TelegramIdentity(telegram_user_id=1, chat_id=1, chat_type="private")
    assert require_identity(identity) is identity
    with pytest.raises(AccessError):
        require_identity(None)
    context = owner_context()
    assert require_context(context, None) is context
    with pytest.raises(AccessError):
        require_context(None, None)
    with pytest.raises(ValueError):
        callback_data("approve", "x" * 64)


@pytest.mark.asyncio
async def test_start_creates_owner_challenges_and_notifies_owner() -> None:
    router = build_access_router()
    start = handler(router, "message", "start")
    request_id = uuid7()
    access = FakeAccessService(request_id)
    challenges = FakeChallengeService()
    message = FakeMessage()
    bot = FakeBot()
    identity = TelegramIdentity(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        username="tester",
        display_name="Test User",
    )

    await start(
        message,
        bot,
        identity,
        access,
        challenges,
        frozenset({7}),
    )

    assert message.answers[0][0].startswith("Access request received")
    assert [item[0] for item in challenges.issued] == [
        ChallengeAction.APPROVE_ACCESS,
        ChallengeAction.REJECT_ACCESS,
    ]
    assert bot.sent[0][0] == 7
    assert "Telegram ID: 99" in bot.sent[0][1]


@pytest.mark.asyncio
async def test_approval_callback_consumes_challenge_and_edits_message() -> None:
    router = build_access_router()
    callback_handler = handler(router, "callback_query", "access_callback")
    access = FakeAccessService(uuid7())
    challenges = FakeChallengeService()
    bot = FakeBot()

    class FakeCallback:
        data = "access:v1:approve:opaque-token"
        message = SimpleNamespace(chat=SimpleNamespace(id=7), message_id=22)

        def __init__(self) -> None:
            self.answers: list[tuple[str, bool]] = []

        async def answer(self, text: str, show_alert: bool) -> None:
            self.answers.append((text, show_alert))

    callback = FakeCallback()
    await callback_handler(callback, bot, owner_context(), None, access, challenges)

    assert access.approved
    assert callback.answers == [("Approved Telegram ID 99.", True)]
    assert bot.sent[0][:2] == (
        99,
        "Your CopyMint access request was approved. Use /help to begin.",
    )
    assert bot.edits == [(7, 22, "Approved Telegram ID 99.")]
