"""consent recorded before an identity check

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("identities", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("identities", sa.Column("consent_version", sa.String(length=40), nullable=True))


def downgrade() -> None:
    op.drop_column("identities", "consent_version")
    op.drop_column("identities", "consent_at")
