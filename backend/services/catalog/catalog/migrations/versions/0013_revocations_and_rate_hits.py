"""sessions revoked early, and per-person rate counters

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-26 12:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_sessions",
        sa.Column("sub", sa.String(length=64), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sub", name=op.f("pk_revoked_sessions")),
    )
    op.create_table(
        "rate_hits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rate_hits")),
    )
    op.create_index("ix_rate_hits_key_at", "rate_hits", ["key", "at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rate_hits_key_at", table_name="rate_hits")
    op.drop_table("rate_hits")
    op.drop_table("revoked_sessions")
