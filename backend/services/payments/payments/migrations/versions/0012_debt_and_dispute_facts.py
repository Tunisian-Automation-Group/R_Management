"""what a payout kept back for an owner's lost chargeback (R2-20), and what
the staff chargebacks list shows: the dispute's reason and the listing title
(R2-24)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-28 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("debt_deducted", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("payments", sa.Column("dispute_reason", sa.String(40), nullable=True))
    op.add_column("payments", sa.Column("title", sa.String(200), nullable=True))


def downgrade() -> None:
    for c in ("title", "dispute_reason", "debt_deducted"):
        op.drop_column("payments", c)
