"""Persistence ports for access-control use cases."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.access.context import TelegramIdentity
from app.domain.enums import AccessRequestStatus, UserStatus, WorkspaceRole


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: UUID
    telegram_user_id: int
    user_status: UserStatus
    workspace_id: UUID | None
    workspace_role: WorkspaceRole | None


@dataclass(frozen=True, slots=True)
class AccessRequestRecord:
    id: UUID
    telegram_user_id: int
    status: AccessRequestStatus
    requested_at: datetime
    cooldown_until: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessRequestOutcome:
    state: str
    request_id: UUID | None
    created: bool = False


@dataclass(frozen=True, slots=True)
class PendingRequestResult:
    record: AccessRequestRecord
    created: bool


@dataclass(frozen=True, slots=True)
class AccessDecisionResult:
    request_id: UUID
    telegram_user_id: int
    status: AccessRequestStatus
    user_id: UUID | None = None
    workspace_id: UUID | None = None


class AccessRepository(Protocol):
    async def find_principal(self, telegram_user_id: int) -> Principal | None: ...

    async def find_latest_request(self, telegram_user_id: int) -> AccessRequestRecord | None: ...

    async def list_pending_requests(self, *, limit: int = 20) -> list[AccessRequestRecord]: ...

    async def get_or_create_pending_request(
        self, identity: TelegramIdentity, requested_at: datetime
    ) -> PendingRequestResult: ...

    async def approve_request(
        self,
        *,
        request_id: UUID,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        decided_at: datetime,
    ) -> AccessDecisionResult: ...

    async def reject_request(
        self,
        *,
        request_id: UUID,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        reason: str | None,
        decided_at: datetime,
        cooldown_until: datetime | None,
    ) -> AccessDecisionResult: ...

    async def revoke_user(
        self,
        *,
        target_telegram_user_id: int,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        reason: str | None,
        revoked_at: datetime,
    ) -> None: ...


class SecurityAuditPort(Protocol):
    async def unauthorized_attempt(
        self,
        *,
        identity: TelegramIdentity,
        action: str,
        code: str,
        correlation_id: UUID,
    ) -> None: ...
