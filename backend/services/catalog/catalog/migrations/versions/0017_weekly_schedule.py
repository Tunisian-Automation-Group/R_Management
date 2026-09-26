"""weekly schedules (H-4): generated windows, how far they go, idle notices

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-27 12:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("slots", sa.Column("generated", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("listings", sa.Column("scheduled_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("listings", sa.Column("idle_notice_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_listings_scheduled_until", "listings", ["scheduled_until"])


def downgrade() -> None:
    op.drop_index("ix_listings_scheduled_until", table_name="listings")
    op.drop_column("listings", "idle_notice_at")
    op.drop_column("listings", "scheduled_until")
    op.drop_column("slots", "generated")
