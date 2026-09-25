"""messages keep the words as written, shown once the booking is accepted

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-26 03:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booking_messages", sa.Column("unmasked", sa.String(length=2000), nullable=True))


def downgrade() -> None:
    op.drop_column("booking_messages", "unmasked")
