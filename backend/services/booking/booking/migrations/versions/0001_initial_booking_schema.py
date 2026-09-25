"""initial booking schema

Revision ID: 0001
Revises:
Create Date: 2026-09-25 19:09:07.207131
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("requester_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("listing_id", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("requirement", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("match", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("listing_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decline_reason", sa.String(length=500), nullable=True),
        sa.Column("outcome", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.UniqueConstraint("requester_id", "idempotency_key", name="uq_bookings_requester_idempotency"),
        sa.CheckConstraint("window_end > window_start", name=op.f("ck_bookings_window_forward")),
    )
    # ADR 0004: two bookings that hold a window can never overlap on one
    # listing, however many requests race for it.
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT ex_bookings_no_double_booking "
        "EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end, '[)') WITH &&) "
        "WHERE (status IN ('awaiting_payment', 'requested', 'accepted', 'active'))"
    )
    op.create_index("ix_bookings_listing_window", "bookings", ["listing_id", "window_start"], unique=False)
    op.create_index("ix_bookings_owner_created", "bookings", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_bookings_requester_created", "bookings", ["requester_id", "created_at"], unique=False)
    op.create_index("ix_bookings_status_expires", "bookings", ["status", "expires_at"], unique=False)
    op.create_index("ix_bookings_status_window_end", "bookings", ["status", "window_end"], unique=False)
    op.create_table(
        "outbox",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox")),
    )
    op.create_index(
        "ix_outbox_unsent", "outbox", ["created_at"], unique=False, postgresql_where=sa.text("sent_at IS NULL")
    )
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_events")),
    )
    op.create_table(
        "booking_transitions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("by", sa.String(length=64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["bookings.id"], name=op.f("fk_booking_transitions_booking_id_bookings"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_booking_transitions")),
    )
    op.create_index(op.f("ix_booking_transitions_booking_id"), "booking_transitions", ["booking_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_booking_transitions_booking_id"), table_name="booking_transitions")
    op.drop_table("booking_transitions")
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_unsent", table_name="outbox", postgresql_where=sa.text("sent_at IS NULL"))
    op.drop_table("outbox")
    op.drop_index("ix_bookings_status_window_end", table_name="bookings")
    op.drop_index("ix_bookings_status_expires", table_name="bookings")
    op.drop_index("ix_bookings_requester_created", table_name="bookings")
    op.drop_index("ix_bookings_owner_created", table_name="bookings")
    op.drop_index("ix_bookings_listing_window", table_name="bookings")
    op.drop_table("bookings")
