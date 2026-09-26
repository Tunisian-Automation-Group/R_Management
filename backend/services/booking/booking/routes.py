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

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, Query, Request, status
from pydantic import Field
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_internal, require_principal
from cappy_common.errors import ApiError, Conflict, Forbidden, Invalid, NotFound, RateLimited, Unavailable
from cappy_common.idempotency import IdempotencyKey, fingerprint, remember, replayed
from cappy_common.ids import new_id
from cappy_common.markets import market
from cappy_common.models import Booking, CamelModel, Iso, Outcome, Requirement
from cappy_common.pagination import Page, clamp_limit
from cappy_common.runtime import ReadTx, Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .cancellation import refund_amount
from .clients import PaymentStart
from .messages import blocked_between
from .repository import REVIEW_WINDOW, SHOWS_HANDOVER, BookingRepository, to_booking
from .settings import Settings
from .state import Action, check_can_rate, next_status
from .tables import IDEMPOTENCY, BookingRow, SuspendedRow, VerifiedRow

log = logging.getLogger(__name__)
# S-11: how long after the start a no-show can be reported, and the renter's grace.
NO_SHOW_REPORTABLE = timedelta(hours=2)
NO_SHOW_GRACE = timedelta(minutes=30)
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
    booking_id: str,
    request: Request,
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> Booking:
    row = await repo.visible(booking_id, p.sub)
    # While the booking is still to happen, the hand-over is read live, so an
    # address the owner adds or corrects after accepting reaches the renter
    # (V4-9). Once it is over, the last copy stands (it is what was used).
    if row.status in SHOWS_HANDOVER and (row.handover is None or row.status in LIVE_HANDOVER):
        try:
            row.handover = await request.app.state.catalog.handover(row.listing_id)
        except Exception as e:  # noqa: BLE001 - the booking still shows, with the last copy if any
            log.warning("no hand-over details for %s yet: %s", row.id, e)
    return to_booking(row, p.sub)


LIVE_HANDOVER = frozenset({"accepted", "active"})


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
    return await create(request, p.sub, body, idempotency_key)


async def create(
    request: Request, sub: str, body: CreateBookingIn, idempotency_key: str | None, *, extends: str | None = None
) -> BookingCreated:
    """A new booking, whichever way it is asked for. ``extends``: the booking
    this one continues, for the same renter (S-12)."""
    p = Principal(sub=sub)
    app = request.app
    db, outbox = app.state.db, app.state.outbox
    settings: Settings = app.state.settings

    if not settings.accepting_bookings:
        raise Unavailable("new bookings are paused for a moment; please try again later")
    fingerprint = hashlib.sha256(body.model_dump_json(by_alias=True).encode()).hexdigest()
    if idempotency_key:
        async with db.session() as s:
            existing = await BookingRepository(s, outbox).by_idempotency_key(p.sub, idempotency_key)
        if existing:
            return await _replay(request, existing, fingerprint, p.sub)
    async with db.session() as s:
        repo = BookingRepository(s, outbox)
        if await repo.unpaid_count(p.sub) >= settings.max_unpaid:
            raise RateLimited("finish paying for the bookings you have started first")
        if await repo.requests_since(p.sub, _now() - timedelta(days=1)) >= settings.max_requests_per_day:
            raise RateLimited("that is a lot of booking requests for one day; try again tomorrow")

    view = await app.state.matching.match_for_offer(
        body.requirement.model_dump(mode="json", by_alias=True),
        body.listing_id,
        body.slot_id,
        body.start,
        body.end,
        **({"extension": True} if extends else {}),
    )
    if view.owner.id == p.sub:
        raise Invalid("you cannot book your own listing")
    async with db.session() as s:
        if await blocked_between(s, p.sub, view.owner.id):
            raise Forbidden("this listing is not available to you")
        if await s.get(SuspendedRow, p.sub) is not None:
            raise Forbidden("your account is suspended; see the email we sent you")
        needs_id = view.listing.category in {c for c in settings.verify_categories.split(",") if c} or (
            view.match.quote.total > market(view.owner.country).id_check_above
        )
        if needs_id and await s.get(VerifiedRow, p.sub) is None:
            raise Forbidden("verify your identity once before booking this", code="verification_required")

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
        # The listing's currency, ISO 4217 uppercase like every answer (M-3):
        # never converted. Only the Stripe calls lowercase it.
        currency=view.listing.currency,
        requirement=body.requirement.model_dump(mode="json", by_alias=True),
        match=m.model_dump(mode="json", by_alias=True),
        listing_snapshot={
            "title": view.listing.title,
            "district": view.listing.district,
            "category": view.listing.category,
            "ownerName": view.owner.name,
            # A trader's identity, for the fee invoice (§ 14 UStG) and the renter.
            **({"ownerBusiness": view.owner.business.model_dump(by_alias=True)} if view.owner.business else {}),
            "instantBook": view.listing.instant_book,
            # The listing's own zone (its weekly hours), else its market's main one.
            "timeZone": (view.listing.availability.time_zone if view.listing.availability else None)
            or market(view.owner.country).time_zone,
            "cancellationPolicy": view.listing.cancellation_policy,
            **({"photo": view.listing.photos[0]} if view.listing.photos else {}),
        },
        idempotency_key=idempotency_key,
        request_hash=fingerprint,
        extends_id=extends,
    )
    try:
        async with db.transaction() as s:
            repo = BookingRepository(s, outbox)
            await repo.lock_listing(row.listing_id)
            if await repo.window_taken(row.listing_id, row.window_start, row.window_end):
                raise Conflict("that window was just taken; pick another")
            await repo.insert(row)
    except DBAPIError as e:
        if not isinstance(e, IntegrityError) and not _contention(e):
            raise
        # Either the same key raced itself (return what it made) or the
        # exclusion constraint caught a concurrent booking of the window.
        if idempotency_key:
            async with db.session() as s:
                existing = await BookingRepository(s, outbox).by_idempotency_key(p.sub, idempotency_key)
            if existing:
                return await _replay(request, existing, fingerprint, p.sub)
        raise Conflict("that window was just taken; pick another") from None
    app.state.relay.wake()
    return await _with_payment(request, row, p.sub)


