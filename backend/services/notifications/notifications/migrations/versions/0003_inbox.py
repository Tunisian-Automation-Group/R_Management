"""inbox: the notification centre

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 00:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("link", sa.String(length=300), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inbox")),
    )
    op.create_index("ix_inbox_user_at", "inbox", ["user_id", "at", "id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_inbox_user_at", table_name="inbox")
    op.drop_table("inbox")
