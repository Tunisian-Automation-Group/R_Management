"""the app locale each person last used

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-26 16:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_prefs", sa.Column("locale", sa.String(length=35), nullable=True))


def downgrade() -> None:
    op.drop_column("notification_prefs", "locale")
