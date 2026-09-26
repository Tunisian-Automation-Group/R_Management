"""verified people

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-25 23:02:56.070399
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verified_people",
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_verified_people")),
    )


def downgrade() -> None:
    op.drop_table("verified_people")
