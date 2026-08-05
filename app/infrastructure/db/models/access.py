"""Phase 1 access-control, workspace, challenge, update, and audit models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.domain.enums import (
    AccessRequestStatus,
    ActorType,
    ChallengeAction,
    ExecutionMode,
    MembershipStatus,
    Severity,
    TelegramUpdateStatus,
    UserStatus,
    WorkspaceRole,
    WorkspaceStatus,
)
from app.domain.ids import uuid7
from app.infrastructure.db.base import Base, TimestampMixin


def enum_type(enum_class: type, name: str, length: int = 32) -> Enum:
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
        length=length,
    )


class PlatformUser(TimestampMixin, Base):
    __tablename__ = "platform_users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        enum_type(UserStatus, "platform_user_status"), nullable=False, default=UserStatus.ACTIVE
    )
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_users.id", ondelete="RESTRICT")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_users.id", ondelete="RESTRICT")
    )


class AccessRequest(TimestampMixin, Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        Index(
            "uq_access_requests_one_pending_per_telegram_user",
            "telegram_user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_access_requests_status_requested", "status", "requested_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[AccessRequestStatus] = mapped_column(
        enum_type(AccessRequestStatus, "access_request_status"),
        nullable=False,
        default=AccessRequestStatus.PENDING,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_users.id", ondelete="RESTRICT")
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    personal_owner_user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("platform_users.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status: Mapped[WorkspaceStatus] = mapped_column(
        enum_type(WorkspaceStatus, "workspace_status"),
        nullable=False,
        default=WorkspaceStatus.ACTIVE,
    )


class WorkspaceMembership(TimestampMixin, Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[WorkspaceRole] = mapped_column(
        enum_type(WorkspaceRole, "workspace_role"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus, "membership_status"),
        nullable=False,
        default=MembershipStatus.ACTIVE,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationDestination(TimestampMixin, Base):
    __tablename__ = "notification_destinations"
    __table_args__ = (UniqueConstraint("workspace_id", "telegram_chat_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_type: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class WorkspaceStrategy(TimestampMixin, Base):
    __tablename__ = "workspace_strategies"
    __table_args__ = (
        UniqueConstraint("workspace_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    mode: Mapped[ExecutionMode] = mapped_column(
        enum_type(ExecutionMode, "execution_mode"),
        nullable=False,
        default=ExecutionMode.ALERT,
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CallbackChallenge(Base):
    __tablename__ = "callback_challenges"
    __table_args__ = (
        Index("ix_callback_challenges_expiry", "expires_at"),
        CheckConstraint("octet_length(token_hash) = 32", name="sha256_token_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False, unique=True)
    action: Mapped[ChallengeAction] = mapped_column(
        enum_type(ChallengeAction, "challenge_action"), nullable=False
    )
    expected_actor_telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authoritative_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"
    __table_args__ = (UniqueConstraint("bot_id", "update_id"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    bot_id: Mapped[str] = mapped_column(String(32), nullable=False)
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[TelegramUpdateStatus] = mapped_column(
        enum_type(TelegramUpdateStatus, "telegram_update_status"),
        nullable=False,
        default=TelegramUpdateStatus.RECEIVED,
    )
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, default=uuid7)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(64))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_workspace_timestamp", "workspace_id", "occurred_at"),
        Index("ix_audit_logs_correlation", "correlation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid7)
    workspace_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT")
    )
    actor_type: Mapped[ActorType] = mapped_column(
        enum_type(ActorType, "audit_actor_type"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correlation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        enum_type(Severity, "audit_severity"), nullable=False, default=Severity.INFO
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
