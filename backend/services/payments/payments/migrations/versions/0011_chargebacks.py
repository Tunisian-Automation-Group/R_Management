"""the chargeback lifecycle: dispute id, status and deadline, the payout it
held back, and what a lost one recovered from the owner (R2-3)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-27 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("dispute_id", sa.String(80), nullable=True))
    op.add_column("payments", sa.Column("dispute_status", sa.String(30), nullable=True))
    op.add_column("payments", sa.Column("dispute_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("held_payout", sa.Text(), nullable=True))
    op.add_column("payments", sa.Column("recovered_amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("owner_owes", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    for c in ("owner_owes", "recovered_amount", "held_payout", "dispute_due_at", "dispute_status", "dispute_id"):
        op.drop_column("payments", c)
