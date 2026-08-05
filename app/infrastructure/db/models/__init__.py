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
from app.infrastructure.db.models.ethereum import (
    Chain,
    ChainCursor,
    Collection,
    CollectionImplementation,
    MintEvent,
    RawEvidence,
    ScanCheckpoint,
    ScanJob,
)

__all__ = [
    "AccessRequest",
    "AuditLog",
    "CallbackChallenge",
    "Chain",
    "ChainCursor",
    "Collection",
    "CollectionImplementation",
    "ExecutionWallet",
    "MintEvent",
    "NotificationDestination",
    "PlatformUser",
    "RawEvidence",
    "ScanCheckpoint",
    "ScanJob",
    "TelegramUpdate",
    "Workspace",
    "WorkspaceMembership",
    "WorkspaceStrategy",
]
