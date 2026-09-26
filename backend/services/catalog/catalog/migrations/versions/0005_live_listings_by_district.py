"""live listings by district

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-25 22:06:07.881293
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_listings_live_district",
        "listings",
        ["district"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL AND active"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listings_live_district", table_name="listings", postgresql_where=sa.text("deleted_at IS NULL AND active")
    )
