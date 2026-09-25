"""renter record

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-25 23:12:49.185243
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("owners", sa.Column("renter_rating_sum", sa.Integer(), server_default="0", nullable=False))
    op.add_column("owners", sa.Column("renter_jobs", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("owners", "renter_jobs")
    op.drop_column("owners", "renter_rating_sum")
