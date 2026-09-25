"""blind reviews

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-25 23:17:50.528069
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("rated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("reviews_published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "reviews_published_at")
    op.drop_column("bookings", "rated_at")
