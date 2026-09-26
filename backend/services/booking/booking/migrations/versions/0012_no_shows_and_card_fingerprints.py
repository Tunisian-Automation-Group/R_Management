"""no-shows and card fingerprints

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("no_show", sa.String(length=6), nullable=True))
    op.add_column("bookings", sa.Column("card_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_bookings_card_fingerprint", "bookings", ["card_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_bookings_card_fingerprint", table_name="bookings")
    op.drop_column("bookings", "card_fingerprint")
    op.drop_column("bookings", "no_show")
