"""Signer-owned encrypted key envelopes.

Revision ID: 0001_signer_keys
Revises: None
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_signer_keys"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signer_request_replays",
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_signer_request_replays_expiry",
        "signer_request_replays",
        ["expires_at"],
    )
    op.create_table(
        "signer_key_envelopes",
        sa.Column("signer_key_id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(length=32), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("chain_id", sa.BigInteger(), nullable=False),
        sa.Column("address", sa.String(length=42), nullable=False),
        sa.Column("idempotency_key_hash", sa.LargeBinary(length=32), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("encrypted_data_key", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=False),
        sa.Column("tag", sa.LargeBinary(length=16), nullable=False),
        sa.Column("kms_key_arn", sa.String(length=512), nullable=False),
        sa.Column("envelope_version", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("octet_length(nonce) = 12", name="aes_gcm_nonce"),
        sa.CheckConstraint("octet_length(tag) = 16", name="aes_gcm_tag"),
        sa.CheckConstraint("chain_id = 1", name="ethereum_mainnet_only"),
        sa.CheckConstraint(
            "octet_length(idempotency_key_hash) = 32",
            name="idempotency_sha256",
        ),
        sa.PrimaryKeyConstraint("signer_key_id"),
        sa.UniqueConstraint(
            "environment",
            "workspace_id",
            "chain_id",
            "idempotency_key_hash",
            name="uq_signer_key_envelopes_environment",
        ),
    )
    op.create_index(
        "ix_signer_key_workspace",
        "signer_key_envelopes",
        ["environment", "workspace_id", "chain_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signer_key_workspace", table_name="signer_key_envelopes")
    op.drop_table("signer_key_envelopes")
    op.drop_index("ix_signer_request_replays_expiry", table_name="signer_request_replays")
    op.drop_table("signer_request_replays")
