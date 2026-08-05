"""PostgreSQL-backed Telegram update deduplication."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.enums import TelegramUpdateStatus
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import TelegramUpdate


class SqlAlchemyTelegramUpdateRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def claim(self, *, bot_id: str, update_id: int, correlation_id: UUID) -> bool:
        statement = (
            insert(TelegramUpdate)
            .values(
                id=uuid7(),
                bot_id=bot_id,
                update_id=update_id,
                status=TelegramUpdateStatus.RECEIVED,
                correlation_id=correlation_id,
            )
            .on_conflict_do_update(
                index_elements=[TelegramUpdate.bot_id, TelegramUpdate.update_id],
                set_={
                    "status": TelegramUpdateStatus.RECEIVED,
                    "correlation_id": correlation_id,
                    "failure_code": None,
                    "processed_at": None,
                },
                where=TelegramUpdate.status == TelegramUpdateStatus.FAILED,
            )
            .returning(TelegramUpdate.id)
        )
        async with self._sessions() as session, session.begin():
            return (await session.scalar(statement)) is not None

    async def mark_processed(self, *, bot_id: str, update_id: int) -> None:
        await self._mark(
            bot_id=bot_id,
            update_id=update_id,
            status=TelegramUpdateStatus.PROCESSED,
            failure_code=None,
        )

    async def mark_failed(self, *, bot_id: str, update_id: int, failure_code: str) -> None:
        await self._mark(
            bot_id=bot_id,
            update_id=update_id,
            status=TelegramUpdateStatus.FAILED,
            failure_code=failure_code,
        )

    async def _mark(
        self,
        *,
        bot_id: str,
        update_id: int,
        status: TelegramUpdateStatus,
        failure_code: str | None,
    ) -> None:
        statement = (
            update(TelegramUpdate)
            .where(TelegramUpdate.bot_id == bot_id, TelegramUpdate.update_id == update_id)
            .values(
                status=status,
                processed_at=datetime.now(tz=UTC),
                failure_code=failure_code,
            )
        )
        async with self._sessions() as session, session.begin():
            await session.execute(statement)
