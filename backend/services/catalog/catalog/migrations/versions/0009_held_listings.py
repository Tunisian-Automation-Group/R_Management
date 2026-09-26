"""held listings

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-25 23:01:04.182149
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "held_at")
