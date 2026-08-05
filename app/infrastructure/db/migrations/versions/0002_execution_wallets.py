"""Workspace-private execution wallet references.

Revision ID: 0002_execution_wallets
Revises: 0001_phase1_access
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_execution_wallets"
down_revision: str | None = "0001_phase1_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_callback_challenges_challenge_action"),
        "callback_challenges",
        type_="check",
    )
    op.create_check_constraint(
        "challenge_action",
        "callback_challenges",
        "action IN ('approve_access', 'reject_access', 'revoke_access', 'create_wallet')",
    )
    op.create_table(
        "execution_wallets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("signer_key_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "suspended",
                name="execution_wallet_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("balance_wei", sa.Numeric(precision=78, scale=0), nullable=False),
        sa.Column("balance_block_number", sa.BigInteger()),
        sa.Column("balance_refreshed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("chain_id = 1", name="ethereum_mainnet_only"),
        sa.CheckConstraint(
            "octet_length(idempotency_key_hash) = 32", name="idempotency_sha256"
        ),
        sa.CheckConstraint("balance_wei >= 0", name="nonnegative_balance"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signer_key_id"),
        sa.UniqueConstraint("chain_id", "address"),
        sa.UniqueConstraint("workspace_id", "idempotency_key_hash"),
    )
    op.create_index(
        "ix_execution_wallets_workspace_created",
        "execution_wallets",
        ["workspace_id", "created_at"],
    )
    op.execute('ALTER TABLE "execution_wallets" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "execution_wallets" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "execution_wallets_workspace_isolation" ON "execution_wallets" '
        "USING (workspace_id = "
        "NULLIF(current_setting('app.workspace_id', true), '')::uuid) "
        "WITH CHECK (workspace_id = "
        "NULLIF(current_setting('app.workspace_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS "execution_wallets_workspace_isolation" ON "execution_wallets"'
    )
    op.drop_index("ix_execution_wallets_workspace_created", table_name="execution_wallets")
    op.drop_table("execution_wallets")
    op.drop_constraint(
        op.f("ck_callback_challenges_challenge_action"),
        "callback_challenges",
        type_="check",
    )
    op.create_check_constraint(
        "challenge_action",
        "callback_challenges",
        "action IN ('approve_access', 'reject_access', 'revoke_access')",
    )
