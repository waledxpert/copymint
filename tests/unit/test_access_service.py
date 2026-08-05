from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.application.access.context import (
    AccessDenied,
    AccessPending,
    PlatformOwnerRequired,
    PrivateChatRequired,
    RequestContext,
    TelegramIdentity,
)
from app.application.access.ports import (
    AccessDecisionResult,
    AccessRequestOutcome,
    AccessRequestRecord,
    PendingRequestResult,
    Principal,
)
from app.application.access.service import AccessService
from app.domain.enums import (
    AccessRequestStatus,
    MembershipStatus,
    PlatformRole,
    UserStatus,
    WorkspaceRole,
)
from app.domain.ids import uuid7

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)


class FakeAccessRepository:
    def __init__(self) -> None:
        self.principal: Principal | None = None
        self.latest: AccessRequestRecord | None = None
        self.pending: list[AccessRequestRecord] = []
        self.created = 0
        self.approvals: list[UUID] = []
        self.rejections: list[UUID] = []
        self.revocations: list[int] = []

    async def find_principal(self, telegram_user_id: int) -> Principal | None:
        if self.principal and self.principal.telegram_user_id == telegram_user_id:
            return self.principal
        return None

    async def find_latest_request(self, telegram_user_id: int) -> AccessRequestRecord | None:
        if self.latest and self.latest.telegram_user_id == telegram_user_id:
            return self.latest
        return None

    async def list_pending_requests(self, *, limit: int = 20) -> list[AccessRequestRecord]:
        return self.pending[:limit]

    async def get_or_create_pending_request(
        self, identity: TelegramIdentity, requested_at: datetime
    ) -> PendingRequestResult:
        self.created += 1
        self.latest = AccessRequestRecord(
            id=uuid7(),
            telegram_user_id=identity.telegram_user_id,
            status=AccessRequestStatus.PENDING,
            requested_at=requested_at,
        )
        return PendingRequestResult(record=self.latest, created=True)

    async def approve_request(self, **values: object) -> AccessDecisionResult:
        request_id = values["request_id"]
        assert isinstance(request_id, UUID)
        self.approvals.append(request_id)
        return AccessDecisionResult(
            request_id=request_id,
            telegram_user_id=99,
            status=AccessRequestStatus.APPROVED,
            user_id=uuid7(),
            workspace_id=uuid7(),
        )

    async def reject_request(self, **values: object) -> AccessDecisionResult:
        request_id = values["request_id"]
        assert isinstance(request_id, UUID)
        self.rejections.append(request_id)
        return AccessDecisionResult(
            request_id=request_id,
            telegram_user_id=99,
            status=AccessRequestStatus.REJECTED,
        )

    async def revoke_user(self, **values: object) -> None:
        target = values["target_telegram_user_id"]
        assert isinstance(target, int)
        self.revocations.append(target)


def identity(user_id: int = 99, *, chat_type: str = "private") -> TelegramIdentity:
    return TelegramIdentity(
        telegram_user_id=user_id,
        chat_id=user_id if chat_type == "private" else -100123,
        chat_type=chat_type,
        username="tester",
        display_name="Test User",
    )


def owner_context(user_id: int = 1) -> RequestContext:
    return RequestContext(
        telegram_user_id=user_id,
        chat_id=user_id,
        chat_type="private",
        correlation_id=uuid7(),
        platform_role=PlatformRole.PLATFORM_OWNER,
    )


@pytest.mark.asyncio
async def test_unknown_user_creates_one_pending_request() -> None:
    repository = FakeAccessRepository()
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)

    first = await service.request_access(identity())
    second = await service.request_access(identity())

    assert first.state == "pending"
    assert first.created
    assert second.request_id == first.request_id
    assert not second.created
    assert repository.created == 1


@pytest.mark.asyncio
async def test_access_request_requires_a_real_private_chat() -> None:
    service = AccessService(
        FakeAccessRepository(), platform_owner_ids=frozenset({1}), clock=lambda: NOW
    )
    with pytest.raises(PrivateChatRequired):
        await service.request_access(identity(chat_type="group"))

    spoofed = TelegramIdentity(telegram_user_id=99, chat_id=100, chat_type="private")
    with pytest.raises(PrivateChatRequired):
        await service.request_access(spoofed)


@pytest.mark.asyncio
async def test_rejected_user_obeys_cooldown() -> None:
    repository = FakeAccessRepository()
    repository.latest = AccessRequestRecord(
        id=uuid7(),
        telegram_user_id=99,
        status=AccessRequestStatus.REJECTED,
        requested_at=NOW - timedelta(days=1),
        cooldown_until=NOW + timedelta(hours=1),
    )
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    outcome = await service.request_access(identity())
    assert outcome == AccessRequestOutcome(state="cooldown", request_id=repository.latest.id)
    assert repository.created == 0


@pytest.mark.asyncio
async def test_active_user_resolves_private_workspace_context() -> None:
    repository = FakeAccessRepository()
    repository.principal = Principal(
        user_id=uuid7(),
        telegram_user_id=99,
        user_status=UserStatus.ACTIVE,
        workspace_id=uuid7(),
        workspace_role=WorkspaceRole.OWNER,
    )
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    context = await service.resolve_context(identity())
    assert context.user_id == repository.principal.user_id
    assert context.require_workspace() == repository.principal.workspace_id
    assert not context.is_platform_owner


@pytest.mark.asyncio
async def test_pending_and_unknown_users_do_not_receive_context() -> None:
    repository = FakeAccessRepository()
    repository.latest = AccessRequestRecord(
        id=uuid7(),
        telegram_user_id=99,
        status=AccessRequestStatus.PENDING,
        requested_at=NOW,
    )
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    with pytest.raises(AccessPending):
        await service.resolve_context(identity())
    with pytest.raises(AccessDenied):
        await service.resolve_context(identity(100))


@pytest.mark.asyncio
async def test_configured_owner_can_bootstrap_without_a_database_principal() -> None:
    service = AccessService(
        FakeAccessRepository(), platform_owner_ids=frozenset({1}), clock=lambda: NOW
    )
    context = await service.resolve_context(identity(1))
    assert context.is_platform_owner
    assert context.user_id is None


@pytest.mark.asyncio
async def test_only_platform_owner_can_decide_requests_and_revoke() -> None:
    repository = FakeAccessRepository()
    service = AccessService(repository, platform_owner_ids=frozenset({1}), clock=lambda: NOW)
    request_id = uuid7()

    await service.approve(owner_context(), request_id)
    await service.reject(owner_context(), request_id, reason="not invited")
    await service.revoke(owner_context(), 99, reason="owner decision")
    assert repository.approvals == [request_id]
    assert repository.rejections == [request_id]
    assert repository.revocations == [99]

    normal = RequestContext(
        telegram_user_id=99,
        chat_id=99,
        chat_type="private",
        correlation_id=uuid7(),
        user_id=uuid7(),
        workspace_id=uuid7(),
        workspace_role=WorkspaceRole.OWNER,
    )
    with pytest.raises(PlatformOwnerRequired):
        await service.approve(normal, request_id)
    with pytest.raises(AccessDenied):
        await service.revoke(owner_context(), 1)


def test_membership_status_wire_value_is_stable() -> None:
    assert MembershipStatus.ACTIVE.value == "active"