def _contention(e: DBAPIError) -> bool:
    """A deadlock or lock timeout between racing bookings: the window was
    contested, so the answer is "taken", never a 500."""
    code = getattr(getattr(e, "orig", None), "sqlstate", None) or getattr(getattr(e, "orig", None), "pgcode", None)
    name = type(getattr(e, "orig", e)).__name__
    return code in ("40P01", "55P03", "57014") or "Deadlock" in name or "QueryCanceled" in name


def _charged(row: BookingRow) -> bool:
    """The card is charged at accept; before that there is only a hold."""
    return row.status in ("accepted", "active")


def _refund(request: Request, row: BookingRow, user: str, now: datetime) -> int:
    policy = (row.listing_snapshot or {}).get("cancellationPolicy", "flexible")
    if not request.app.state.settings.paid_cancellation_policies:
        policy = "flexible"
    return refund_amount(
        policy,
        row.amount,
        charged=_charged(row),
        by_owner=user == row.owner_id,
        now=now,
        window_start=row.window_start,
    )


async def _replay(request: Request, row: BookingRow, fingerprint: str, viewer: str) -> BookingCreated:
    if row.request_hash and row.request_hash != fingerprint:
        raise Invalid("that Idempotency-Key was already used for a different booking request")
    return await _with_payment(request, row, viewer)


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
    # Handed over early (V4-3): whoever holds the thing now can report what
    # they found at once. A cancel stays closed from `active` on purpose: the
    # renter has the item, so a refund must not happen without staff; the
    # dispute holds the payout until they decide, which is the safe side.
    if action == "dispute" and not started and row.status != "active":
        raise Conflict("nothing to report before the booked time; cancel instead")
    early = timedelta(minutes=request.app.state.settings.start_early_minutes)
    if action == "start" and now < row.window_start - early:  # the same rule as Booking.canStartFrom
        raise Conflict("the hand-over can be marked from 30 minutes before the booked time")
    if action == "no_show":
        missing = "owner" if user == row.requester_id else "renter"
        # A renter running late gets half an hour before the owner may give up.
        opens = row.window_start + (NO_SHOW_GRACE if missing == "renter" else timedelta(0))
        if not opens <= now <= row.window_start + NO_SHOW_REPORTABLE:
            raise Conflict(
                "a no-show can be reported from the booked time"
                + (" plus 30 minutes" if missing == "renter" else "")
                + " until 2 hours after it starts"
            )
        # The owner not turning up refunds everything; the renter not turning
        # up is a cancellation too late for any policy: nothing back (S-11).
        fields["no_show"] = missing
        fields["refund_amount"] = row.amount if missing == "owner" else 0
    if to not in ("awaiting_payment", "requested"):
        fields["expires_at"] = None
    if to == "cancelled" and "refund_amount" not in fields and _charged(row):
        # Nothing charged yet (a request, awaiting payment): no refund to show.
        fields["refund_amount"] = _refund(request, row, user, now)
    await repo.move(row, to, user, now, **fields)
    if to == "disputed":
        # S-21: the two sides get 72 hours to settle it between them first.
        from .tables import DisputeRow

        reason = str(fields.get("decline_reason") or "")
        window = request.app.state.settings.dispute_offer_window
        repo.s.add(DisputeRow(booking_id=row.id, by=user, reason=reason, opened_at=now, respond_by=now + window))
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


