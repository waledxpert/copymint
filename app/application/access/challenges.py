"""Opaque, actor-bound, chat-bound, expiring callback challenges."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.application.access.context import AccessDenied, RequestContext
from app.domain.enums import ChallengeAction


class InvalidChallenge(AccessDenied):
    code = "invalid_challenge"


@dataclass(frozen=True, slots=True)
class ChallengeRecord:
    id: UUID
    token_hash: bytes
    action: ChallengeAction
    expected_actor_telegram_user_id: int
    expected_chat_id: int
    resource_type: str
    resource_id: UUID
    authoritative_payload: dict[str, Any]
    expires_at: datetime
    consumed_at: datetime | None


@dataclass(frozen=True, slots=True)
class IssuedChallenge:
    token: str
    record: ChallengeRecord


class ChallengeRepository(Protocol):
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
    ) -> ChallengeRecord: ...

    async def consume_challenge(
        self,
        *,
        token_hash: bytes,
        expected_action: ChallengeAction,
        expected_actor_telegram_user_id: int,
        expected_chat_id: int,
        consumed_at: datetime,
    ) -> ChallengeRecord | None: ...


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def hash_challenge_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


class ChallengeService:
    def __init__(
        self,
        repository: ChallengeRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
        default_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if default_ttl <= timedelta(0) or default_ttl > timedelta(minutes=15):
            raise ValueError("challenge TTL must be greater than zero and at most 15 minutes")
        self._repository = repository
        self._clock = clock
        self._default_ttl = default_ttl

    async def issue(
        self,
        actor: RequestContext,
        *,
        action: ChallengeAction,
        resource_type: str,
        resource_id: UUID,
        authoritative_payload: dict[str, Any] | None = None,
    ) -> IssuedChallenge:
        if action is ChallengeAction.CREATE_WALLET:
            actor.require_workspace()
        else:
            actor.require_platform_owner()
        raw_token = secrets.token_urlsafe(32)
        record = await self._repository.create_challenge(
            token_hash=hash_challenge_token(raw_token),
            action=action,
            expected_actor_telegram_user_id=actor.telegram_user_id,
            expected_chat_id=actor.chat_id,
            resource_type=resource_type,
            resource_id=resource_id,
            authoritative_payload=authoritative_payload or {},
            expires_at=self._clock() + self._default_ttl,
        )
        return IssuedChallenge(token=raw_token, record=record)

    async def consume(
        self,
        actor: RequestContext,
        *,
        token: str,
        expected_action: ChallengeAction,
    ) -> ChallengeRecord:
        if expected_action is ChallengeAction.CREATE_WALLET:
            actor.require_workspace()
        else:
            actor.require_platform_owner()
        now = self._clock()
        record = await self._repository.consume_challenge(
            token_hash=hash_challenge_token(token),
            expected_action=expected_action,
            expected_actor_telegram_user_id=actor.telegram_user_id,
            expected_chat_id=actor.chat_id,
            consumed_at=now,
        )
        if record is None:
            raise InvalidChallenge("The confirmation is invalid, expired, or already consumed.")
        return record
