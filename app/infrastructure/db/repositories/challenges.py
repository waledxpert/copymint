"""Atomic callback challenge creation and consumption."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.access.challenges import ChallengeRecord
from app.domain.enums import ChallengeAction
from app.infrastructure.db.models.access import CallbackChallenge


def challenge_record(model: CallbackChallenge) -> ChallengeRecord:
    return ChallengeRecord(
        id=model.id,
        token_hash=model.token_hash,
        action=model.action,
        expected_actor_telegram_user_id=model.expected_actor_telegram_user_id,
        expected_chat_id=model.expected_chat_id,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        authoritative_payload=model.authoritative_payload,
        expires_at=model.expires_at,
        consumed_at=model.consumed_at,
    )


class SqlAlchemyChallengeRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_challenge(
        self,
        *,
        token_hash: bytes,
        action: ChallengeAction,
        expected_actor_telegram_user_id: int,
        expected_chat_id: int,
        resource_type: str,
        resource_id: UUID,
        authoritative_payload: dict[str, Any],
        expires_at: datetime,
    ) -> ChallengeRecord:
        model = CallbackChallenge(
            token_hash=token_hash,
            action=action,
            expected_actor_telegram_user_id=expected_actor_telegram_user_id,
            expected_chat_id=expected_chat_id,
            resource_type=resource_type,
            resource_id=resource_id,
            authoritative_payload=authoritative_payload,
            expires_at=expires_at,
        )
        async with self._sessions() as session, session.begin():
            session.add(model)
            await session.flush()
            return challenge_record(model)

    async def consume_challenge(
        self,
        *,
        token_hash: bytes,
        expected_action: ChallengeAction,
        expected_actor_telegram_user_id: int,
        expected_chat_id: int,
        consumed_at: datetime,
    ) -> ChallengeRecord | None:
        statement = (
            update(CallbackChallenge)
            .where(
                CallbackChallenge.token_hash == token_hash,
                CallbackChallenge.action == expected_action,
                CallbackChallenge.expected_actor_telegram_user_id
                == expected_actor_telegram_user_id,
                CallbackChallenge.expected_chat_id == expected_chat_id,
                CallbackChallenge.expires_at > consumed_at,
                CallbackChallenge.consumed_at.is_(None),
            )
            .values(consumed_at=consumed_at)
            .returning(CallbackChallenge)
        )
        async with self._sessions() as session, session.begin():
            model = (await session.execute(statement)).scalar_one_or_none()
            return challenge_record(model) if model else None
