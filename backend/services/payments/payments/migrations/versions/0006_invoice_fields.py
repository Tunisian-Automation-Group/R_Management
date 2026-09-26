"""invoice fields for § 14 UStG: the service, its date and the recipient

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26 03:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

COLUMNS = [
    ("title", sa.String(length=200)),
    ("service_start", sa.DateTime(timezone=True)),
    ("service_end", sa.DateTime(timezone=True)),
    ("recipient_name", sa.String(length=200)),
    ("recipient_address", sa.String(length=400)),
    ("recipient_vat_id", sa.String(length=20)),
]


def upgrade() -> None:
    for name, type_ in COLUMNS:
        op.add_column("invoices", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("invoices", name)
