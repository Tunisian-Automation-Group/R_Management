"""currency codes uppercase (ISO 4217), as every answer gives them

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27 09:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("payments", "invoices"):
        op.execute(f"UPDATE {table} SET currency = UPPER(currency)")


def downgrade() -> None:
    for table in ("payments", "invoices"):
        op.execute(f"UPDATE {table} SET currency = LOWER(currency)")
