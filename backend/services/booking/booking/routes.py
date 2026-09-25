"""Bookings: request (and pay), answer, hand over, complete, rate.

Creating a booking crosses two services, so it is not one transaction:

1. matching prices the chosen window (never trusted from the client) and
   confirms it is free;
2. the booking is inserted as ``awaiting_payment`` and committed. From here
   the window is held: the exclusion constraint refuses any overlapping one;
3. payments creates the PaymentIntent that will authorise the price. If that
   call fails the booking becomes ``payment_failed`` and the window is free.

The owner only sees the request once the card is authorised
(``payment.authorised`` moves it to ``requested``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, Query, Request, status
from pydantic import Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_internal, require_principal
from cappy_common.errors import ApiError, Conflict, Invalid, NotFound, Unavailable
from cappy_common.events import BOOKING_RATED
from cappy_common.ids import new_id
from cappy_common.models import Booking, CamelModel, Iso, Outcome, Requirement
from cappy_common.pagination import Page, clamp_limit
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .clients import PaymentStart
from .repository import BookingRepository, to_booking
from .settings import Settings
from .state import Action, check_can_rate, next_status
from .tables import BookingRow

log = logging.getLogger(__name__)
router = ApiRouter()
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])


def _now() -> datetime:
    return datetime.now(UTC)


def get_repo(request: Request, session: AsyncSession = Tx) -> BookingRepository:
    return BookingRepository(session, request.app.state.outbox)


class CreateBookingIn(CamelModel):
    requirement: Requirement
    listing_id: str = Field(max_length=40)
    slot_id: str = Field(max_length=40)
    start: Iso
    end: Iso


class BookingCreated(CamelModel):
    booking: Booking
    # Absent when there is nothing (left) to pay: a retried request whose
    # payment already failed, say.
    payment: PaymentStart | None = None


class DeclineIn(CamelModel):
    reason: str = Field(min_length=1, max_length=500)


class BusyIn(CamelModel):
    listing_ids: list[str] = Field(max_length=500)
    start: Iso
    until: Iso


# --- reading ---------------------------------------------------------------------------


@router.get("/bookings", response_model=Page[Booking])
async def list_bookings(
    role: str | None = Query(default=None, pattern="^(requester|owner)$"),
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Page[Booking]:
    """What the caller asked for (``role=requester``), is being asked for
    (``role=owner``), or both, newest first."""
    rows, nxt = await repo.page(p.sub, role, cursor=cursor, limit=clamp_limit(limit))
    return Page(items=[to_booking(r, p.sub) for r in rows], next_cursor=nxt)


@router.get("/bookings/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: str, repo: BookingRepository = Depends(get_repo), p: Principal = Depends(require_principal)
) -> Booking:
    return to_booking(await repo.visible(booking_id, p.sub), p.sub)


# --- creating --------------------------------------------------------------------------


@router.post("/bookings", response_model=BookingCreated, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: CreateBookingIn,
    request: Request,
    p: Principal = Depends(require_principal),
    idempotency_key: str | None = Header(default=None, max_length=80),
) -> BookingCreated:
    """Send the same ``Idempotency-Key`` when retrying: a retry returns the
    booking the first attempt made, rather than a second booking."""
    app = request.app
    db, outbox = app.state.db, app.state.outbox
    settings: Settings = app.state.settings

    if idempotency_key:
        async with db.session() as s:
            existing = await BookingRepository(s, outbox).by_idempotency_key(p.sub, idempotency_key)
        if existing:
            return await _with_payment(request, existing, p.sub)

    view = await app.state.matching.match_for_offer(
        body.requirement.model_dump(mode="json", by_alias=True), body.listing_id, body.slot_id, body.start, body.end
    )
    if view.owner.id == p.sub:
        raise Invalid("you cannot book your own listing")

    now = _now()
    m = view.match
    row = BookingRow(
        id=new_id("bk"),
        requester_id=p.sub,
        owner_id=m.owner_id,
        listing_id=m.listing_id,
        status="awaiting_payment",
        window_start=dt_from_iso(m.start),
        window_end=dt_from_iso(m.end),
        created_at=now,
        updated_at=now,
        expires_at=now + settings.payment_timeout,
        amount=m.quote.total,
        currency="eur",
        requirement=body.requirement.model_dump(mode="json", by_alias=True),
        match=m.model_dump(mode="json", by_alias=True),
        listing_snapshot={
            "title": view.listing.title,
            "district": view.listing.district,
            "category": view.listing.category,
            "ownerName": view.owner.name,
            **({"photo": view.listing.photos[0]} if view.listing.photos else {}),
        },
        idempotency_key=idempotency_key,
    )
    try:
        async with db.transaction() as s:
            repo = BookingRepository(s, outbox)
            if await repo.window_taken(row.listing_id, row.window_start, row.window_end):
                raise Conflict("that window was just taken; pick another")
            await repo.insert(row)
    except IntegrityError:
        # Either the same key raced itself (return what it made) or the
        # exclusion constraint caught a concurrent booking of the window.
        if idempotency_key:
            async with db.session() as s:
                existing = await BookingRepository(s, outbox).by_idempotency_key(p.sub, idempotency_key)
            if existing:
                return await _with_payment(request, existing, p.sub)
        raise Conflict("that window was just taken; pick another") from None
    app.state.relay.wake()
    return await _with_payment(request, row, p.sub)


async def _payments_start(request: Request, row: BookingRow) -> PaymentStart:
    return await request.app.state.payments.start(
        booking_id=row.id,
        requester_id=row.requester_id,
        owner_id=row.owner_id,
        amount=row.amount,
        owner_net=row.match["quote"]["ownerNet"],
        currency=row.currency,
    )


async def _with_payment(request: Request, row: BookingRow, viewer: str) -> BookingCreated:
    app = request.app
    if row.status != "awaiting_payment":
        return BookingCreated(booking=to_booking(row, viewer))
    try:
        payment = await _payments_start(request, row)
    except ApiError as e:
        if e.status >= 500:
            # Payments may have made the intent before failing to answer. Keep
            # the booking: a retry gets the same intent, and if nobody pays the
            # expiry sweep releases the window.
            log.warning("payments unavailable for %s: %s", row.id, e)
            raise Unavailable("we could not start the payment, and you have not been charged; try again") from e
        # A definite refusal (the owner cannot be paid yet, say): release the window.
        async with app.state.db.transaction() as s:
            repo = BookingRepository(s, app.state.outbox)
            fresh = await repo.get(row.id, lock=True)
            if fresh.status == "awaiting_payment":
                await repo.move(fresh, "payment_failed", "system", _now(), expires_at=None)
        app.state.relay.wake()
        raise
    return BookingCreated(booking=to_booking(row, viewer), payment=payment)


# --- people moving a booking along ---------------------------------------------------------


async def _transition(
    request: Request, repo: BookingRepository, booking_id: str, action: Action, user: str, **fields: object
) -> Booking:
    row = await repo.visible(booking_id, user, lock=True)
    now = _now()
    if row.expires_at is not None and row.expires_at <= now:
        # The sweep has not got to it yet, but it has lapsed all the same.
        raise Conflict("this request has lapsed")
    to = next_status(action, row.status, user, row.requester_id, row.owner_id)
    started = now >= row.window_start
    if action == "cancel" and started:
        # Once the window has begun the machine may already be in use: a full
        # refund is no longer automatic. The buyer reports a problem instead.
        raise Conflict("the booked time has started; report a problem instead of cancelling")
    if action == "dispute" and not started:
        raise Conflict("nothing to report before the booked time; cancel instead")
    early = timedelta(minutes=request.app.state.settings.start_early_minutes)
    if action == "start" and now < row.window_start - early:
        raise Conflict("the hand-over can be marked from 30 minutes before the booked time")
    if to not in ("awaiting_payment", "requested"):
        fields["expires_at"] = None
    await repo.move(row, to, user, now, **fields)
    return to_booking(row, user)


class DisputeIn(CamelModel):
    reason: str = Field(min_length=1, max_length=500)


Repo = Depends(get_repo)
Me = Depends(require_principal)


@router.post("/bookings/{booking_id}/accept", response_model=Booking)
async def accept(booking_id: str, request: Request, repo: BookingRepository = Repo, p: Principal = Me):
    return await _transition(request, repo, booking_id, "accept", p.sub)


@router.post("/bookings/{booking_id}/decline", response_model=Booking)
async def decline(
    booking_id: str, body: DeclineIn, request: Request, repo: BookingRepository = Repo, p: Principal = Me
):
    reason = body.reason.strip()
    if not reason:
        raise Invalid("tell the buyer why, rather than just refusing")
    return await _transition(request, repo, booking_id, "decline", p.sub, decline_reason=reason)


@router.post("/bookings/{booking_id}/start", response_model=Booking)
async def start(booking_id: str, request: Request, repo: BookingRepository = Repo, p: Principal = Me):
    return await _transition(request, repo, booking_id, "start", p.sub)


@router.post("/bookings/{booking_id}/complete", response_model=Booking)
async def complete(booking_id: str, request: Request, repo: BookingRepository = Repo, p: Principal = Me):
    return await _transition(request, repo, booking_id, "complete", p.sub)


@router.post("/bookings/{booking_id}/cancel", response_model=Booking)
async def cancel(booking_id: str, request: Request, repo: BookingRepository = Repo, p: Principal = Me):
    return await _transition(request, repo, booking_id, "cancel", p.sub)


@router.post("/bookings/{booking_id}/dispute", response_model=Booking)
async def dispute(
    booking_id: str, body: DisputeIn, request: Request, repo: BookingRepository = Repo, p: Principal = Me
):
    """Something went wrong once the booked time began. The payout is held
    and the booking no longer completes by itself; support resolves it."""
    reason = body.reason.strip()
    if not reason:
        raise Invalid("say what went wrong")
    return await _transition(request, repo, booking_id, "dispute", p.sub, decline_reason=reason)


@router.get("/bookings/{booking_id}/payment", response_model=PaymentStart)
async def payment(booking_id: str, request: Request, p: Principal = Me) -> PaymentStart:
    """The card step again, for a buyer who left it half way. Payments returns
    the same intent however often it is asked."""
    async with request.app.state.db.session() as s:
        row = await BookingRepository(s, request.app.state.outbox).visible(booking_id, p.sub)
    if row.requester_id != p.sub or row.status != "awaiting_payment":
        raise NotFound("there is nothing to pay for this booking")
    return await _payments_start(request, row)


@router.post("/bookings/{booking_id}/rate", response_model=Booking)
async def rate(
    booking_id: str,
    outcome: Outcome,
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Booking:
    """``booking.rated`` feeds the owner's record and becomes a review. It is
    dated at the end of the booked window, not when the buyer got round to it."""
    row = await repo.visible(booking_id, p.sub, lock=True)
    check_can_rate(row.status, row.outcome is not None, p.sub, row.requester_id)
    row.outcome = outcome.model_dump(mode="json", by_alias=True, exclude_none=True)
    row.updated_at = _now()
    await repo.s.flush()
    await repo.outbox.add(
        repo.s,
        BOOKING_RATED,
        {
            "bookingId": row.id,
            "ownerId": row.owner_id,
            "listingId": row.listing_id,
            "requesterId": row.requester_id,
            "outcome": row.outcome,
            "at": iso_from_datetime(row.window_end),
            "ratedAt": iso_from_datetime(row.updated_at),
        },
    )
    return to_booking(row, p.sub)


# --- internal: matching asks what is already taken -------------------------------------------


class ResolveIn(CamelModel):
    outcome: str = Field(pattern="^(pay_owner|refund_buyer)$")
    by: str = Field(min_length=1, max_length=64, description="who at support decided")


@internal.post("/bookings/{booking_id}/resolve", response_model=Booking)
async def resolve(booking_id: str, body: ResolveIn, repo: BookingRepository = Depends(get_repo)) -> Booking:
    """Support settles a dispute (docs/runbook.md). Paying the owner completes
    the booking (payments transfers); refunding cancels it (payments refunds)."""
    row = await repo.get(booking_id, lock=True)
    if row.status != "disputed":
        raise Conflict(f"only a disputed booking can be resolved; this one is {row.status}")
    to = "completed" if body.outcome == "pay_owner" else "cancelled"
    await repo.move(row, to, f"support:{body.by}", _now())
    return to_booking(row, row.owner_id)


class OpenBookings(CamelModel):
    open: int


@internal.get("/people/{person}/open", response_model=OpenBookings)
async def open_bookings(person: str, repo: BookingRepository = Depends(get_repo)) -> OpenBookings:
    """Before an account is deleted: is anything still in flight for them?"""
    return OpenBookings(open=await repo.open_for(person))


@internal.get("/people/{person}/bookings", response_model=list[Booking])
async def bookings_of(person: str, repo: BookingRepository = Depends(get_repo)) -> list[Booking]:
    """Every booking they were part of, for their data export."""
    return [to_booking(r, person) for r in await repo.all_for(person)]


@internal.post("/busy", response_model=dict[str, list[tuple[Iso, Iso]]])
async def busy(body: BusyIn, repo: BookingRepository = Depends(get_repo)) -> dict[str, list[tuple[str, str]]]:
    if not body.listing_ids:
        return {}
    return await repo.busy(body.listing_ids, dt_from_iso(body.start), dt_from_iso(body.until))
