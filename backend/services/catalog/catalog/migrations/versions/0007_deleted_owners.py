"""deleted owners

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-25 22:38:59.139172
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("owners", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("owners", "deleted_at")
