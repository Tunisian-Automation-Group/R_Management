"""moderation

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-25 22:46:17.829746
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "moderation_actions",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("target_type", sa.String(length=10), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("report_id", sa.String(length=40), nullable=True),
        sa.Column("statement", sa.String(length=2000), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_moderation_actions")),
    )
    op.create_index("ix_moderation_actions_at", "moderation_actions", ["at"], unique=False)
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=10), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=20), nullable=False),
        sa.Column("details", sa.String(length=2000), nullable=False),
        sa.Column("reporter_id", sa.String(length=64), nullable=True),
        sa.Column("reporter_email", sa.String(length=254), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("statement", sa.String(length=2000), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_index("ix_reports_status_created", "reports", ["status", "created_at"], unique=False)
    op.add_column("listings", sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("owners", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("owners", "suspended_at")
    op.drop_column("listings", "moderated_at")
    op.drop_index("ix_reports_status_created", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_moderation_actions_at", table_name="moderation_actions")
    op.drop_table("moderation_actions")
