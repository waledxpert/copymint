"""Phase 1 access control and tenant isolation.

Revision ID: 0001_phase1_access
Revises: None
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_phase1_access"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def string_enum(name: str, *values: str, length: int = 32) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
    )


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def enable_workspace_rls(
    table: str,
    *,
    workspace_column: str = "workspace_id",
    user_column: str | None = None,
) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    workspace_clause = (
        f"{workspace_column} = "
        "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
    )
    if user_column:
        user_clause = f"{user_column} = NULLIF(current_setting('app.user_id', true), '')::uuid"
        workspace_clause = f"({workspace_clause} OR {user_clause})"
    op.execute(
        f'CREATE POLICY "{table}_workspace_isolation" ON "{table}" '
        f"USING ({workspace_clause}) WITH CHECK ({workspace_clause})"
    )


def upgrade() -> None:
    op.create_table(
        "platform_users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64)),
        sa.Column("display_name", sa.String(length=255)),
        sa.Column(
            "status",
            string_enum("platform_user_status", "active", "revoked"),
            nullable=False,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_by_user_id", sa.Uuid()),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_user_id", sa.Uuid()),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"], ["platform_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by_user_id"], ["platform_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_user_id"),
    )

    op.create_table(
        "access_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=64)),
        sa.Column("display_name", sa.String(length=255)),
        sa.Column(
            "status",
            string_enum("access_request_status", "pending", "approved", "rejected", "cancelled"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_by_user_id", sa.Uuid()),
        sa.Column("decision_reason", sa.Text()),
        sa.Column("cooldown_until", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"], ["platform_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_requests_status_requested",
        "access_requests",
        ["status", "requested_at"],
    )
    op.create_index(
        "uq_access_requests_one_pending_per_telegram_user",
        "access_requests",
        ["telegram_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("personal_owner_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            string_enum("workspace_status", "active", "suspended", "closed"),
            nullable=False,
        ),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["personal_owner_user_id"], ["platform_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("personal_owner_user_id"),
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role", string_enum("workspace_role", "workspace_owner"), nullable=False
        ),
        sa.Column(
            "status",
            string_enum("membership_status", "active", "revoked"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["platform_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id"),
    )

    op.create_table(
        "notification_destinations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("chat_type", sa.String(length=16), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "telegram_chat_id"),
    )

    op.create_table(
        "workspace_strategies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "mode", string_enum("execution_mode", "alert", "paper", "manual", "auto"), nullable=False
        ),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_workspace_strategies_positive_version"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "version"),
    )

    op.create_table(
        "callback_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "action",
            string_enum(
                "challenge_action", "approve_access", "reject_access", "revoke_access"
            ),
            nullable=False,
        ),
        sa.Column("expected_actor_telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("expected_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column(
            "authoritative_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32", name="ck_callback_challenges_sha256_token_hash"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_callback_challenges_expiry", "callback_challenges", ["expires_at"]
    )

    op.create_table(
        "telegram_updates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.String(length=32), nullable=False),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            string_enum("telegram_update_status", "received", "processed", "failed"),
            nullable=False,
        ),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String(length=64)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bot_id", "update_id"),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid()),
        sa.Column(
            "actor_type",
            string_enum("audit_actor_type", "telegram_user", "service", "signer", "system"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "severity",
            string_enum("audit_severity", "info", "low", "medium", "high", "critical"),
            nullable=False,
        ),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_correlation", "audit_logs", ["correlation_id"])
    op.create_index(
        "ix_audit_logs_workspace_timestamp", "audit_logs", ["workspace_id", "occurred_at"]
    )

    enable_workspace_rls(
        "workspaces", workspace_column="id", user_column="personal_owner_user_id"
    )
    enable_workspace_rls("workspace_memberships", user_column="user_id")
    enable_workspace_rls("notification_destinations")
    enable_workspace_rls("workspace_strategies")
    op.execute('ALTER TABLE "audit_logs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "audit_logs" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "audit_logs_workspace_select" ON "audit_logs" FOR SELECT '
        "USING (workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid)"
    )
    op.execute(
        'CREATE POLICY "audit_logs_insert" ON "audit_logs" FOR INSERT WITH CHECK '
        "(workspace_id IS NULL OR "
        "workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS "audit_logs_insert" ON "audit_logs"')
    op.execute('DROP POLICY IF EXISTS "audit_logs_workspace_select" ON "audit_logs"')
    for table in (
        "workspace_strategies",
        "notification_destinations",
        "workspace_memberships",
        "workspaces",
    ):
        op.execute(f'DROP POLICY IF EXISTS "{table}_workspace_isolation" ON "{table}"')

    op.drop_index("ix_audit_logs_workspace_timestamp", table_name="audit_logs")
    op.drop_index("ix_audit_logs_correlation", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("telegram_updates")
    op.drop_index("ix_callback_challenges_expiry", table_name="callback_challenges")
    op.drop_table("callback_challenges")
    op.drop_table("workspace_strategies")
    op.drop_table("notification_destinations")
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
    op.drop_index(
        "uq_access_requests_one_pending_per_telegram_user", table_name="access_requests"
    )
    op.drop_index("ix_access_requests_status_requested", table_name="access_requests")
    op.drop_table("access_requests")
    op.drop_table("platform_users")
