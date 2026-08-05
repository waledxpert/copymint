from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.application.access.challenges import (
    ChallengeRecord,
    ChallengeService,
    InvalidChallenge,
)
from app.application.access.context import RequestContext
from app.domain.enums import ChallengeAction, PlatformRole
from app.domain.ids import uuid7

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class FakeChallengeRepository:
    def __init__(self) -> None:
        self.records: dict[bytes, ChallengeRecord] = {}

    async def create_challenge(self, **values: object) -> ChallengeRecord:
        record = ChallengeRecord(id=uuid7(), consumed_at=None, **values)  # type: ignore[arg-type]
        self.records[record.token_hash] = record
        return record

    async def consume_challenge(self, **values: object) -> ChallengeRecord | None:
        token_hash = values["token_hash"]
        assert isinstance(token_hash, bytes)
        record = self.records.get(token_hash)
        consumed_at = values["consumed_at"]
        assert isinstance(consumed_at, datetime)
        if (
            record is None
            or record.consumed_at is not None
            or record.expires_at <= consumed_at
            or record.action is not values["expected_action"]
            or record.expected_actor_telegram_user_id != values["expected_actor_telegram_user_id"]
            or record.expected_chat_id != values["expected_chat_id"]
        ):
            return None
        consumed = replace(record, consumed_at=consumed_at)
        self.records[token_hash] = consumed
        return consumed


def owner(user_id: int = 1) -> RequestContext:
    return RequestContext(
        telegram_user_id=user_id,
        chat_id=user_id,
        chat_type="private",
        correlation_id=uuid7(),
        platform_role=PlatformRole.PLATFORM_OWNER,
    )


@pytest.mark.asyncio
async def test_challenge_is_opaque_bound_and_single_use() -> None:
    repository = FakeChallengeRepository()
    service = ChallengeService(repository, clock=lambda: NOW, default_ttl=timedelta(minutes=5))
    resource_id = uuid7()

    issued = await service.issue(
        owner(),
        action=ChallengeAction.APPROVE_ACCESS,
        resource_type="access_request",
        resource_id=resource_id,
        authoritative_payload={"decision": "approve"},
    )
    assert issued.token.encode("ascii") != issued.record.token_hash
    assert len(issued.record.token_hash) == 32
    assert issued.record.resource_id == resource_id

    consumed = await service.consume(
        owner(), token=issued.token, expected_action=ChallengeAction.APPROVE_ACCESS
    )
    assert consumed.consumed_at == NOW
    with pytest.raises(InvalidChallenge):
        await service.consume(
            owner(), token=issued.token, expected_action=ChallengeAction.APPROVE_ACCESS
        )


@pytest.mark.asyncio
async def test_challenge_rejects_wrong_actor_action_and_expiry() -> None:
    repository = FakeChallengeRepository()
    service = ChallengeService(repository, clock=lambda: NOW)
    issued = await service.issue(
        owner(),
        action=ChallengeAction.REJECT_ACCESS,
        resource_type="access_request",
        resource_id=uuid7(),
    )
    with pytest.raises(InvalidChallenge):
        await service.consume(
            owner(2), token=issued.token, expected_action=ChallengeAction.REJECT_ACCESS
        )
    with pytest.raises(InvalidChallenge):
        await service.consume(
            owner(), token=issued.token, expected_action=ChallengeAction.APPROVE_ACCESS
        )

    late_service = ChallengeService(repository, clock=lambda: NOW + timedelta(minutes=10))
    with pytest.raises(InvalidChallenge):
        await late_service.consume(
            owner(), token=issued.token, expected_action=ChallengeAction.REJECT_ACCESS
        )


def test_challenge_ttl_has_a_hard_upper_bound() -> None:
    with pytest.raises(ValueError, match="at most 15 minutes"):
        ChallengeService(FakeChallengeRepository(), default_ttl=timedelta(hours=1))
