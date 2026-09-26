"""traders, minimum age, owner reliability, structured statements of reasons

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-26 02:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _json() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column("owners", sa.Column("business", _json(), nullable=True))
    op.add_column("owners", sa.Column("adult_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("owners", sa.Column("cancellation_rate", sa.Float(), nullable=True))
    # Everyone who signed up before the age question accepted the terms that
    # already required 18+: grandfathered as confirmed now.
    op.execute("UPDATE owners SET adult_confirmed_at = now() WHERE adult_confirmed_at IS NULL")
    op.add_column("reports", sa.Column("statement_of_reasons", _json(), nullable=True))
    op.add_column("moderation_actions", sa.Column("statement_of_reasons", _json(), nullable=True))


def downgrade() -> None:
    op.drop_column("moderation_actions", "statement_of_reasons")
    op.drop_column("reports", "statement_of_reasons")
    op.drop_column("owners", "cancellation_rate")
    op.drop_column("owners", "adult_confirmed_at")
    op.drop_column("owners", "business")
