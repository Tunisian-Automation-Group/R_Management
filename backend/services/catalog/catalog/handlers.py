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
    await repo.apply_outcome(d["ownerId"], outcome)

    review_id = f"rv_{d['bookingId']}"
    if await repo.has_review(review_id):
        return
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
