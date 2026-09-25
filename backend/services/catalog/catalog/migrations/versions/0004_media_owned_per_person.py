"""media owned per person

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-25 21:55:46.888822
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per (photo, owner): two people uploading the same picture both own it.
    op.drop_constraint("pk_media", "media", type_="primary")
    op.create_primary_key("pk_media", "media", ["name", "owner_id"])


def downgrade() -> None:
    op.drop_constraint("pk_media", "media", type_="primary")
    op.create_primary_key("pk_media", "media", ["name"])
