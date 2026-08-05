from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.access.challenges import ChallengeService, InvalidChallenge
from app.application.access.context import AccessDenied, TelegramIdentity
from app.application.access.service import AccessService
from app.application.access.updates import TelegramUpdateDeduplicator
from app.domain.enums import AccessRequestStatus, ChallengeAction
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import AuditLog, Workspace
from app.infrastructure.db.repositories.access import (
    SqlAlchemyAccessRepository,
    set_workspace_context,
)
from app.infrastructure.db.repositories.challenges import SqlAlchemyChallengeRepository
from app.infrastructure.db.repositories.telegram_updates import (
    SqlAlchemyTelegramUpdateRepository,
)

pytestmark = pytest.mark.database
NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


def identity(user_id: int) -> TelegramIdentity:
    return TelegramIdentity(
        telegram_user_id=user_id,
        chat_id=user_id,
        chat_type="private",
        username=f"user{user_id}",
        display_name=f"User {user_id}",
    )


@pytest.mark.asyncio
async def test_access_approval_is_atomic_and_creates_private_workspace(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAccessRepository(database_sessions)
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)

    requested = await service.request_access(identity(99))
    assert requested.state == "pending"
    assert requested.request_id is not None

    owner = await service.resolve_context(identity(1))
    approved = await service.approve(owner, requested.request_id)
    assert approved.status is AccessRequestStatus.APPROVED
    assert approved.workspace_id is not None

    user_context = await service.resolve_context(identity(99))
    assert user_context.workspace_id == approved.workspace_id
    assert (await service.request_access(identity(99))).state == "active"


@pytest.mark.asyncio
async def test_workspace_row_level_policy_hides_other_workspace(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAccessRepository(database_sessions)
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    owner = await service.resolve_context(identity(1))

    first_request = await service.request_access(identity(99))
    second_request = await service.request_access(identity(100))
    assert first_request.request_id and second_request.request_id
    first = await service.approve(owner, first_request.request_id)
    second = await service.approve(owner, second_request.request_id)
    assert first.workspace_id and second.workspace_id

    async with database_sessions() as session, session.begin():
        await set_workspace_context(session, first.workspace_id)
        visible = set(await session.scalars(select(Workspace.id)))
        changed = await session.execute(
            update(Workspace)
            .where(Workspace.id == second.workspace_id)
            .values(name="cross-tenant write")
        )
    assert visible == {first.workspace_id}
    assert second.workspace_id not in visible
    assert changed.rowcount == 0

    async with database_sessions() as session, session.begin():
        await set_workspace_context(session, second.workspace_id)
        second_name = await session.scalar(
            select(Workspace.name).where(Workspace.id == second.workspace_id)
        )
    assert second_name != "cross-tenant write"

    async with database_sessions() as session, session.begin():
        await set_workspace_context(session, first.workspace_id)
        audit = await session.scalar(
            select(AuditLog).where(AuditLog.action == "access_request_approved")
        )
    assert audit is not None
    assert audit.actor_id == "1"
    assert audit.resource_id == str(first.request_id)
    assert audit.correlation_id is not None


@pytest.mark.asyncio
async def test_challenge_and_update_deduplication_are_atomic(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    access = AccessService(
        SqlAlchemyAccessRepository(database_sessions),
        platform_owner_ids=frozenset({1}),
        clock=lambda: NOW,
    )
    owner = await access.resolve_context(identity(1))
    challenge_service = ChallengeService(
        SqlAlchemyChallengeRepository(database_sessions), clock=lambda: NOW
    )
    issued = await challenge_service.issue(
        owner,
        action=ChallengeAction.APPROVE_ACCESS,
        resource_type="access_request",
        resource_id=uuid7(),
    )
    await challenge_service.consume(
        owner,
        token=issued.token,
        expected_action=ChallengeAction.APPROVE_ACCESS,
    )
    with pytest.raises(InvalidChallenge):
        await challenge_service.consume(
            owner,
            token=issued.token,
            expected_action=ChallengeAction.APPROVE_ACCESS,
        )

    dedupe = TelegramUpdateDeduplicator(SqlAlchemyTelegramUpdateRepository(database_sessions))
    assert await dedupe.claim(bot_id="test-bot", update_id=1, correlation_id=uuid7())
    assert not await dedupe.claim(bot_id="test-bot", update_id=1, correlation_id=uuid7())
    await dedupe.failed(bot_id="test-bot", update_id=1, failure_code="synthetic_failure")
    assert await dedupe.claim(bot_id="test-bot", update_id=1, correlation_id=uuid7())
    await dedupe.processed(bot_id="test-bot", update_id=1)


@pytest.mark.asyncio
async def test_revocation_removes_access_immediately(
    database_sessions: async_sessionmaker[AsyncSession],
) -> None:
    repository = SqlAlchemyAccessRepository(database_sessions)
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    owner = await service.resolve_context(identity(1))
    request = await service.request_access(identity(99))
    assert request.request_id is not None
    await service.approve(owner, request.request_id)
    assert (await service.resolve_context(identity(99))).workspace_id is not None
    await service.revoke(owner, 99)
    with pytest.raises(AccessDenied, match="revoked"):
        await service.resolve_context(identity(99))
