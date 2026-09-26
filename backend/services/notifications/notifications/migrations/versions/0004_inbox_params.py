"""inbox items keep their text params, rendered in the reader's language

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26 03:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbox", sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("inbox", "params")