@router.post("/bookings/{booking_id}/no-show", response_model=Booking)
async def no_show(booking_id: str, request: Request, repo: BookingRepository = Repo, p: Principal = Me):
    """The other side never came. Either side reports it about the other, in
    the first 2 hours of the booked time, while nobody marked the hand-over."""
    return await _transition(request, repo, booking_id, "no_show", p.sub)


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
    request: Request,
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
    key: str | None = IdempotencyKey,
) -> Booking:
    """``booking.rated`` feeds the owner's record and becomes a review. It is
    dated at the end of the booked window, not when the buyer got round to it."""
    fp = fingerprint(request, outcome)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    row = await repo.visible(booking_id, p.sub, lock=True)
    check_can_rate(row.status, row.outcome is not None, p.sub, row.requester_id)
    now = _now()
    if now > row.window_end + REVIEW_WINDOW:
        raise Conflict("reviews close 14 days after the booked time")
    row.outcome = outcome.model_dump(mode="json", by_alias=True, exclude_none=True)
    row.rated_at = row.updated_at = now
    await repo.s.flush()
    if row.renter_rating is not None:
        await repo.publish_reviews(row, now)
    answer = to_booking(row, p.sub)
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


class RenterRatingIn(CamelModel):
    quality: int = Field(ge=1, le=5)


class CancellationQuote(CamelModel):
    refund_amount: int
    currency: str
    policy: str
    # False: nothing was charged yet; cancelling releases the card hold (FL-8).
    charged: bool


@router.get("/bookings/{booking_id}/cancellation", response_model=CancellationQuote)
async def cancellation_quote(
    booking_id: str,
    request: Request,
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
) -> CancellationQuote:
    """What cancelling now would refund, shown before anyone confirms."""
    row = await repo.visible(booking_id, p.sub)
    policy = (row.listing_snapshot or {}).get("cancellationPolicy", "flexible")
    if not request.app.state.settings.paid_cancellation_policies:
        policy = "flexible"
    return CancellationQuote(
        refund_amount=_refund(request, row, p.sub, _now()), currency=row.currency, policy=policy, charged=_charged(row)
    )


@router.post("/bookings/{booking_id}/rate-renter", response_model=Booking)
async def rate_renter(
    booking_id: str,
    body: RenterRatingIn,
    request: Request,
    repo: BookingRepository = Depends(get_repo),
    p: Principal = Depends(require_principal),
    key: str | None = IdempotencyKey,
) -> Booking:
    """Two-way reviews: the owner rates the renter after a completed booking,
    once. Builds the renter's record other owners see before accepting."""
    fp = fingerprint(request, body)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    row = await repo.visible(booking_id, p.sub, lock=True)
    if p.sub != row.owner_id:
        raise Forbidden("only the owner can rate the renter")
    if row.status != "completed":
        raise Conflict("a renter can be rated once the booking is completed")
    if row.renter_rating is not None:
        raise Conflict("you already rated this renter")
    now = _now()
    if now > row.window_end + REVIEW_WINDOW:
        raise Conflict("reviews close 14 days after the booked time")
    row.renter_rating = body.quality
    row.updated_at = now
    await repo.s.flush()
    if row.outcome is not None:
        await repo.publish_reviews(row, now)
    answer = to_booking(row, p.sub)
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


class OpenBookings(CamelModel):
    open: int
    # When the last open booking's window ends.
    until: Iso | None = None


class MessageAuthor(CamelModel):
    sender_id: str


@internal.get("/messages/{message_id}", response_model=MessageAuthor)
async def message_author(message_id: str, repo: BookingRepository = Depends(get_repo)) -> MessageAuthor:
    """Who wrote a reported message (catalog's moderation, FL-7)."""
    from .tables import MessageRow

    row = await repo.s.get(MessageRow, message_id)
    if row is None:
        raise NotFound(f"message {message_id} not found")
    return MessageAuthor(sender_id=row.sender_id)


@internal.post("/messages/{message_id}/remove", status_code=204)
async def remove_message(message_id: str, repo: BookingRepository = Depends(get_repo)) -> None:
    """A moderation decision: the words go, the conversation keeps its shape."""
    from .tables import MessageRow

    row = await repo.s.get(MessageRow, message_id, with_for_update=True)
    if row is None:
        raise NotFound(f"message {message_id} not found")
    row.body, row.unmasked = "[removed by Cappy: it broke our rules]", None


