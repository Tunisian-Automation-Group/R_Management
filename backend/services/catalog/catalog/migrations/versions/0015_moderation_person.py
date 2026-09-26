"""moderation actions: whom each decision is about

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-27 09:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moderation_actions", sa.Column("person_id", sa.String(length=64), nullable=True))
    op.create_index("ix_moderation_actions_person", "moderation_actions", ["person_id"])
    # Earlier decisions: the owner themselves, or their listing's owner. A
    # message or review decision before this change stays unattributed.
    op.execute("UPDATE moderation_actions SET person_id = target_id WHERE target_type = 'owner'")
    op.execute(
        "UPDATE moderation_actions SET person_id = "
        "(SELECT owner_id FROM listings WHERE listings.id = moderation_actions.target_id) "
        "WHERE target_type = 'listing'"
    )


def downgrade() -> None:
    op.drop_index("ix_moderation_actions_person", table_name="moderation_actions")
    op.drop_column("moderation_actions", "person_id")
