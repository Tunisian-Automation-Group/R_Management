"""a photo's dominant colour, its placeholder while loading; renditions (U-40)

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-27 23:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("color", sa.String(7), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "color")
