"""currency codes uppercase (ISO 4217), as every answer gives them

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-27 09:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE bookings SET currency = UPPER(currency)")


def downgrade() -> None:
    op.execute("UPDATE bookings SET currency = LOWER(currency)")
