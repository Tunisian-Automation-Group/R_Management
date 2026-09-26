"""push devices remember which app install registered them

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("install_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("devices", "install_hash")
