"""messages and blocks

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25 22:41:36.599487
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blocks",
        sa.Column("blocker_id", sa.String(length=64), nullable=False),
        sa.Column("blocked_id", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("blocker_id", "blocked_id", name=op.f("pk_blocks")),
    )
    op.create_table(
        "booking_messages",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("sender_id", sa.String(length=64), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_messages_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_messages")),
    )
    op.create_index("ix_booking_messages_booking_at", "booking_messages", ["booking_id", "at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_booking_messages_booking_at", table_name="booking_messages")
    op.drop_table("booking_messages")
    op.drop_table("blocks")
