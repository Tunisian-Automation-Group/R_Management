"""listing handover address

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25 21:43:22.426817
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("address", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "address")
