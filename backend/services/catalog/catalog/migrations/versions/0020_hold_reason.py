"""listings held because their place is not in an open market (V5-1)

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-27 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("hold_reason", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("listings", "hold_reason")
