"""fee invoices

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25 23:21:05.202788
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year", name=op.f("pk_invoice_counters")),
    )
    op.create_table(
        "invoices",
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("net", sa.Integer(), nullable=False),
        sa.Column("vat_rate_bps", sa.Integer(), nullable=False),
        sa.Column("vat", sa.Integer(), nullable=False),
        sa.Column("gross", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("number", name=op.f("pk_invoices")),
        sa.UniqueConstraint("booking_id", name=op.f("uq_invoices_booking_id")),
    )
    op.create_index(op.f("ix_invoices_owner_id"), "invoices", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_invoices_owner_id"), table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("invoice_counters")
