"""payable owners

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25 19:50:45.625012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payable_owners",
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("ready", sa.Boolean(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("owner_id", name=op.f("pk_payable_owners")),
    )


def downgrade() -> None:
    op.drop_table("payable_owners")
