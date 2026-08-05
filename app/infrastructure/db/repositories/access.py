"""Atomic PostgreSQL persistence for invite-only access control."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.access.context import TelegramIdentity
from app.application.access.ports import (
    AccessDecisionResult,
    AccessRequestRecord,
    PendingRequestResult,
    Principal,
)
from app.domain.enums import (
    AccessRequestStatus,
    ActorType,
    ExecutionMode,
    MembershipStatus,
    Severity,
    UserStatus,
    WorkspaceRole,
    WorkspaceStatus,
)
from app.domain.ids import uuid7
from app.infrastructure.db.models.access import (
    AccessRequest,
    AuditLog,
    NotificationDestination,
    PlatformUser,
    Workspace,
    WorkspaceMembership,
    WorkspaceStrategy,
)


class AccessPersistenceError(RuntimeError):
    pass


class AccessRequestNotFound(AccessPersistenceError):
    pass


class AccessRequestNotPending(AccessPersistenceError):
    pass


class UserNotFound(AccessPersistenceError):
    pass


async def set_user_context(session: AsyncSession, user_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.user_id', :user_id, true)"), {"user_id": str(user_id)}
    )


async def set_workspace_context(session: AsyncSession, workspace_id: UUID) -> None:
    await session.execute(
        text("SELECT set_config('app.workspace_id', :workspace_id, true)"),
        {"workspace_id": str(workspace_id)},
    )


def request_record(model: AccessRequest) -> AccessRequestRecord:
    return AccessRequestRecord(
        id=model.id,
        telegram_user_id=model.telegram_user_id,
        status=model.status,
        requested_at=model.requested_at,
        cooldown_until=model.cooldown_until,
    )


class SqlAlchemyAccessRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def find_principal(self, telegram_user_id: int) -> Principal | None:
        async with self._sessions() as session, session.begin():
            user = await session.scalar(
                select(PlatformUser).where(PlatformUser.telegram_user_id == telegram_user_id)
            )
            if user is None:
                return None

            await set_user_context(session, user.id)
            membership = (
                await session.execute(
                    select(WorkspaceMembership.workspace_id, WorkspaceMembership.role)
                    .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
                    .where(
                        WorkspaceMembership.user_id == user.id,
                        WorkspaceMembership.status == MembershipStatus.ACTIVE,
                        Workspace.status == WorkspaceStatus.ACTIVE,
                    )
                    .limit(1)
                )
            ).one_or_none()
            return Principal(
                user_id=user.id,
                telegram_user_id=user.telegram_user_id,
                user_status=user.status,
                workspace_id=membership.workspace_id if membership else None,
                workspace_role=membership.role if membership else None,
            )

    async def find_latest_request(self, telegram_user_id: int) -> AccessRequestRecord | None:
        async with self._sessions() as session:
            model = await session.scalar(
                select(AccessRequest)
                .where(AccessRequest.telegram_user_id == telegram_user_id)
                .order_by(AccessRequest.requested_at.desc())
                .limit(1)
            )
            return request_record(model) if model else None

    async def list_pending_requests(self, *, limit: int = 20) -> list[AccessRequestRecord]:
        async with self._sessions() as session:
            models = (
                await session.scalars(
                    select(AccessRequest)
                    .where(AccessRequest.status == AccessRequestStatus.PENDING)
                    .order_by(AccessRequest.requested_at.asc())
                    .limit(limit)
                )
            ).all()
            return [request_record(model) for model in models]

    async def get_or_create_pending_request(
        self, identity: TelegramIdentity, requested_at: datetime
    ) -> PendingRequestResult:
        request_id = uuid7()
        statement = (
            insert(AccessRequest)
            .values(
                id=request_id,
                telegram_user_id=identity.telegram_user_id,
                username=identity.username,
                display_name=identity.display_name,
                status=AccessRequestStatus.PENDING,
                requested_at=requested_at,
            )
            .on_conflict_do_nothing(
                index_elements=[AccessRequest.telegram_user_id],
                index_where=AccessRequest.status == AccessRequestStatus.PENDING,
            )
            .returning(AccessRequest)
        )
        async with self._sessions() as session, session.begin():
            created = (await session.execute(statement)).scalar_one_or_none()
            if created:
                return PendingRequestResult(record=request_record(created), created=True)
            existing = await session.scalar(
                select(AccessRequest).where(
                    AccessRequest.telegram_user_id == identity.telegram_user_id,
                    AccessRequest.status == AccessRequestStatus.PENDING,
                )
            )
            if existing is None:
                raise AccessPersistenceError("pending access request conflict was not recoverable")
            return PendingRequestResult(record=request_record(existing), created=False)

    async def _platform_actor(
        self, session: AsyncSession, telegram_user_id: int, now: datetime
    ) -> PlatformUser:
        actor = await session.scalar(
            select(PlatformUser)
            .where(PlatformUser.telegram_user_id == telegram_user_id)
            .with_for_update()
        )
        if actor:
            if actor.status is not UserStatus.ACTIVE:
                actor.status = UserStatus.ACTIVE
                actor.revoked_at = None
                actor.revoked_by_user_id = None
            return actor
        actor = PlatformUser(
            telegram_user_id=telegram_user_id,
            status=UserStatus.ACTIVE,
            approved_at=now,
        )
        session.add(actor)
        await session.flush()
        return actor

    async def approve_request(
        self,
        *,
        request_id: UUID,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        decided_at: datetime,
    ) -> AccessDecisionResult:
        async with self._sessions() as session, session.begin():
            actor = await self._platform_actor(session, actor_telegram_user_id, decided_at)
            access_request = await session.scalar(
                select(AccessRequest).where(AccessRequest.id == request_id).with_for_update()
            )
            if access_request is None:
                raise AccessRequestNotFound("access request was not found")
            if access_request.status is not AccessRequestStatus.PENDING:
                raise AccessRequestNotPending("access request has already been decided")

            user = await session.scalar(
                select(PlatformUser)
                .where(PlatformUser.telegram_user_id == access_request.telegram_user_id)
                .with_for_update()
            )
            if user is None:
                user = PlatformUser(
                    telegram_user_id=access_request.telegram_user_id,
                    username=access_request.username,
                    display_name=access_request.display_name,
                    status=UserStatus.ACTIVE,
                    approved_at=decided_at,
                    approved_by_user_id=actor.id,
                )
                session.add(user)
                await session.flush()
            else:
                user.username = access_request.username
                user.display_name = access_request.display_name
                user.status = UserStatus.ACTIVE
                user.approved_at = decided_at
                user.approved_by_user_id = actor.id
                user.revoked_at = None
                user.revoked_by_user_id = None

            await set_user_context(session, user.id)
            workspace = await session.scalar(
                select(Workspace)
                .where(Workspace.personal_owner_user_id == user.id)
                .with_for_update()
            )
            if workspace is None:
                label = user.display_name or user.username or str(user.telegram_user_id)
                workspace = Workspace(
                    name=f"{label}'s workspace",
                    personal_owner_user_id=user.id,
                    status=WorkspaceStatus.ACTIVE,
                )
                session.add(workspace)
                await session.flush()
            else:
                workspace.status = WorkspaceStatus.ACTIVE

            await set_workspace_context(session, workspace.id)
            membership = await session.scalar(
                select(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace.id,
                    WorkspaceMembership.user_id == user.id,
                )
            )
            if membership is None:
                session.add(
                    WorkspaceMembership(
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role=WorkspaceRole.OWNER,
                        status=MembershipStatus.ACTIVE,
                    )
                )
            else:
                membership.status = MembershipStatus.ACTIVE
                membership.revoked_at = None

            destination = await session.scalar(
                select(NotificationDestination).where(
                    NotificationDestination.workspace_id == workspace.id,
                    NotificationDestination.telegram_chat_id == access_request.telegram_user_id,
                )
            )
            if destination is None:
                session.add(
                    NotificationDestination(
                        workspace_id=workspace.id,
                        telegram_chat_id=access_request.telegram_user_id,
                        chat_type="private",
                        enabled=True,
                    )
                )
            else:
                destination.enabled = True

            strategy = await session.scalar(
                select(WorkspaceStrategy).where(
                    WorkspaceStrategy.workspace_id == workspace.id,
                    WorkspaceStrategy.version == 1,
                )
            )
            if strategy is None:
                session.add(
                    WorkspaceStrategy(
                        workspace_id=workspace.id,
                        version=1,
                        mode=ExecutionMode.ALERT,
                        configuration={"minimum_support": 2, "identity_mode": "initiator"},
                        active=True,
                    )
                )

            access_request.status = AccessRequestStatus.APPROVED
            access_request.decided_at = decided_at
            access_request.decided_by_user_id = actor.id
            session.add(
                AuditLog(
                    workspace_id=workspace.id,
                    actor_type=ActorType.TELEGRAM_USER,
                    actor_id=str(actor_telegram_user_id),
                    action="access_request_approved",
                    resource_type="access_request",
                    resource_id=str(request_id),
                    before={"status": AccessRequestStatus.PENDING.value},
                    after={
                        "status": AccessRequestStatus.APPROVED.value,
                        "user_id": str(user.id),
                        "workspace_id": str(workspace.id),
                    },
                    correlation_id=correlation_id,
                    severity=Severity.INFO,
                )
            )
            return AccessDecisionResult(
                request_id=request_id,
                telegram_user_id=user.telegram_user_id,
                status=AccessRequestStatus.APPROVED,
                user_id=user.id,
                workspace_id=workspace.id,
            )

    async def reject_request(
        self,
        *,
        request_id: UUID,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        reason: str | None,
        decided_at: datetime,
        cooldown_until: datetime | None,
    ) -> AccessDecisionResult:
        async with self._sessions() as session, session.begin():
            actor = await self._platform_actor(session, actor_telegram_user_id, decided_at)
            access_request = await session.scalar(
                select(AccessRequest).where(AccessRequest.id == request_id).with_for_update()
            )
            if access_request is None:
                raise AccessRequestNotFound("access request was not found")
            if access_request.status is not AccessRequestStatus.PENDING:
                raise AccessRequestNotPending("access request has already been decided")

            access_request.status = AccessRequestStatus.REJECTED
            access_request.decided_at = decided_at
            access_request.decided_by_user_id = actor.id
            access_request.decision_reason = reason
            access_request.cooldown_until = cooldown_until
            session.add(
                AuditLog(
                    workspace_id=None,
                    actor_type=ActorType.TELEGRAM_USER,
                    actor_id=str(actor_telegram_user_id),
                    action="access_request_rejected",
                    resource_type="access_request",
                    resource_id=str(request_id),
                    before={"status": AccessRequestStatus.PENDING.value},
                    after={
                        "status": AccessRequestStatus.REJECTED.value,
                        "reason": reason,
                        "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
                    },
                    correlation_id=correlation_id,
                    severity=Severity.INFO,
                )
            )
            return AccessDecisionResult(
                request_id=request_id,
                telegram_user_id=access_request.telegram_user_id,
                status=AccessRequestStatus.REJECTED,
            )

    async def revoke_user(
        self,
        *,
        target_telegram_user_id: int,
        actor_telegram_user_id: int,
        correlation_id: UUID,
        reason: str | None,
        revoked_at: datetime,
    ) -> None:
        async with self._sessions() as session, session.begin():
            actor = await self._platform_actor(session, actor_telegram_user_id, revoked_at)
            user = await session.scalar(
                select(PlatformUser)
                .where(PlatformUser.telegram_user_id == target_telegram_user_id)
                .with_for_update()
            )
            if user is None:
                raise UserNotFound("approved user was not found")

            await set_user_context(session, user.id)
            workspace = await session.scalar(
                select(Workspace)
                .where(Workspace.personal_owner_user_id == user.id)
                .with_for_update()
            )
            if workspace:
                await set_workspace_context(session, workspace.id)
                workspace.status = WorkspaceStatus.SUSPENDED
                await session.execute(
                    update(WorkspaceMembership)
                    .where(
                        WorkspaceMembership.workspace_id == workspace.id,
                        WorkspaceMembership.user_id == user.id,
                    )
                    .values(status=MembershipStatus.REVOKED, revoked_at=revoked_at)
                )
                await session.execute(
                    update(NotificationDestination)
                    .where(NotificationDestination.workspace_id == workspace.id)
                    .values(enabled=False)
                )

            before_status = user.status
            user.status = UserStatus.REVOKED
            user.revoked_at = revoked_at
            user.revoked_by_user_id = actor.id
            session.add(
                AuditLog(
                    workspace_id=workspace.id if workspace else None,
                    actor_type=ActorType.TELEGRAM_USER,
                    actor_id=str(actor_telegram_user_id),
                    action="platform_user_revoked",
                    resource_type="platform_user",
                    resource_id=str(user.id),
                    before={"status": before_status.value},
                    after={"status": UserStatus.REVOKED.value, "reason": reason},
                    correlation_id=correlation_id,
                    severity=Severity.HIGH,
                )
            )


class SqlAlchemySecurityAudit:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def unauthorized_attempt(
        self,
        *,
        identity: TelegramIdentity,
        action: str,
        code: str,
        correlation_id: UUID,
    ) -> None:
        async with self._sessions() as session, session.begin():
            session.add(
                AuditLog(
                    workspace_id=None,
                    actor_type=ActorType.TELEGRAM_USER,
                    actor_id=str(identity.telegram_user_id),
                    action="unauthorized_telegram_attempt",
                    resource_type="telegram_action",
                    resource_id=action,
                    before=None,
                    after={
                        "code": code,
                        "chat_type": identity.chat_type,
                        "chat_id": identity.chat_id,
                    },
                    correlation_id=correlation_id,
                    severity=Severity.HIGH,
                )
            )
