"""booking handover

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25 21:43:22.952084
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("handover", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("bookings", sa.Column("request_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "request_hash")
    op.drop_column("bookings", "handover")
