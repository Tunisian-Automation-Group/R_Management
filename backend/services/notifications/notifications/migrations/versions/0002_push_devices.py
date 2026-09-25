"""push devices

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25 22:26:26.661533
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("token", sa.String(length=400), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("endpoint", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_devices")),
    )
    op.create_index(op.f("ix_devices_user_id"), "devices", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_devices_user_id"), table_name="devices")
    op.drop_table("devices")
