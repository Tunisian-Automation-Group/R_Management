"""What the catalog does when other services tell it something."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import Event
from cappy_common.models import Outcome, Review
from cappy_common.timeutil import dt_from_iso

from .repository import CatalogRepository


def short_name(name: str) -> str:
    """How a reviewer is shown to strangers: "Ada L.", never a full name."""
    parts = name.split()
    return parts[0] if len(parts) < 2 else f"{parts[0]} {parts[-1][0]}."


async def on_renter_rated(session: AsyncSession, event: Event) -> None:
    await CatalogRepository(session).apply_renter_rating(event.data["renterId"], int(event.data["quality"]))


async def on_payouts_ready(session: AsyncSession, event: Event) -> None:
    d = event.data
    as_of = dt_from_iso(d.get("asOf") or event.occurred_at)
    await CatalogRepository(session).set_payable(d["ownerId"], bool(d["ready"]), as_of)


async def on_booking_rated(session: AsyncSession, event: Event) -> None:
    """The write half of the loop. A rated booking moves its owner's record
    (which moves where they rank for everyone) and becomes a review the next
    buyer reads — both in one transaction, and exactly once: the dispatcher
    records the event id in the same transaction, so a redelivery is a no-op."""
    d = event.data
    repo = CatalogRepository(session)
    outcome = Outcome.model_validate(d["outcome"])
    review_id = f"rv_{d['bookingId']}"
    if await repo.has_review(review_id):
        # The same booking's rating again (a republished event): count it once.
        return
    await repo.apply_outcome(d["ownerId"], outcome)
    try:
        await repo.listing_row(d["listingId"], include_deleted=True)
    except Exception:  # noqa: BLE001 - a listing that never existed has no page for the words
        return
    author = await repo.find_owner(d["requesterId"]) if d.get("requesterId") else None
    await repo.add_review(
        Review(
            id=review_id,
            listing_id=d["listingId"],
            owner_id=d["ownerId"],
            author=short_name(author.name) if author else "A buyer",
            initials=author.initials if author else "??",
            author_id=d.get("requesterId"),
            rating=outcome.quality,
            on_time=outcome.on_time,
            text=(outcome.note or "")[:1000],
            tags=outcome.tags or [],
            at=d["at"],
        )
    )


async def on_owner_reliability(session: AsyncSession, event: Event) -> None:
    """Booking measured an owner: cancellations and no-shows (S-18), or how
    fast and how often they answer requests (H-1). Each event carries one of
    the two; a field it does not carry is left as it was."""
    from .tables import OwnerRow

    d = event.data
    row = await session.get(OwnerRow, d["ownerId"], with_for_update=True)
    if row is None:
        return
    if "rate" in d:
        row.cancellation_rate = d["rate"]
    if "responseMins" in d:
        row.response_mins, row.response_rate = d["responseMins"], d.get("responseRate")


async def on_person_flagged(session: AsyncSession, event: Event) -> None:
    """Something for staff nobody reported (S-17, S-18): it joins the reports
    queue as a notice from the system, once while an earlier one is open."""
    from .moderation import flag

    d = event.data
    await flag(session, d["personId"], d["reason"], d["details"])


async def on_identity_verified(session: AsyncSession, event: Event) -> None:
    """A passed ID check shows on the profile as "verified" (F-10)."""
    from .tables import OwnerRow

    row = await session.get(OwnerRow, event.data["personId"], with_for_update=True)
    if row is not None and row.deleted_at is None:
        row.verified = True
