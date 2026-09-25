"""What booking does when payments tells it something."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import PAYMENT_AUTHORISED, PAYMENT_FAILED, Event, Handler, Outbox

from .repository import BookingRepository
from .settings import Settings
from .state import SystemAction, system_status
from .tables import OUTBOX, BookingRow

log = logging.getLogger(__name__)


def answer_deadline(settings: Settings, now: datetime, row: BookingRow) -> datetime:
    """An owner has a day to answer, and never past the window's start."""
    return min(now + settings.answer_within, row.window_start)


def handlers(settings: Settings) -> dict[str, Handler]:
    outbox = Outbox(OUTBOX, settings.service_name)

    async def apply(session: AsyncSession, event: Event, action: SystemAction) -> None:
        repo = BookingRepository(session, outbox)
        row = await session.get(BookingRow, event.data["bookingId"], with_for_update=True)
        if row is None:
            log.warning("%s for unknown booking %s", event.type, event.data["bookingId"])
            return
        to = system_status(action, row.status)
        if to is None:
            # Already moved on (cancelled, expired). Payments voids the
            # authorisation when it sees that status change.
            return
        now = datetime.now(UTC)
        expires = answer_deadline(settings, now, row) if to == "requested" else None
        await repo.move(row, to, "payments", now, expires_at=expires)

    async def on_authorised(session: AsyncSession, event: Event) -> None:
        await apply(session, event, "authorised")

    async def on_failed(session: AsyncSession, event: Event) -> None:
        await apply(session, event, "payment_failed")

    return {PAYMENT_AUTHORISED: on_authorised, PAYMENT_FAILED: on_failed}
