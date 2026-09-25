"""renter rating

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25 23:12:49.713099
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("renter_rating", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "renter_rating")
