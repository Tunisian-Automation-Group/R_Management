"""media used

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25 22:17:45.488735
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("used", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("media", "used")
