"""Server-derived request identity and authorization context."""

from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import PlatformRole, WorkspaceRole
from app.domain.ids import uuid7


class AccessError(Exception):
    """Base class for safe operator-facing access failures."""

    code = "access_error"


class PrivateChatRequired(AccessError):
    code = "private_chat_required"


class AccessPending(AccessError):
    code = "access_pending"


class AccessDenied(AccessError):
    code = "access_denied"


class PlatformOwnerRequired(AccessError):
    code = "platform_owner_required"


class WorkspaceRequired(AccessError):
    code = "workspace_required"


class RateLimited(AccessError):
    code = "rate_limited"


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    telegram_user_id: int
    chat_id: int
    chat_type: str
    username: str | None = None
    display_name: str | None = None

    @property
    def is_private_chat(self) -> bool:
        return self.chat_type == "private" and self.chat_id == self.telegram_user_id

    def require_private_chat(self) -> None:
        if not self.is_private_chat:
            raise PrivateChatRequired("This action is available only in a private bot chat.")


@dataclass(frozen=True, slots=True)
class RequestContext:
    telegram_user_id: int
    chat_id: int
    chat_type: str
    correlation_id: UUID
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    workspace_role: WorkspaceRole | None = None
    platform_role: PlatformRole | None = None

    @classmethod
    def platform_owner(cls, identity: TelegramIdentity) -> "RequestContext":
        return cls(
            telegram_user_id=identity.telegram_user_id,
            chat_id=identity.chat_id,
            chat_type=identity.chat_type,
            correlation_id=uuid7(),
            platform_role=PlatformRole.PLATFORM_OWNER,
        )

    @property
    def is_platform_owner(self) -> bool:
        return self.platform_role is PlatformRole.PLATFORM_OWNER

    def require_private_chat(self) -> None:
        TelegramIdentity(
            telegram_user_id=self.telegram_user_id,
            chat_id=self.chat_id,
            chat_type=self.chat_type,
        ).require_private_chat()

    def require_platform_owner(self) -> None:
        self.require_private_chat()
        if not self.is_platform_owner:
            raise PlatformOwnerRequired("Platform-owner authorization is required.")

    def require_workspace(self) -> UUID:
        self.require_private_chat()
        if self.workspace_id is None:
            raise WorkspaceRequired("An active workspace is required.")
        return self.workspace_id
