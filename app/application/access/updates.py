"""Durable Telegram update idempotency contract."""

from typing import Protocol
from uuid import UUID


class TelegramUpdateRepository(Protocol):
    async def claim(self, *, bot_id: str, update_id: int, correlation_id: UUID) -> bool: ...

    async def mark_processed(self, *, bot_id: str, update_id: int) -> None: ...

    async def mark_failed(self, *, bot_id: str, update_id: int, failure_code: str) -> None: ...


class TelegramUpdateDeduplicator:
    def __init__(self, repository: TelegramUpdateRepository) -> None:
        self._repository = repository

    async def claim(self, *, bot_id: str, update_id: int, correlation_id: UUID) -> bool:
        if not bot_id or len(bot_id) > 32:
            raise ValueError("bot_id must contain between 1 and 32 characters")
        if update_id < 0:
            raise ValueError("Telegram update_id cannot be negative")
        return await self._repository.claim(
            bot_id=bot_id, update_id=update_id, correlation_id=correlation_id
        )

    async def processed(self, *, bot_id: str, update_id: int) -> None:
        await self._repository.mark_processed(bot_id=bot_id, update_id=update_id)

    async def failed(self, *, bot_id: str, update_id: int, failure_code: str) -> None:
        if not failure_code or len(failure_code) > 64:
            raise ValueError("failure_code must contain between 1 and 64 characters")
        await self._repository.mark_failed(
            bot_id=bot_id, update_id=update_id, failure_code=failure_code
        )
