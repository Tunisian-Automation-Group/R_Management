"""when each side last opened a conversation, for the inbox's unread count

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-27 22:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_reads",
        sa.Column("booking_id", sa.String(40), sa.ForeignKey("bookings.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_id", sa.String(64), primary_key=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message_reads")
