"""legal invoice documents: the issuer as it was at issue, the tax
treatment (reverse charge, not taxable), the rendered Factur-X PDF kept as
issued, and credit notes (Rechnungskorrektur) in their own number series

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-28 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

ISSUER = (
    ("issuer_name", 200),
    ("issuer_address", 400),
    ("issuer_vat_id", 20),
    ("issuer_tax_number", 40),
    ("issuer_register", 200),
    ("issuer_directors", 200),
    ("issuer_email", 200),
    ("issuer_country", 2),
    ("recipient_country", 2),
    ("document_lang", 5),
    ("pdf_sha256", 64),
)


def upgrade() -> None:
    op.add_column("invoices", sa.Column("tax_treatment", sa.String(20), nullable=False, server_default="standard"))
    for name, size in ISSUER:
        op.add_column("invoices", sa.Column(name, sa.String(size), nullable=True))
    op.add_column("invoices", sa.Column("pdf", sa.LargeBinary(), nullable=True))
    op.create_table(
        "credit_notes",
        sa.Column("number", sa.String(20), primary_key=True),
        sa.Column("corrects", sa.String(20), nullable=False, index=True),
        sa.Column("booking_id", sa.String(40), nullable=False, index=True),
        sa.Column("owner_id", sa.String(64), nullable=False, index=True),
        sa.Column("net", sa.Integer(), nullable=False),
        sa.Column("vat_rate_bps", sa.Integer(), nullable=False),
        sa.Column("vat", sa.Integer(), nullable=False),
        sa.Column("gross", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_lang", sa.String(5), nullable=True),
        sa.Column("pdf", sa.LargeBinary(), nullable=True),
        sa.Column("pdf_sha256", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("credit_notes")
    op.drop_column("invoices", "pdf")
    for name, _ in reversed(ISSUER):
        op.drop_column("invoices", name)
    op.drop_column("invoices", "tax_treatment")
