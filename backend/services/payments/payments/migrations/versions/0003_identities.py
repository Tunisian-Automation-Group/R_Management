"""identities

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25 23:02:55.486904
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "identities",
        sa.Column("person_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("person_id", name=op.f("pk_identities")),
        sa.UniqueConstraint("session_id", name=op.f("uq_identities_session_id")),
    )


def downgrade() -> None:
    op.drop_table("identities")
