"""initial payments schema

Revision ID: 0001
Revises:
Create Date: 2026-09-25 19:19:29.953211
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
    op.create_table(
        "connect_accounts",
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=80), nullable=False),
        sa.Column("payouts_enabled", sa.Boolean(), nullable=False),
        sa.Column("details_submitted", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("owner_id", name=op.f("pk_connect_accounts")),
        sa.UniqueConstraint("account_id", name=op.f("uq_connect_accounts_account_id")),
    )
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
        "payments",
        sa.Column("booking_id", sa.String(length=40), nullable=False),
        sa.Column("intent_id", sa.String(length=80), nullable=False),
        sa.Column("requester_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("owner_net", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("charge_id", sa.String(length=80), nullable=True),
        sa.Column("transfer_id", sa.String(length=80), nullable=True),
        sa.Column("refund_id", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("booking_id", name=op.f("pk_payments")),
        sa.UniqueConstraint("intent_id", name=op.f("uq_payments_intent_id")),
    )
    op.create_index(op.f("ix_payments_owner_id"), "payments", ["owner_id"], unique=False)
    op.create_index(op.f("ix_payments_requester_id"), "payments", ["requester_id"], unique=False)
    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id", name=op.f("pk_processed_events")),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_index(op.f("ix_payments_requester_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_owner_id"), table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_outbox_unsent", table_name="outbox", postgresql_where=sa.text("sent_at IS NULL"))
    op.drop_table("outbox")
    op.drop_table("connect_accounts")
