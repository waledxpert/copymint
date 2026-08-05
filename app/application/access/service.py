"""Invite-only access and authorization application service."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.application.access.context import (
    AccessDenied,
    AccessPending,
    RequestContext,
    TelegramIdentity,
)
from app.application.access.ports import (
    AccessDecisionResult,
    AccessRepository,
    AccessRequestOutcome,
    AccessRequestRecord,
)
from app.domain.enums import AccessRequestStatus, PlatformRole, UserStatus
from app.domain.ids import uuid7


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class AccessService:
    """Enforce access rules before delegating atomic persistence operations."""

    def __init__(
        self,
        repository: AccessRepository,
        *,
        platform_owner_ids: frozenset[int],
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not platform_owner_ids:
            raise ValueError("at least one platform owner ID is required")
        self._repository = repository
        self._platform_owner_ids = platform_owner_ids
        self._clock = clock

    async def request_access(self, identity: TelegramIdentity) -> AccessRequestOutcome:
        identity.require_private_chat()
        principal = await self._repository.find_principal(identity.telegram_user_id)
        if principal and principal.user_status is UserStatus.ACTIVE:
            return AccessRequestOutcome(state="active", request_id=None)

        latest = await self._repository.find_latest_request(identity.telegram_user_id)
        now = self._clock()
        if latest and latest.status is AccessRequestStatus.PENDING:
            return AccessRequestOutcome(state="pending", request_id=latest.id)
        if latest and latest.cooldown_until and latest.cooldown_until > now:
            return AccessRequestOutcome(state="cooldown", request_id=latest.id)

        pending = await self._repository.get_or_create_pending_request(identity, now)
        return AccessRequestOutcome(
            state="pending", request_id=pending.record.id, created=pending.created
        )

    async def access_status(self, identity: TelegramIdentity) -> AccessRequestOutcome:
        identity.require_private_chat()
        principal = await self._repository.find_principal(identity.telegram_user_id)
        if principal and principal.user_status is UserStatus.ACTIVE:
            return AccessRequestOutcome(state="active", request_id=None)
        latest = await self._repository.find_latest_request(identity.telegram_user_id)
        if latest is None:
            return AccessRequestOutcome(state="not_requested", request_id=None)
        return AccessRequestOutcome(state=latest.status.value, request_id=latest.id)

    async def resolve_context(self, identity: TelegramIdentity) -> RequestContext:
        identity.require_private_chat()
        correlation_id = uuid7()
        is_owner = identity.telegram_user_id in self._platform_owner_ids
        principal = await self._repository.find_principal(identity.telegram_user_id)

        if principal is None:
            if is_owner:
                return RequestContext.platform_owner(identity)
            latest = await self._repository.find_latest_request(identity.telegram_user_id)
            if latest and latest.status is AccessRequestStatus.PENDING:
                raise AccessPending("Access request is awaiting owner approval.")
            raise AccessDenied("This Telegram account is not approved for CopyMint.")

        if principal.user_status is not UserStatus.ACTIVE:
            raise AccessDenied("CopyMint access has been revoked.")
        if principal.workspace_id is None or principal.workspace_role is None:
            if not is_owner:
                raise AccessDenied("The approved account has no active workspace.")

        return RequestContext(
            telegram_user_id=identity.telegram_user_id,
            chat_id=identity.chat_id,
            chat_type=identity.chat_type,
            correlation_id=correlation_id,
            user_id=principal.user_id,
            workspace_id=principal.workspace_id,
            workspace_role=principal.workspace_role,
            platform_role=PlatformRole.PLATFORM_OWNER if is_owner else None,
        )

    async def approve(self, actor: RequestContext, request_id: UUID) -> AccessDecisionResult:
        actor.require_platform_owner()
        return await self._repository.approve_request(
            request_id=request_id,
            actor_telegram_user_id=actor.telegram_user_id,
            correlation_id=actor.correlation_id,
            decided_at=self._clock(),
        )

    async def pending_requests(
        self, actor: RequestContext, *, limit: int = 20
    ) -> list[AccessRequestRecord]:
        actor.require_platform_owner()
        if limit < 1 or limit > 100:
            raise ValueError("pending request limit must be between 1 and 100")
        return await self._repository.list_pending_requests(limit=limit)

    async def reject(
        self,
        actor: RequestContext,
        request_id: UUID,
        *,
        reason: str | None = None,
        cooldown: timedelta | None = None,
    ) -> AccessDecisionResult:
        actor.require_platform_owner()
        now = self._clock()
        return await self._repository.reject_request(
            request_id=request_id,
            actor_telegram_user_id=actor.telegram_user_id,
            correlation_id=actor.correlation_id,
            reason=reason,
            decided_at=now,
            cooldown_until=now + cooldown if cooldown else None,
        )

    async def revoke(
        self,
        actor: RequestContext,
        target_telegram_user_id: int,
        *,
        reason: str | None = None,
    ) -> None:
        actor.require_platform_owner()
        if target_telegram_user_id in self._platform_owner_ids:
            raise AccessDenied("A configured platform owner cannot be revoked through the bot.")
        await self._repository.revoke_user(
            target_telegram_user_id=target_telegram_user_id,
            actor_telegram_user_id=actor.telegram_user_id,
            correlation_id=actor.correlation_id,
            reason=reason,
            revoked_at=self._clock(),
        )
