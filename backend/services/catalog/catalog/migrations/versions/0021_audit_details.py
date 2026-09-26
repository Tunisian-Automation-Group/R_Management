"""the facts of a staff action, for the console to render in words (V6-9)

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-27 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moderation_actions", sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("moderation_actions", "details")
