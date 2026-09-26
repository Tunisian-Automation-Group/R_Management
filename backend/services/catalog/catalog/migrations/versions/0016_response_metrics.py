"""owners: measured response time and rate (H-1)

The response time used to default to 60 minutes for everyone and was never
updated: shown as fact, it was invented. Now booking measures it; until it
has, it is unknown.

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-27 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("owners") as b:
        b.alter_column("response_mins", existing_type=sa.Integer(), nullable=True)
        b.add_column(sa.Column("response_rate", sa.Float(), nullable=True))
    op.execute("UPDATE owners SET response_mins = NULL")


def downgrade() -> None:
    with op.batch_alter_table("owners") as b:
        b.drop_column("response_rate")
