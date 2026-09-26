"""Every read and write of bookings, and the events that go with them.

Each status change goes through ``move``: it updates the row, appends to the
audit trail and writes ``booking.status_changed`` to the outbox, all in the
caller's transaction. Payments and notifications act on that event.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from pydantic import TypeAdapter
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.errors import NotFound
from cappy_common.events import (
    BOOKING_RATED,
    BOOKING_STATUS_CHANGED,
    OWNER_RELIABILITY,
    PERSON_FLAGGED,
    RENTER_RATED,
    Outbox,
)
from cappy_common.markets import market_of_currency
from cappy_common.models import Booking, Handover, ListingSnapshot, Match, Outcome, Requirement
from cappy_common.pagination import decode_cursor, encode_cursor
from cappy_common.reasons import code_of
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .state import HOLDING, OPEN
from .tables import BookingRow, SuspendedRow, TransitionRow

_requirement = TypeAdapter(Requirement)


def to_booking(row: BookingRow, viewer: str) -> Booking:
    # Blind reviews: until both are published, neither side sees the other's.
    blind = row.reviews_published_at is None
    outcome = row.outcome if not (blind and viewer == row.owner_id) else None
    renter_rating = row.renter_rating if not (blind and viewer == row.requester_id) else None
    """``requesterId`` is absent when the viewer is the requester and present
    when someone is asking *them*: the app's Earn inbox keys on it."""
    return Booking(
        id=row.id,
        match=Match.model_validate(row.match),
        requirement=_requirement.validate_python(row.requirement),
        status=row.status,  # type: ignore[arg-type]
        created_at=iso_from_datetime(row.created_at),
        requester_id=None if row.requester_id == viewer else row.requester_id,
        decline_reason=row.decline_reason,
        decline_reason_code=code_of(row.decline_reason),
        outcome=Outcome.model_validate(outcome) if outcome else None,
        listing=ListingSnapshot.model_validate(row.listing_snapshot),
        expires_at=iso_from_datetime(row.expires_at) if row.expires_at else None,
        handover=Handover.model_validate(row.handover) if row.handover and row.status in SHOWS_HANDOVER else None,
        can_start_from=iso_from_datetime(row.window_start - START_EARLY) if row.status == "accepted" else None,
        late_return_from=iso_from_datetime(row.window_end - LATE_RETURN_EARLY)
        if row.status in ("active", "completed", "disputed")
        else None,
        renter_rating=renter_rating,
        refund_amount=row.refund_amount,
        currency=row.currency,
        no_show=row.no_show,
        extends_id=row.extends_id,
        **money_of(row),
    )


CAPTURED = frozenset({"accepted", "active", "completed", "disputed"})


def money_of(row: BookingRow) -> dict[str, int]:
    """The money of a booking from its own facts, the way payments moves it
    (payments/handlers.py): charged at accept; a cancelled booking was charged
    only if it recorded a refund; the owner gets their share of what was kept.
    What reached the owner is payments' to say: the detail view overlays its
    real figures (``payments_money``), a list leaves ``paid_out`` out."""
    charged = (
        row.amount if row.status in CAPTURED or (row.status == "cancelled" and row.refund_amount is not None) else 0
    )
    refunded = min(charged, row.refund_amount or 0) if charged else 0
    owner_net = int((row.match or {}).get("quote", {}).get("ownerNet", 0))
    share = (charged - refunded) * owner_net // row.amount if row.amount else 0
    return {
        "charged": charged,
        "refunded": refunded,
        "owner_share": share,
    }


def payments_money(state: dict) -> dict[str, int]:
    """Payments' own record (/internal/bookings/{id}/payment) as booking fields;
    nothing when it carries no amounts (an older payments service)."""
    if "captured" not in state:
        return {}
    return {
        "charged": state["captured"],
        "refunded": state["refunded"],
        "owner_share": (state["captured"] - state["refunded"]) * state["ownerNet"] // state["amount"]
        if state["amount"]
        else 0,
        "paid_out": state["paidOut"],
    }