@internal.get("/people/{person}/open", response_model=OpenBookings)
async def open_bookings(person: str, repo: BookingRepository = Depends(get_repo)) -> OpenBookings:
    """Before an account is deleted: is anything still in flight for them?"""
    n, until = await repo.open_for(person)
    return OpenBookings(open=n, until=iso_from_datetime(until) if until else None)


class ActivePeople(CamelModel):
    people: int


@internal.get("/stats/active-people", response_model=ActivePeople)
async def active_people(
    since: str = Query(alias="from"), until: str = Query(), repo: BookingRepository = Depends(get_repo)
) -> ActivePeople:
    """For the DSA transparency numbers (catalog's /admin/dsa-stats)."""
    return ActivePeople(people=await repo.active_people(dt_from_iso(since), dt_from_iso(until)))


class PersonExport(CamelModel):
    bookings: list[Booking]
    messages_sent: list[dict]
    evidence: list[dict]
    # Who they blocked, and what booking holds as flags about them (D-10).
    blocked: list[str]
    identity_verified: bool
    suspended: bool
    card_fingerprints: list[str]
    # Disputes they opened and claims they made (S-12, S-21).
    disputes: list[dict] = []
    claims: list[dict] = []


@internal.get("/people/{person}/export", response_model=PersonExport)
async def export_person(person: str, request: Request, repo: BookingRepository = Depends(get_repo)) -> PersonExport:
    """Everything booking holds about them (GDPR art. 15/20). Hand-over photos
    come as links signed for a day, so the file can be saved from them."""
    from sqlalchemy import select

    from .messages import EXPORT_LINK_TTL, _link
    from .tables import EvidenceRow, MessageRow

    s = repo.s
    msgs = (
        await s.execute(select(MessageRow).where(MessageRow.sender_id == person).order_by(MessageRow.at).limit(10_000))
    ).scalars()
    ev = (
        await s.execute(select(EvidenceRow).where(EvidenceRow.by == person).order_by(EvidenceRow.at).limit(10_000))
    ).scalars()
    from .tables import BlockRow, SuspendedRow, VerifiedRow

    rows = await repo.all_for(person)
    blocked = (await s.execute(select(BlockRow.blocked_id).where(BlockRow.blocker_id == person))).scalars()
    from .tables import ClaimRow, DisputeRow

    disputes = (await s.execute(select(DisputeRow).where(DisputeRow.by == person))).scalars()
    claims = (await s.execute(select(ClaimRow).where(ClaimRow.by == person))).scalars()
    return PersonExport(
        disputes=[
            {
                "bookingId": d.booking_id,
                "reason": d.reason,
                "openedAt": iso_from_datetime(d.opened_at),
                "offerAmount": d.offer_amount if d.offer_by == person else None,
            }
            for d in disputes
        ],
        claims=[
            {
                "bookingId": c.booking_id,
                "kind": c.kind,
                "minutesLate": c.minutes_late,
                "amount": c.amount,
                "currency": c.currency,
                "note": c.note,
                "status": c.status,
                "at": iso_from_datetime(c.created_at),
            }
            for c in claims
        ],
        bookings=[to_booking(r, person) for r in rows],
        blocked=list(blocked),
        identity_verified=await s.get(VerifiedRow, person) is not None,
        suspended=await s.get(SuspendedRow, person) is not None,
        card_fingerprints=sorted({r.card_fingerprint for r in rows if r.card_fingerprint and r.requester_id == person}),
        messages_sent=[
            {"bookingId": m.booking_id, "body": m.unmasked or m.body, "at": iso_from_datetime(m.at)} for m in msgs
        ],
        evidence=[
            {
                "bookingId": e.booking_id,
                "stage": e.stage,
                "photos": [
                    _link(request, e.booking_id, e.id, i, photo, EXPORT_LINK_TTL) for i, photo in enumerate(e.photos)
                ],
                "note": e.note,
                "at": iso_from_datetime(e.at),
            }
            for e in ev
        ],
    )


@internal.post("/busy", response_model=dict[str, list[tuple[Iso, Iso]]])
async def busy(body: BusyIn, request: Request, session: AsyncSession = ReadTx) -> dict[str, list[tuple[str, str]]]:
    """From the reader: a window booked a moment ago may still show as free,
    in which case the booking itself is refused by the constraint."""
    repo = BookingRepository(session, request.app.state.outbox)
    if not body.listing_ids:
        return {}
    return await repo.busy(body.listing_ids, dt_from_iso(body.start), dt_from_iso(body.until))
