"""completed and disputed bookings keep their window

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25

Found by the browser verification: a booking completed before its window
ended released the window, and it was sold again. The exclusion constraint
now covers every booking that used its time.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

HOLDING = "'awaiting_payment', 'requested', 'accepted', 'active', 'completed', 'disputed'"
BEFORE = "'awaiting_payment', 'requested', 'accepted', 'active'"


def _constraint(statuses: str) -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS ex_bookings_no_double_booking")
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT ex_bookings_no_double_booking "
        "EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end, '[)') WITH &&) "
        f"WHERE (status IN ({statuses}))"
    )


def upgrade() -> None:
    _constraint(HOLDING)


def downgrade() -> None:
    _constraint(BEFORE)
