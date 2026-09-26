"""initial notifications schema

Revision ID: 0001
Revises:
Create Date: 2026-09-25 19:21:23.925298
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(
        "ix_outbox_unsent", "outbox", ["created_at"], unique=False, postgresql_where=sa.text("sent_at IS NULL")
    )
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_events")),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_unsent", table_name="outbox", postgresql_where=sa.text("sent_at IS NULL"))
    op.drop_table("outbox")
