"""card fingerprints

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("card_fingerprint", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("payments", "card_fingerprint")
