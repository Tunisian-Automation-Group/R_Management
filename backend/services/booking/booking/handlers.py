"""What booking does when payments tells it something."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import (
    IDENTITY_VERIFIED,
    LISTING_CHANGED,
    OWNER_SUSPENDED,
    PAYMENT_AUTHORISED,
    PAYMENT_FAILED,
    Event,
    Handler,
    Outbox,
)

from .repository import BookingRepository
from .settings import Settings
from .state import SystemAction, system_status
from .tables import OUTBOX, BookingRow, SuspendedRow, VerifiedRow

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

    async def on_listing_changed(session: AsyncSession, event: Event) -> None:
        if event.data.get("change") != "removed":
            return
        repo = BookingRepository(session, outbox)
        now = datetime.now(UTC)
        for row in await repo.pending_for_listing(event.data["listingId"]):
            to = system_status("listing_removed", row.status)
            if to:
                await repo.move(
                    row, to, "system", now, expires_at=None, decline_reason="The listing was removed by its owner"
                )

    async def on_suspended(session: AsyncSession, event: Event) -> None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, SuspendedRow, person_id=event.data["ownerId"], at=datetime.now(UTC))

    async def on_verified(session: AsyncSession, event: Event) -> None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, VerifiedRow, person_id=event.data["personId"], at=datetime.now(UTC))

    return {
        IDENTITY_VERIFIED: on_verified,
        PAYMENT_AUTHORISED: on_authorised,
        PAYMENT_FAILED: on_failed,
        LISTING_CHANGED: on_listing_changed,
        OWNER_SUSPENDED: on_suspended,
    }
