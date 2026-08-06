"""Workspace-private collection registrations.

Revision ID: 0003_workspace_collections
Revises: 6014276fbd67
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_workspace_collections"
down_revision: str | None = "6014276fbd67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=120)),
        sa.Column("added_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "notification_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["added_by_user_id"], ["platform_users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "collection_id"),
    )
    op.create_index(
        "ix_workspace_collections_workspace_created",
        "workspace_collections",
        ["workspace_id", "created_at"],
    )
    op.execute('ALTER TABLE "workspace_collections" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "workspace_collections" FORCE ROW LEVEL SECURITY')
    op.execute(
        'CREATE POLICY "workspace_collections_workspace_isolation" '
        'ON "workspace_collections" '
        "USING (workspace_id = "
        "NULLIF(current_setting('app.workspace_id', true), '')::uuid) "
        "WITH CHECK (workspace_id = "
        "NULLIF(current_setting('app.workspace_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute(
        'DROP POLICY IF EXISTS "workspace_collections_workspace_isolation" '
        'ON "workspace_collections"'
    )
    op.drop_index(
        "ix_workspace_collections_workspace_created", table_name="workspace_collections"
    )
    op.drop_table("workspace_collections")
