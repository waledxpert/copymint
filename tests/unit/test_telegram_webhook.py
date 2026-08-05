from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from aiogram import Bot
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes.telegram import router


class FakeUpdates:
    def __init__(self) -> None:
        self.states: dict[tuple[str, int], str] = {}

    async def claim(self, *, bot_id: str, update_id: int, correlation_id: UUID) -> bool:
        key = (bot_id, update_id)
        if self.states.get(key) not in (None, "failed"):
            return False
        self.states[key] = "received"
        return True

    async def processed(self, *, bot_id: str, update_id: int) -> None:
        self.states[(bot_id, update_id)] = "processed"

    async def failed(self, *, bot_id: str, update_id: int, failure_code: str) -> None:
        self.states[(bot_id, update_id)] = "failed"


@dataclass
class FakeDispatcher:
    fail: bool = False
    update_ids: list[int] = field(default_factory=list)

    async def feed_update(self, bot: Bot, update: Any) -> None:
        self.update_ids.append(update.update_id)
        if self.fail:
            raise RuntimeError("safe synthetic failure")


@pytest.fixture
async def webhook_app() -> tuple[FastAPI, Bot, FakeDispatcher, FakeUpdates]:
    app = FastAPI()
    app.include_router(router)
    bot = Bot(f"{123456789}:{'x' * 35}")
    dispatcher = FakeDispatcher()
    updates = FakeUpdates()
    app.state.telegram_runtime = type(
        "Runtime",
        (),
        {
            "bot": bot,
            "dispatcher": dispatcher,
            "updates": updates,
            "webhook_secret": "w" * 32,
            "bot_id": str(bot.id),
        },
    )()
    try:
        yield app, bot, dispatcher, updates
    finally:
        await bot.session.close()


def update_payload(update_id: int) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": 1_786_000_000,
            "chat": {"id": 99, "type": "private"},
            "from": {"id": 99, "is_bot": False, "first_name": "Tester"},
            "text": "/start",
        },
    }


@pytest.mark.asyncio
async def test_webhook_rejects_bad_secret_before_claiming(
    webhook_app: tuple[FastAPI, Bot, FakeDispatcher, FakeUpdates],
) -> None:
    app, _, dispatcher, updates = webhook_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/telegram/webhook", json=update_payload(10))
    assert response.status_code == 401
    assert dispatcher.update_ids == []
    assert updates.states == {}


@pytest.mark.asyncio
async def test_webhook_processes_each_update_once(
    webhook_app: tuple[FastAPI, Bot, FakeDispatcher, FakeUpdates],
) -> None:
    app, _, dispatcher, updates = webhook_app
    headers = {"X-Telegram-Bot-Api-Secret-Token": "w" * 32}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/telegram/webhook", json=update_payload(11), headers=headers)
        duplicate = await client.post("/telegram/webhook", json=update_payload(11), headers=headers)
    assert first.json() == {"status": "processed"}
    assert duplicate.json() == {"status": "duplicate"}
    assert dispatcher.update_ids == [11]
    assert updates.states[("123456789", 11)] == "processed"


@pytest.mark.asyncio
async def test_failed_dispatch_is_retryable(
    webhook_app: tuple[FastAPI, Bot, FakeDispatcher, FakeUpdates],
) -> None:
    app, _, dispatcher, updates = webhook_app
    headers = {"X-Telegram-Bot-Api-Secret-Token": "w" * 32}
    dispatcher.fail = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        failed = await client.post("/telegram/webhook", json=update_payload(12), headers=headers)
        dispatcher.fail = False
        retried = await client.post("/telegram/webhook", json=update_payload(12), headers=headers)
    assert failed.status_code == 503
    assert retried.json() == {"status": "processed"}
    assert dispatcher.update_ids == [12, 12]
    assert updates.states[("123456789", 12)] == "processed"
