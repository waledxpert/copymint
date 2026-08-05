"""Stable domain enums derived from the technical specification."""

from enum import StrEnum


class IdentityMode(StrEnum):
    INITIATOR = "initiator"
    RECIPIENT = "recipient"
    EITHER = "either"


class TokenStandard(StrEnum):
    ERC721 = "erc721"
    ERC1155 = "erc1155"
    ERC2309 = "erc2309"
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class MintRoute(StrEnum):
    DIRECT = "direct"
    SEADROP = "seadrop"
    LAUNCHPAD = "launchpad"
    MARKETPLACE = "marketplace"
    RELAYER = "relayer"
    UNKNOWN = "unknown"


class MintClassification(StrEnum):
    PUBLIC_PAID_MINT = "public_paid_mint"
    PUBLIC_FREE_MINT = "public_free_mint"
    ALLOWLIST_MINT = "allowlist_mint"
    TOKEN_GATED_MINT = "token_gated_mint"  # noqa: S105 - public domain enum value
    SERVER_SIGNED_MINT = "server_signed_mint"
    ADMIN_MINT = "admin_mint"
    AIRDROP = "airdrop"
    BRIDGE_MINT = "bridge_mint"
    MIGRATION_MINT = "migration_mint"
    LAZY_MARKETPLACE_MINT = "lazy_marketplace_mint"
    UNKNOWN_MINT = "unknown_mint"


class FinalityStatus(StrEnum):
    PROVISIONAL = "provisional"
    SAFE = "safe"
    FINALIZED = "finalized"
    REORGED = "reorged"


class OpportunityDecision(StrEnum):
    ALERT_ONLY = "alert_only"
    PAPER_READY = "paper_ready"
    MANUAL_READY = "manual_ready"
    AUTO_READY = "auto_ready"
    NOT_COPYABLE = "not_copyable"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class ExecutionMode(StrEnum):
    ALERT = "alert"
    PAPER = "paper"
    MANUAL = "manual"
    AUTO = "auto"


class AttemptStatus(StrEnum):
    CREATED = "created"
    QUOTED = "quoted"
    SIMULATED = "simulated"
    APPROVED = "approved"
    SIGNED = "signed"
    BROADCAST = "broadcast"
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    REPLACED = "replaced"
    DROPPED = "dropped"
    REORGED = "reorged"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class AccessRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PlatformRole(StrEnum):
    PLATFORM_OWNER = "platform_owner"
    WORKSPACE_OWNER = "workspace_owner"
    SERVICE_WORKER = "service_worker"
    SIGNER = "signer"


class WorkspaceStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class MembershipStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class WorkspaceRole(StrEnum):
    OWNER = "workspace_owner"


class ChallengeAction(StrEnum):
    APPROVE_ACCESS = "approve_access"
    REJECT_ACCESS = "reject_access"
    REVOKE_ACCESS = "revoke_access"
    CREATE_WALLET = "create_wallet"


class WalletStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class TelegramUpdateStatus(StrEnum):
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"


class ActorType(StrEnum):
    TELEGRAM_USER = "telegram_user"
    SERVICE = "service"
    SIGNER = "signer"
    SYSTEM = "system"


class SimulationEvidenceLevel(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
