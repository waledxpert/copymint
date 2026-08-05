from uuid import UUID

import pytest

from app.application.access.updates import TelegramUpdateDeduplicator
from app.domain.ids import uuid7


class FakeUpdateRepository:
    def __init__(self) -> None:
        self.claimed: set[tuple[str, int]] = set()
        self.status: dict[tuple[str, int], tuple[str, str | None]] = {}

    async def claim(self, *, bot_id: str, update_id: int, correlation_id: UUID) -> bool:
        key = (bot_id, update_id)
        if key in self.claimed:
            return False
        self.claimed.add(key)
        self.status[key] = ("received", None)
        return True

    async def mark_processed(self, *, bot_id: str, update_id: int) -> None:
        self.status[(bot_id, update_id)] = ("processed", None)

    async def mark_failed(self, *, bot_id: str, update_id: int, failure_code: str) -> None:
        self.status[(bot_id, update_id)] = ("failed", failure_code)


@pytest.mark.asyncio
async def test_duplicate_telegram_update_is_claimed_once() -> None:
    repository = FakeUpdateRepository()
    service = TelegramUpdateDeduplicator(repository)
    assert await service.claim(bot_id="bot-1", update_id=42, correlation_id=uuid7())
    assert not await service.claim(bot_id="bot-1", update_id=42, correlation_id=uuid7())
    await service.processed(bot_id="bot-1", update_id=42)
    assert repository.status[("bot-1", 42)] == ("processed", None)


@pytest.mark.asyncio
async def test_failure_code_is_bounded() -> None:
    service = TelegramUpdateDeduplicator(FakeUpdateRepository())
    with pytest.raises(ValueError):
        await service.failed(bot_id="bot-1", update_id=1, failure_code="x" * 65)
