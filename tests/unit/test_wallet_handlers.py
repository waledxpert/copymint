from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from app.application.access.context import RequestContext
from app.application.wallets.ports import WalletRecord
from app.bot.handlers.wallets import (
    CUSTODY_NOTICE,
    build_wallet_router,
    format_wei,
    wallet_callback_data,
)
from app.domain.enums import WalletStatus, WorkspaceRole
from app.domain.ids import uuid7


def handler(router: Any, observer: str, name: str) -> Any:
    return next(
        item.callback
        for item in getattr(router, observer).handlers
        if item.callback.__name__ == name
    )


def context() -> RequestContext:
    return RequestContext(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        correlation_id=uuid7(),
        user_id=uuid7(),
        workspace_id=uuid7(),
        workspace_role=WorkspaceRole.OWNER,
    )


@dataclass
class FakeMessage:
    answers: list[tuple[str, Any]] = field(default_factory=list)

    async def answer(self, text: str, reply_markup: Any = None) -> None:
        self.answers.append((text, reply_markup))


class FakeChallenges:
    def __init__(self, request_context: RequestContext) -> None:
        self.context = request_context
        self.payload: dict[str, Any] = {}

    async def issue(self, actor: RequestContext, **values: Any) -> Any:
        self.payload = values["authoritative_payload"]
        return SimpleNamespace(token="opaque-token")

    async def consume(self, actor: RequestContext, **values: Any) -> Any:
        return SimpleNamespace(
            resource_id=self.context.workspace_id,
            authoritative_payload=self.payload or {"idempotency_key": "wallet-request-001"},
        )


class FakeWalletService:
    def __init__(self, request_context: RequestContext) -> None:
        self.wallet = WalletRecord(
            id=uuid7(),
            workspace_id=request_context.workspace_id,  # type: ignore[arg-type]
            chain_id=1,
            address="0x1111111111111111111111111111111111111111",
            signer_key_id=uuid7(),
            status=WalletStatus.ACTIVE,
            balance_wei=1_250_000_000_000_000_000,
        )

    async def create_wallet(self, *args: Any, **kwargs: Any) -> tuple[WalletRecord, bool]:
        return self.wallet, True

    async def list_wallets(self, *args: Any, **kwargs: Any) -> list[WalletRecord]:
        return [self.wallet]


@pytest.mark.asyncio
async def test_create_wallet_command_displays_custody_confirmation() -> None:
    router = build_wallet_router()
    command = handler(router, "message", "create_wallet_command")
    request_context = context()
    message = FakeMessage()
    challenges = FakeChallenges(request_context)
    await command(message, request_context, None, challenges)
    assert message.answers[0][0] == CUSTODY_NOTICE
    assert message.answers[0][1].inline_keyboard[0][0].callback_data.startswith("wallet:v1:create:")
    assert challenges.payload["chain_id"] == 1


@pytest.mark.asyncio
async def test_wallet_callback_creates_wallet_and_replaces_confirmation() -> None:
    router = build_wallet_router()
    callback_handler = handler(router, "callback_query", "create_wallet_callback")
    request_context = context()
    challenges = FakeChallenges(request_context)
    service = FakeWalletService(request_context)

    class FakeCallback:
        data = "wallet:v1:create:opaque-token"
        message = SimpleNamespace(chat=SimpleNamespace(id=99), message_id=2)

        def __init__(self) -> None:
            self.answers: list[tuple[str, bool]] = []

        async def answer(self, text: str, show_alert: bool) -> None:
            self.answers.append((text, show_alert))

    class FakeBot:
        def __init__(self) -> None:
            self.text = ""

        async def edit_message_text(self, **values: Any) -> None:
            self.text = values["text"]

    callback = FakeCallback()
    bot = FakeBot()
    await callback_handler(callback, bot, request_context, None, challenges, service)
    assert callback.answers == [("Execution wallet created.", True)]
    assert service.wallet.address in bot.text
    assert "Signing and broadcasting remain disabled" in bot.text


def test_wallet_display_uses_exact_integer_wei_formatting() -> None:
    assert format_wei(0) == "0"
    assert format_wei(10**18) == "1"
    assert format_wei(1_250_000_000_000_000_000) == "1.25"
    assert wallet_callback_data("opaque-token") == "wallet:v1:create:opaque-token"
