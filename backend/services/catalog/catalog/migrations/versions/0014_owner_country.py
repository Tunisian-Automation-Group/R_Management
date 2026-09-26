"""owners: country of residence (M-9)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-26 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Everyone so far signed up in Germany, the first market.
    op.add_column("owners", sa.Column("country", sa.String(length=2), server_default="DE", nullable=False))


def downgrade() -> None:
    op.drop_column("owners", "country")
