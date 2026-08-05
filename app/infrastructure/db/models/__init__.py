"""Import all ORM models so Alembic sees complete metadata."""

from app.infrastructure.db.models.access import (
    AccessRequest,
    AuditLog,
    CallbackChallenge,
    ExecutionWallet,
    NotificationDestination,
    PlatformUser,
    TelegramUpdate,
    Workspace,
    WorkspaceMembership,
    WorkspaceStrategy,
)

__all__ = [
    "AccessRequest",
    "AuditLog",
    "CallbackChallenge",
    "ExecutionWallet",
    "NotificationDestination",
    "PlatformUser",
    "TelegramUpdate",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceStrategy",
]