# How long before the window the hand-over may be marked; set from settings
# when the app is built (booking.main).
START_EARLY = timedelta(minutes=30)
# From when the owner may report a late return: the end, or earlier locally.
LATE_RETURN_EARLY = timedelta(0)
REVIEW_WINDOW = timedelta(days=14)
RELIABILITY_WINDOW = timedelta(days=365)
RELIABILITY_MIN_BOOKINGS = 5
# H-1: how fast and how often owners answer, over 90 days, shown from 3 requests.
RESPONSE_WINDOW = timedelta(days=90)
RESPONSE_MIN_REQUESTS = 3


# The two sides see where to meet once the booking is on, and afterwards.
SHOWS_HANDOVER = frozenset({"accepted", "active", "completed", "disputed"})


def status_event(row: BookingRow, before: str | None, by: str) -> dict:
    return {
        "bookingId": row.id,
        "from": before,
        "to": row.status,
        "by": by,
        "requesterId": row.requester_id,
        "ownerId": row.owner_id,
        "listingId": row.listing_id,
        "title": row.listing_snapshot["title"],
        "ownerName": row.listing_snapshot.get("ownerName"),
        # Who asked, for the owner's mails (V7-23).
        "renterName": row.listing_snapshot.get("renterName"),
        "ownerBusiness": row.listing_snapshot.get("ownerBusiness"),
        "amount": row.amount,
        "currency": row.currency,
        "refundAmount": row.refund_amount,
        "noShow": row.no_show,
        # An extension names the booking it extends (V7-12, V7-23).
        "extendsId": row.extends_id,
        # ...and when that booking started: an extension's notices name it (V9-19).
        "extendsStart": (row.listing_snapshot or {}).get("extendsStart"),
        # Why the owner said no: the renter hears it in the notice (V5-16).
        "declineReason": row.decline_reason if row.status == "declined" else None,
        "windowStart": iso_from_datetime(row.window_start),
        "windowEnd": iso_from_datetime(row.window_end),
        # A request's answer-by (it lapses then): what the owner is told.
        "expiresAt": iso_from_datetime(row.expires_at) if row.expires_at else None,
        # Times in what people are told read in the listing's zone.
        "timeZone": (row.listing_snapshot or {}).get("timeZone") or market_of_currency(row.currency).time_zone,
        # Where to go, only once it is agreed (V7-23; SHOWS_HANDOVER).
        "handover": {k: row.handover.get(k) for k in ("address", "postalCode")}
        if row.status == "accepted" and row.handover
        else None,
    }


def _owner_sees():
    """An owner hears of a booking once the card is held (FL-15): not while it
    awaits payment, nor when its payment failed before they ever saw it. A
    capture declined after they accepted they do see."""
    failed_after_accept = exists().where(
        TransitionRow.booking_id == BookingRow.id,
        TransitionRow.from_status == "accepted",
        TransitionRow.to_status == "payment_failed",
    )
    return and_(
        BookingRow.status != "awaiting_payment",
        or_(BookingRow.status != "payment_failed", failed_after_accept),
    )


