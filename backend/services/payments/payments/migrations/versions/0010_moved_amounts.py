"""what moved: refunded and paid-out amounts, not only their ids

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("refunded_amount", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("paid_out_amount", sa.Integer(), nullable=False, server_default="0"))
    # Rows before this: full refunds and plain payouts are known exactly. A
    # partial one's split was never stored; it shows 0 until the next change.
    op.execute("UPDATE payments SET refunded_amount = amount WHERE status = 'refunded' AND refund_id IS NOT NULL")
    # "refunded" with nothing refunded and the owner paid (a renter no-show,
    # before this) was an ordinary payout.
    op.execute(
        "UPDATE payments SET status = 'transferred' "
        "WHERE status IN ('refunded', 'partially_refunded') AND refund_id IS NULL AND transfer_id IS NOT NULL"
    )
    op.execute("UPDATE payments SET paid_out_amount = owner_net WHERE status = 'transferred'")


def downgrade() -> None:
    op.drop_column("payments", "paid_out_amount")
    op.drop_column("payments", "refunded_amount")
