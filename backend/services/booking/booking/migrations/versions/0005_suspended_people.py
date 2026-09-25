"""suspended people

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25 22:46:18.367089
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "suspended",
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_suspended")),
    )


def downgrade() -> None:
    op.drop_table("suspended")
