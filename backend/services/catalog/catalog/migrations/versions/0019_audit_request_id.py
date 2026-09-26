"""the staff audit log (H-7): the request each action was done in, and lookups by target and actor

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-27 15:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("moderation_actions", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.create_index("ix_moderation_actions_target", "moderation_actions", ["target_id", "at"])
    op.create_index("ix_moderation_actions_actor", "moderation_actions", ["actor_id", "at"])


def downgrade() -> None:
    op.drop_index("ix_moderation_actions_actor", table_name="moderation_actions")
    op.drop_index("ix_moderation_actions_target", table_name="moderation_actions")
    op.drop_column("moderation_actions", "request_id")
