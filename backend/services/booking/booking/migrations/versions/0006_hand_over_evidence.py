"""hand-over evidence

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-25 22:48:39.218124
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_evidence",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("by", sa.String(length=64), nullable=False),
        sa.Column("stage", sa.String(length=10), nullable=False),
        sa.Column("photos", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_evidence_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_evidence")),
    )
    op.create_index(op.f("ix_booking_evidence_booking_id"), "booking_evidence", ["booking_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_evidence_booking_id"), table_name="booking_evidence")
    op.drop_table("booking_evidence")