class BookingRepository:
    def __init__(self, session: AsyncSession, outbox: Outbox) -> None:
        self.s = session
        self.outbox = outbox

    async def get(self, booking_id: str, *, lock: bool = False) -> BookingRow:
        row = await self.s.get(BookingRow, booking_id, with_for_update=lock)
        if not row:
            raise NotFound(f"booking {booking_id} not found")
        return row

    async def visible(self, booking_id: str, viewer: str, *, lock: bool = False) -> BookingRow:
        """A booking only its two parties can see. To anyone else it does not exist."""
        row = await self.s.get(BookingRow, booking_id, with_for_update=lock)
        if not row or viewer not in (row.requester_id, row.owner_id):
            raise NotFound(f"booking {booking_id} not found")
        if viewer == row.owner_id and viewer != row.requester_id:
            seen = (await self.s.execute(select(BookingRow.id).where(BookingRow.id == row.id, _owner_sees()))).first()
            if seen is None:
                raise NotFound(f"booking {booking_id} not found")
        return row

    async def by_idempotency_key(self, requester_id: str, key: str) -> BookingRow | None:
        q = select(BookingRow).where(BookingRow.requester_id == requester_id, BookingRow.idempotency_key == key)
        return (await self.s.execute(q)).scalar_one_or_none()

    async def pending_of_requester(self, requester_id: str) -> list[BookingRow]:
        q = (
            select(BookingRow)
            .where(BookingRow.requester_id == requester_id, BookingRow.status.in_(("awaiting_payment", "requested")))
            .with_for_update()
        )
        return list((await self.s.execute(q)).scalars())

    async def pending_for_listing(self, listing_id: str) -> list[BookingRow]:
        q = (
            select(BookingRow)
            .where(BookingRow.listing_id == listing_id, BookingRow.status.in_(("awaiting_payment", "requested")))
            .with_for_update()
        )
        return list((await self.s.execute(q)).scalars())

    async def requests_since(self, requester_id: str, since: datetime) -> int:
        q = select(func.count()).where(BookingRow.requester_id == requester_id, BookingRow.created_at >= since)
        return (await self.s.execute(q)).scalar_one()

    async def unpaid_count(self, requester_id: str) -> int:
        q = select(func.count()).where(BookingRow.requester_id == requester_id, BookingRow.status == "awaiting_payment")
        return (await self.s.execute(q)).scalar_one()

    async def lock_listing(self, listing_id: str) -> None:
        """Queue bookings of one listing behind each other for the rest of this
        transaction. Without it, many buyers racing for one window each wait
        on the others inside the exclusion constraint, and after the first
        commits the rest deadlock or time out (500s instead of a clean
        "taken"). Other listings are not affected."""
        if self.s.bind.dialect.name == "postgresql":
            await self.s.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": listing_id})

    async def window_taken(self, listing_id: str, start: datetime, end: datetime) -> bool:
        """The friendly check. The exclusion constraint is the one that holds
        under concurrency; this one only produces a nicer error first."""
        q = select(BookingRow.id).where(
            BookingRow.listing_id == listing_id,
            BookingRow.status.in_(HOLDING),
            BookingRow.window_start < end,
            start < BookingRow.window_end,
        )
        return (await self.s.execute(q.limit(1))).first() is not None

    async def insert(self, row: BookingRow) -> None:
        self.s.add(row)
        self.s.add(
            TransitionRow(
                booking_id=row.id, from_status=None, to_status=row.status, by=row.requester_id, at=row.created_at
            )
        )
        await self.s.flush()
        await self.outbox.add(self.s, BOOKING_STATUS_CHANGED, status_event(row, None, row.requester_id))

    async def move(self, row: BookingRow, to: str, by: str, now: datetime, **fields: object) -> None:
        before = row.status
        row.status = to
        row.updated_at = now
        for k, v in fields.items():
            setattr(row, k, v)
        self.s.add(TransitionRow(booking_id=row.id, from_status=before, to_status=to, by=by, at=now))
        await self.s.flush()
        await self.outbox.add(self.s, BOOKING_STATUS_CHANGED, status_event(row, before, by))
        # The owner cancelling, or not turning up; reporting the renter's
        # no-show is the owner doing their part.
        by_owner = by == row.owner_id and row.no_show != "renter"
        failed = before == "accepted" and to == "cancelled" and (by_owner or row.no_show == "owner")
        if before == "requested" and to in ("accepted", "declined", "expired"):
            await self.owner_responsiveness(row.owner_id, now)
        if to == "accepted" or failed:
            await self.owner_reliability(row.owner_id, now, failed=failed)

    async def owner_responsiveness(self, owner_id: str, now: datetime) -> None:
        """H-1: of the requests that reached an owner in 90 days and were
        answered or lapsed, the median minutes to answer and the share
        answered in time. A decline the system made (listing removed, owner
        suspended) is not the owner answering, and a request the renter
        withdrew never needed one: both are left out."""
        since = now - RESPONSE_WINDOW
        rows = (
            await self.s.execute(
                select(
                    TransitionRow.booking_id,
                    TransitionRow.from_status,
                    TransitionRow.to_status,
                    TransitionRow.by,
                    TransitionRow.at,
                )
                .join(BookingRow, TransitionRow.booking_id == BookingRow.id)
                .where(
                    BookingRow.owner_id == owner_id,
                    TransitionRow.at >= since - timedelta(days=2),
                    or_(TransitionRow.to_status == "requested", TransitionRow.from_status == "requested"),
                )
            )
        ).all()
        asked = {r.booking_id: r.at for r in rows if r.to_status == "requested"}
        answered, lapsed = [], 0
        for r in rows:
            if r.from_status != "requested" or r.at < since or r.booking_id not in asked:
                continue
            if r.to_status == "expired":
                lapsed += 1
            elif r.to_status in ("accepted", "declined") and r.by == owner_id:
                answered.append((r.at - asked[r.booking_id]).total_seconds() / 60)
        total = len(answered) + lapsed
        if total < RESPONSE_MIN_REQUESTS:
            mins = rate = None
        else:
            rate = round(len(answered) / total, 4)
            mins = round(statistics.median(answered)) if answered else None
        await self.outbox.add(
            self.s, OWNER_RELIABILITY, {"ownerId": owner_id, "responseMins": mins, "responseRate": rate}
        )

    async def owner_reliability(self, owner_id: str, now: datetime, *, failed: bool) -> None:
        """S-18: of the bookings an owner accepted in 12 months, the share they
        cancelled or did not show up for. Catalog shows it and ranking uses it;
        three in 30 days put the owner in front of staff."""
        since = now - RELIABILITY_WINDOW
        mine = and_(TransitionRow.booking_id == BookingRow.id, BookingRow.owner_id == owner_id)
        accepted = (
            await self.s.execute(
                select(func.count(func.distinct(TransitionRow.booking_id))).where(
                    mine, TransitionRow.to_status == "accepted", TransitionRow.at >= since
                )
            )
        ).scalar_one()
        misses = list(
            (
                await self.s.execute(
                    select(TransitionRow.at).where(
                        mine,
                        TransitionRow.from_status == "accepted",
                        TransitionRow.to_status == "cancelled",
                        TransitionRow.at >= since,
                        or_(
                            and_(TransitionRow.by == owner_id, BookingRow.no_show.is_distinct_from("renter")),
                            BookingRow.no_show == "owner",
                        ),
                    )
                )
            ).scalars()
        )
        rate = round(len(misses) / accepted, 4) if accepted >= RELIABILITY_MIN_BOOKINGS else None
        await self.outbox.add(
            self.s,
            OWNER_RELIABILITY,
            {"ownerId": owner_id, "rate": rate, "bookings": accepted, "failures": len(misses)},
        )
        recent = sum(1 for at in misses if at >= now - timedelta(days=30))
        if failed and recent >= 3:
            await self.outbox.add(
                self.s,
                PERSON_FLAGGED,
                {
                    "personId": owner_id,
                    "reason": "reliability",
                    "details": f"The owner cancelled or missed {recent} accepted bookings in the last 30 days.",
                },
            )

    async def busy(self, listing_ids: list[str], start: datetime, until: datetime) -> dict[str, list[tuple[str, str]]]:
        q = (
            select(BookingRow.listing_id, BookingRow.window_start, BookingRow.window_end)
            .where(
                BookingRow.listing_id.in_(listing_ids),
                BookingRow.status.in_(HOLDING),
                BookingRow.window_start < until,
                start < BookingRow.window_end,
            )
            .order_by(BookingRow.listing_id, BookingRow.window_start)
        )
        out: dict[str, list[tuple[str, str]]] = {}
        for lid, a, b in await self.s.execute(q):
            out.setdefault(lid, []).append((iso_from_datetime(a), iso_from_datetime(b)))
        return out

    async def page(
        self, viewer: str, role: str | None, *, cursor: str | None, limit: int
    ) -> tuple[list[BookingRow], str | None]:
        """Newest first. ``role`` narrows to what the viewer asked for
        (``requester``) or is being asked for (``owner``)."""
        mine = BookingRow.requester_id == viewer
        theirs = and_(BookingRow.owner_id == viewer, _owner_sees())
        if role == "requester":
            q = select(BookingRow).where(mine)
        elif role == "owner":
            q = select(BookingRow).where(theirs)
        else:
            q = select(BookingRow).where(or_(mine, theirs))
        key = decode_cursor(cursor)
        if key:
            at = dt_from_iso(key["at"])
            q = q.where(or_(BookingRow.created_at < at, and_(BookingRow.created_at == at, BookingRow.id < key["id"])))
        q = q.order_by(BookingRow.created_at.desc(), BookingRow.id.desc()).limit(limit + 1)
        rows = list((await self.s.execute(q)).scalars())
        more = len(rows) > limit
        rows = rows[:limit]
        nxt = encode_cursor({"at": rows[-1].created_at.isoformat(), "id": rows[-1].id}) if more else None
        return rows, nxt

    async def open_for(self, person: str) -> tuple[int, datetime | None]:
        """Bookings of this person, on either side, that are not settled yet,
        and when the last of them ends."""
        q = select(func.count(), func.max(BookingRow.window_end)).where(
            or_(BookingRow.requester_id == person, BookingRow.owner_id == person),
            BookingRow.status.in_(OPEN),
        )
        n, until = (await self.s.execute(q)).one()
        return n, until

    async def active_people(self, start: datetime, end: datetime) -> int:
        """Both parties of bookings made in [start, end), counted once each."""
        made = and_(BookingRow.created_at >= start, BookingRow.created_at < end)
        people = (
            select(BookingRow.requester_id.label("p"))
            .where(made)
            .union(select(BookingRow.owner_id.label("p")).where(made))
        )
        return (await self.s.execute(select(func.count()).select_from(people.subquery()))).scalar_one()

    async def card_linked_to_suspended(self, fingerprint: str, person: str) -> str | None:
        """Someone else, now suspended, who paid with this card (S-17)."""
        q = (
            select(BookingRow.requester_id)
            .join(SuspendedRow, SuspendedRow.person_id == BookingRow.requester_id)
            .where(BookingRow.card_fingerprint == fingerprint, BookingRow.requester_id != person)
            .limit(1)
        )
        return (await self.s.execute(q)).scalar_one_or_none()

    async def all_for(self, person: str, limit: int = 10_000) -> list[BookingRow]:
        """Everything, for a data export. ponytail: capped at 10k; stream it if anyone gets near."""
        q = (
            select(BookingRow)
            .where(or_(BookingRow.requester_id == person, BookingRow.owner_id == person))
            .order_by(BookingRow.created_at.desc())
            .limit(limit)
        )
        return list((await self.s.execute(q)).scalars())

    async def publish_reviews(self, row: BookingRow, now: datetime) -> None:
        """Blind reviews (Airbnb's rule): neither side sees the other's review
        before writing their own. Both go out together, once both are in or
        the 14-day window closes."""
        if row.reviews_published_at is not None:
            return
        row.reviews_published_at = now
        if row.outcome is not None:
            await self.outbox.add(
                self.s,
                BOOKING_RATED,
                {
                    "bookingId": row.id,
                    "ownerId": row.owner_id,
                    "listingId": row.listing_id,
                    "requesterId": row.requester_id,
                    "outcome": row.outcome,
                    # When it was written; a job finished early is not reviewed "in the future".
                    "at": iso_from_datetime(min(row.window_end, row.rated_at or now)),
                    "ratedAt": iso_from_datetime(row.rated_at or now),
                },
            )
        if row.renter_rating is not None:
            await self.outbox.add(
                self.s,
                RENTER_RATED,
                {
                    "bookingId": row.id,
                    "renterId": row.requester_id,
                    "ownerId": row.owner_id,
                    "quality": row.renter_rating,
                },
            )

    async def reviews_due(self, now: datetime, limit: int) -> list[BookingRow]:
        """Completed bookings whose review window closed with one review in."""
        q = (
            select(BookingRow)
            .where(
                BookingRow.status == "completed",
                BookingRow.reviews_published_at.is_(None),
                or_(BookingRow.outcome.is_not(None), BookingRow.renter_rating.is_not(None)),
                BookingRow.window_end < now - REVIEW_WINDOW,
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.s.execute(q)).scalars())

    # --- the sweeps. SKIP LOCKED: replicas share the work instead of repeating it.

    async def lapsed(self, now: datetime, limit: int) -> list[BookingRow]:
        q = (
            select(BookingRow)
            .where(BookingRow.status.in_(("awaiting_payment", "requested")), BookingRow.expires_at <= now)
            .order_by(BookingRow.expires_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.s.execute(q)).scalars())

    async def finished(self, now: datetime, grace: timedelta, limit: int) -> list[BookingRow]:
        q = (
            select(BookingRow)
            .where(BookingRow.status.in_(("accepted", "active")), BookingRow.window_end <= now - grace)
            .order_by(BookingRow.window_end)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return list((await self.s.execute(q)).scalars())
