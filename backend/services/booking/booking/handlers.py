"""What booking does when payments tells it something."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import (
    IDENTITY_VERIFIED,
    LISTING_CHANGED,
    OWNER_REINSTATED,
    OWNER_SUSPENDED,
    PAYMENT_AUTHORISED,
    PAYMENT_FAILED,
    PERSON_FLAGGED,
    PROFILE_DELETED,
    Event,
    Handler,
    Outbox,
)

from .repository import BookingRepository
from .settings import Settings
from .state import SystemAction, system_status
from .tables import OUTBOX, BlockRow, BookingRow, SuspendedRow, VerifiedRow

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
        row = await session.get(BookingRow, event.data["bookingId"])
        instant = bool(row and (row.listing_snapshot or {}).get("instantBook"))
        await apply(session, event, "authorised_instant" if instant else "authorised")
        fp = event.data.get("cardFingerprint")
        if row is not None and fp:
            await linked_card(session, row, fp)

    async def linked_card(session: AsyncSession, row: BookingRow, fp: str) -> None:
        """S-17: a card a suspended account paid with, now on a new account.
        The booking goes ahead (a shared family card is not fraud); staff look."""
        row.card_fingerprint = fp
        linked = await BookingRepository(session, outbox).card_linked_to_suspended(fp, row.requester_id)
        if linked:
            log.warning("booking %s paid with a card a suspended account used", row.id)
            await outbox.add(
                session,
                PERSON_FLAGGED,
                {
                    "personId": row.requester_id,
                    "reason": "linked_to_suspended",
                    "details": f"Paid booking {row.id} with a card that suspended account {linked} also used.",
                },
            )

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
        # Their own pending requests go too (their listings' requests are
        # declined through listing.changed).
        repo = BookingRepository(session, outbox)
        now = datetime.now(UTC)
        for row in await repo.pending_of_requester(event.data["ownerId"]):
            if to := system_status("listing_removed", row.status):
                await repo.move(row, to, "system", now, expires_at=None, decline_reason="The account was suspended")

    async def on_reinstated(session: AsyncSession, event: Event) -> None:
        from sqlalchemy import delete

        await session.execute(delete(SuspendedRow).where(SuspendedRow.person_id == event.data["ownerId"]))

    async def on_verified(session: AsyncSession, event: Event) -> None:
        from cappy_common.db import insert_or_ignore

        await insert_or_ignore(session, VerifiedRow, person_id=event.data["personId"], at=datetime.now(UTC))

    async def on_profile_deleted(session: AsyncSession, event: Event) -> None:
        """Their blocks and flags go; bookings stay (financial records)."""
        from sqlalchemy import delete, or_, update

        person = event.data["ownerId"]
        await session.execute(delete(BlockRow).where(or_(BlockRow.blocker_id == person, BlockRow.blocked_id == person)))
        await session.execute(delete(VerifiedRow).where(VerifiedRow.person_id == person))
        # What they wrote may name them or hold their number: the other side
        # keeps the conversation's shape, not their words.
        from .tables import MessageRow

        await session.execute(
            update(MessageRow)
            .where(MessageRow.sender_id == person)
            .values(body="[removed: the account was deleted]", unmasked=None)
        )

    return {
        PROFILE_DELETED: on_profile_deleted,
        IDENTITY_VERIFIED: on_verified,
        PAYMENT_AUTHORISED: on_authorised,
        PAYMENT_FAILED: on_failed,
        LISTING_CHANGED: on_listing_changed,
        OWNER_SUSPENDED: on_suspended,
        OWNER_REINSTATED: on_reinstated,
    }
