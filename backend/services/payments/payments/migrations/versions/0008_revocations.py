"""sessions revoked early

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26 12:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("sub", sa.String(length=64), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sub", name=op.f("pk_revoked_sessions")),
    )


def downgrade() -> None:
    op.drop_table("revoked_sessions")
