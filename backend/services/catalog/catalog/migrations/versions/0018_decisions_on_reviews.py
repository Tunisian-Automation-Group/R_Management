"""moderation actions: attribute earlier review decisions to their author

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-27 12:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0015 attributed owner and listing decisions; a review's author is here
    # too. Message authors live in booking: catalog's jobs attribute those.
    op.execute(
        "UPDATE moderation_actions SET person_id = "
        "(SELECT author_id FROM reviews WHERE reviews.id = moderation_actions.target_id) "
        "WHERE target_type = 'review' AND person_id IS NULL"
    )


def downgrade() -> None:
    pass
