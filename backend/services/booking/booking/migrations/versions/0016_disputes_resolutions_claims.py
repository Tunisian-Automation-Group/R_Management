"""dispute offers, staff resolutions, owners' claims, extensions (H-6, S-12, S-21)

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-27 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("extends_id", sa.String(length=40), nullable=True))
    op.create_index("ix_bookings_status_updated", "bookings", ["status", "updated_at"])
    op.create_table(
        "booking_disputes",
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("by", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("respond_by", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("offer_amount", sa.Integer(), nullable=True),
        sa.Column("offer_by", sa.String(length=64), nullable=True),
        sa.Column("offer_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_disputes_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("booking_id", name=op.f("pk_booking_disputes")),
    )
    op.create_index(op.f("ix_booking_disputes_respond_by"), "booking_disputes", ["respond_by"], unique=False)
    # Disputes opened before this table: the 72 hours start now.
    op.execute(
        "INSERT INTO booking_disputes (booking_id, by, reason, opened_at, respond_by) "
        "SELECT id, requester_id, COALESCE(decline_reason, ''), updated_at, "
        "CURRENT_TIMESTAMP + INTERVAL '72 hours' FROM bookings WHERE status = 'disputed'"
    )
    op.create_table(
        "booking_resolutions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("refund_amount", sa.Integer(), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=False),
        sa.Column("by", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("approved_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_resolutions_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_resolutions")),
    )
    op.create_index(op.f("ix_booking_resolutions_booking_id"), "booking_resolutions", ["booking_id"], unique=False)
    op.create_table(
        "booking_claims",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("by", sa.String(length=64), nullable=False),
        sa.Column("minutes_late", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_claims_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_claims")),
        sa.UniqueConstraint("booking_id", "kind", name="uq_booking_claims_booking_kind"),
    )
    op.create_index(op.f("ix_booking_claims_booking_id"), "booking_claims", ["booking_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_claims_booking_id"), table_name="booking_claims")
    op.drop_table("booking_claims")
    op.drop_index(op.f("ix_booking_resolutions_booking_id"), table_name="booking_resolutions")
    op.drop_table("booking_resolutions")
    op.drop_index(op.f("ix_booking_disputes_respond_by"), table_name="booking_disputes")
    op.drop_table("booking_disputes")
    op.drop_index("ix_bookings_status_updated", table_name="bookings")
    op.drop_column("bookings", "extends_id")
