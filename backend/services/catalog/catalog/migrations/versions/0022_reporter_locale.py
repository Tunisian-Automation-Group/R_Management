"""the language a signed-out reporter wrote in, for their mails (V8-12)

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-27 22:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("reporter_locale", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "reporter_locale")
