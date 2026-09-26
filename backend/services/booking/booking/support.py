"""Settling what went wrong, and the tools staff use for it.

- Disputes between the two sides (S-21): either side offers a refund amount,
  the other accepts it and the dispute is settled without staff. Each offer
  gives the other side 72 hours; a deadline passing with no agreement sends
  the dispute to staff (``escalatedAt``).
- Staff resolutions (H-6): pay the owner, refund the renter, or a partial
  refund, with a reason. A refund above the staff member's limit (per market
  and role, markets.json) waits for a second staff member (four eyes).
- The case view (H-9): one answer with everything about a booking.
- Owners' late-return claims and renters' extensions (S-12).

Every staff action, and every staff read of a case or evidence, is announced
as ``staff.action``; catalog keeps the one append-only audit log (H-7).

How money moves: a settlement is a status change payments already acts on.
Refunding everything cancels the booking (a full refund); anything less
completes it with ``refundAmount`` set, and payments refunds that part and
pays the owner their share of the rest.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Depends, Header, Query, Request
from pydantic import Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_admin, require_internal, require_principal, staff_role
from cappy_common.errors import Conflict, Forbidden, Invalid, NotFound
from cappy_common.events import DISPUTE_OFFER, STAFF_ACTION, Outbox
from cappy_common.idempotency import IdempotencyKey, fingerprint, remember, replayed
from cappy_common.ids import new_id
from cappy_common.markets import market_of_currency
from cappy_common.models import Booking, CamelModel, Iso
from cappy_common.observability import request_id
from cappy_common.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .repository import BookingRepository, to_booking
from .tables import IDEMPOTENCY, BookingRow, ClaimRow, DisputeRow, MessageRow, ResolutionRow, TransitionRow

OFFER_WINDOW = timedelta(hours=72)
# S-12: a late return is reported within a day of the end; the first half
# hour is grace; the fee on top is one hour at the listing's rate, capped.
CLAIM_WITHIN = timedelta(hours=24)
LATE_GRACE_MINUTES = 30
REASONS = "damage|no_show|not_as_described|late_return|cleanliness|safety|goodwill|agreement|other"

router = ApiRouter()
admin = ApiRouter(prefix="/admin")
internal = ApiRouter(prefix="/internal", dependencies=[Depends(require_internal)])


def _now() -> datetime:
    return datetime.now(UTC)


def _repo(request: Request, session: AsyncSession = Tx) -> BookingRepository:
    return BookingRepository(session, request.app.state.outbox)


async def audit(
    session: AsyncSession,
    outbox: Outbox,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    person: str | None = None,
) -> None:
    """One line of the staff audit log (catalog stores it, H-7)."""
    await outbox.add(
        session,
        STAFF_ACTION,
        {
            "actorId": actor,
            "action": action,
            "targetType": target_type,
            "targetId": target_id,
            "personId": person,
            "reason": (reason or action)[:2000],
            "requestId": request_id.get(),
            "service": "booking",
            "at": iso_from_datetime(_now()),
        },
    )


# --- shapes -----------------------------------------------------------------------------


class Offer(CamelModel):
    refund_amount: int
    by: str
    at: Iso


class Dispute(CamelModel):
    booking_id: str
    opened_by: str
    reason: str
    opened_at: Iso
    # When whoever has to answer the offer on the table (or make one) must
    # have done so; after it, staff take over.
    respond_by: Iso
    escalated_at: Iso | None = None
    offer: Offer | None = None
    currency: str
    amount: int


class Resolution(CamelModel):
    id: str
    booking_id: str
    outcome: str
    refund_amount: int
    currency: str
    reason_code: str
    note: str
    by: str
    role: str
    status: Literal["pending_approval", "done", "rejected"]
    approved_by: str | None = None
    created_at: Iso
    decided_at: Iso | None = None


class Settled(CamelModel):
    resolution: Resolution
    booking: Booking


class Claim(CamelModel):
    id: str
    booking_id: str
    kind: str
    by: str
    minutes_late: int
    amount: int
    currency: str
    note: str | None = None
    status: Literal["open", "confirmed", "rejected"]
    created_at: Iso
    decided_by: str | None = None
    decided_at: Iso | None = None
    decision_note: str | None = None


def _dispute(d: DisputeRow, row: BookingRow) -> Dispute:
    offer = (
        Offer(refund_amount=d.offer_amount, by=d.offer_by or "", at=iso_from_datetime(d.offer_at))
        if d.offer_amount is not None and d.offer_at
        else None
    )
    return Dispute(
        booking_id=d.booking_id,
        opened_by=d.by,
        reason=d.reason,
        opened_at=iso_from_datetime(d.opened_at),
        respond_by=iso_from_datetime(d.respond_by),
        escalated_at=iso_from_datetime(d.escalated_at) if d.escalated_at else None,
        offer=offer,
        currency=row.currency,
        amount=row.amount,
    )


def _resolution(r: ResolutionRow, currency: str) -> Resolution:
    return Resolution(
        id=r.id,
        booking_id=r.booking_id,
        outcome=r.outcome,
        refund_amount=r.refund_amount,
        currency=currency,
        reason_code=r.reason_code,
        note=r.note,
        by=r.by,
        role=r.role,
        status=r.status,  # type: ignore[arg-type]
        approved_by=r.approved_by,
        created_at=iso_from_datetime(r.created_at),
        decided_at=iso_from_datetime(r.decided_at) if r.decided_at else None,
    )


def _claim(c: ClaimRow) -> Claim:
    return Claim(
        id=c.id,
        booking_id=c.booking_id,
        kind=c.kind,
        by=c.by,
        minutes_late=c.minutes_late,
        amount=c.amount,
        currency=c.currency,
        note=c.note,
        status=c.status,  # type: ignore[arg-type]
        created_at=iso_from_datetime(c.created_at),
        decided_by=c.decided_by,
        decided_at=iso_from_datetime(c.decided_at) if c.decided_at else None,
        decision_note=c.decision_note,
    )


async def _dispute_of(s: AsyncSession, row: BookingRow, *, lock: bool = False) -> DisputeRow:
    d = await s.get(DisputeRow, row.id, with_for_update=lock)
    if d is None:
        # ponytail: disputes opened before booking_disputes existed have their
        # row from migration 0016; this covers a race with that migration.
        now = _now()
        d = DisputeRow(
            booking_id=row.id,
            by=row.requester_id,
            reason=row.decline_reason or "",
            opened_at=now,
            respond_by=now + OFFER_WINDOW,
        )
        s.add(d)
        await s.flush()
    return d


# --- settling: one place moves the money ---------------------------------------------------


def refund_for(outcome: str, refund_amount: int | None, row: BookingRow) -> int:
    if outcome == "pay_owner":
        return 0
    if outcome == "refund_buyer":
        return row.amount
    if refund_amount is None or not 0 < refund_amount < row.amount:
        raise Invalid(f"a partial refund is more than 0 and less than {row.amount}", code="invalid_refund")
    return refund_amount


def outcome_of(refund: int, row: BookingRow) -> str:
    return "pay_owner" if refund == 0 else "refund_buyer" if refund == row.amount else "partial"


async def settle(repo: BookingRepository, row: BookingRow, refund: int, by: str, now: datetime) -> None:
    """Refund all: cancelled (payments refunds in full). Otherwise completed,
    with the refunded part in ``refundAmount`` (payments refunds it and pays
    the owner their share of the rest)."""
    if row.status != "disputed":
        raise Conflict(f"only a disputed booking can be settled; this one is {row.status}")
    to = "cancelled" if refund == row.amount else "completed"
    await repo.move(row, to, by, now, **({"refund_amount": refund} if refund else {}))


# --- the two sides settling it themselves (S-21) --------------------------------------------


class OfferIn(CamelModel):
    refund_amount: int = Field(ge=0)


@router.get("/bookings/{booking_id}/dispute", response_model=Dispute)
async def get_dispute(
    booking_id: str, repo: BookingRepository = Depends(_repo), p: Principal = Depends(require_principal)
) -> Dispute:
    row = await repo.visible(booking_id, p.sub)
    d = await repo.s.get(DisputeRow, row.id)
    if d is None:
        raise NotFound("this booking has no dispute")
    return _dispute(d, row)


@router.post("/bookings/{booking_id}/dispute/offer", response_model=Dispute)
async def make_offer(
    booking_id: str,
    body: OfferIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_principal),
) -> Dispute:
    """Either side proposes how much of the price goes back to the renter.
    A new offer replaces the one on the table and gives the other side 72
    hours to answer."""
    row = await repo.visible(booking_id, p.sub, lock=True)
    if row.status != "disputed":
        raise Conflict("offers are for a booking in dispute")
    if body.refund_amount > row.amount:
        raise Invalid(f"the refund cannot be more than the price ({row.amount})", code="invalid_refund")
    d = await _dispute_of(repo.s, row, lock=True)
    now = _now()
    d.offer_amount, d.offer_by, d.offer_at, d.respond_by = body.refund_amount, p.sub, now, now + OFFER_WINDOW
    other = row.owner_id if p.sub == row.requester_id else row.requester_id
    await repo.outbox.add(
        repo.s,
        DISPUTE_OFFER,
        {
            "bookingId": row.id,
            "to": other,
            "by": p.sub,
            "title": (row.listing_snapshot or {}).get("title", ""),
            "refundAmount": body.refund_amount,
            "currency": row.currency,
            "respondBy": iso_from_datetime(d.respond_by),
            "timeZone": (row.listing_snapshot or {}).get("timeZone") or market_of_currency(row.currency).time_zone,
        },
    )
    request.app.state.relay.wake()
    return _dispute(d, row)


@router.post("/bookings/{booking_id}/dispute/accept", response_model=Settled)
async def accept_offer(
    booking_id: str,
    body: OfferIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_principal),
    key: str | None = IdempotencyKey,
) -> Settled:
    """The other side agrees to the offer on the table (the amount is sent
    back, so nobody accepts an offer that changed under them)."""
    fp = fingerprint(request, body)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    row = await repo.visible(booking_id, p.sub, lock=True)
    d = await _dispute_of(repo.s, row, lock=True)
    if d.offer_amount is None:
        raise Conflict("there is no offer to accept")
    if d.offer_by == p.sub:
        raise Forbidden("the other side accepts your offer, not you", code="own_offer")
    if d.offer_amount != body.refund_amount:
        raise Conflict("the offer changed; look at it again", code="offer_changed")
    now = _now()
    res = ResolutionRow(
        id=new_id("rs"),
        booking_id=row.id,
        outcome=outcome_of(d.offer_amount, row),
        refund_amount=d.offer_amount,
        reason_code="agreement",
        note="",
        by=p.sub,
        role="parties",
        status="done",
        created_at=now,
        decided_at=now,
    )
    repo.s.add(res)
    await settle(repo, row, d.offer_amount, p.sub, now)
    request.app.state.relay.wake()
    answer = Settled(resolution=_resolution(res, row.currency), booking=to_booking(row, p.sub))
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


async def escalate_due(s: AsyncSession, now: datetime, limit: int) -> int:
    """Disputes whose deadline passed with no agreement go to staff."""
    q = (
        select(DisputeRow)
        .join(BookingRow, BookingRow.id == DisputeRow.booking_id)
        .where(DisputeRow.escalated_at.is_(None), DisputeRow.respond_by <= now, BookingRow.status == "disputed")
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    rows = list((await s.execute(q)).scalars())
    for d in rows:
        d.escalated_at = now
    return len(rows)


# --- staff settling it (H-6) ---------------------------------------------------------------


class ResolveIn(CamelModel):
    outcome: Literal["pay_owner", "refund_buyer", "partial"]
    # A partial refund, in the booking's minor units.
    refund_amount: int | None = Field(default=None, ge=1)
    reason_code: str = Field(default="other", pattern=f"^({REASONS})$")
    note: str = Field(default="", max_length=1000)
    # Only for the internal route (support tooling): who at support decided.
    by: str | None = Field(default=None, max_length=64)


class DecideIn(CamelModel):
    note: str = Field(default="", max_length=1000)


async def _resolve(
    request: Request, repo: BookingRepository, booking_id: str, body: ResolveIn, actor: str, role: str
) -> Settled:
    row = await repo.get(booking_id, lock=True)
    if row.status != "disputed":
        raise Conflict(f"only a disputed booking can be resolved; this one is {row.status}")
    pending = (
        await repo.s.execute(
            select(ResolutionRow.id).where(
                ResolutionRow.booking_id == row.id, ResolutionRow.status == "pending_approval"
            )
        )
    ).first()
    if pending:
        raise Conflict("a resolution of this booking is waiting for approval", code="approval_pending")
    refund = refund_for(body.outcome, body.refund_amount, row)
    limit = market_of_currency(row.currency).refund_limit(role)
    now = _now()
    res = ResolutionRow(
        id=new_id("rs"),
        booking_id=row.id,
        outcome=body.outcome,
        refund_amount=refund,
        reason_code=body.reason_code,
        note=body.note.strip(),
        by=actor,
        role=role,
        status="done" if refund <= limit else "pending_approval",
        created_at=now,
        decided_at=now if refund <= limit else None,
    )
    repo.s.add(res)
    if res.status == "done":
        await settle(repo, row, refund, f"support:{actor}", now)
    await audit(
        repo.s,
        repo.outbox,
        actor,
        "resolve_dispute" if res.status == "done" else "propose_resolution",
        "booking",
        row.id,
        f"{body.outcome} {refund} {row.currency} ({body.reason_code}) {res.note}".strip(),
    )
    request.app.state.relay.wake()
    return Settled(resolution=_resolution(res, row.currency), booking=to_booking(row, ""))


@admin.post("/bookings/{booking_id}/resolve", response_model=Settled)
async def resolve_as_staff(
    booking_id: str,
    body: ResolveIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_admin),
    key: str | None = IdempotencyKey,
) -> Settled:
    """Pay the owner, refund the renter, or refund part. Above the staff
    member's limit the resolution waits for a second staff member."""
    fp = fingerprint(request, body)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    role = staff_role(p, request.app.state.settings)
    answer = await _resolve(request, repo, booking_id, body.model_copy(update={"by": None}), p.sub, role)
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


@internal.post("/bookings/{booking_id}/resolve", response_model=Settled)
async def resolve(
    booking_id: str, body: ResolveIn, request: Request, repo: BookingRepository = Depends(_repo)
) -> Settled:
    """Support tooling (docs/runbook.md): the same rules as the console, with
    the support role's limit; ``by`` says who decided."""
    if not body.by:
        raise Invalid("say who at support decided (by)")
    return await _resolve(request, repo, booking_id, body, body.by, "support")


@admin.get("/resolutions", response_model=list[Resolution])
async def resolutions(
    status: str = Query(default="pending_approval", pattern="^(pending_approval|done|rejected)$"),
    repo: BookingRepository = Depends(_repo),
    _: Principal = Depends(require_admin),
) -> list[Resolution]:
    """Oldest first: what waits for a second pair of eyes."""
    q = (
        select(ResolutionRow, BookingRow.currency)
        .join(BookingRow, BookingRow.id == ResolutionRow.booking_id)
        .where(ResolutionRow.status == status)
        .order_by(ResolutionRow.created_at)
        .limit(200)
    )
    return [_resolution(r, cur) for r, cur in (await repo.s.execute(q)).all()]


async def _pending(repo: BookingRepository, resolution_id: str) -> tuple[ResolutionRow, BookingRow]:
    res = await repo.s.get(ResolutionRow, resolution_id, with_for_update=True)
    if res is None:
        raise NotFound(f"resolution {resolution_id} not found")
    if res.status != "pending_approval":
        raise Conflict(f"this resolution is already {res.status.replace('_', ' ')}")
    return res, await repo.get(res.booking_id, lock=True)


@admin.post("/resolutions/{resolution_id}/approve", response_model=Settled)
async def approve_resolution(
    resolution_id: str,
    body: DecideIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_admin),
    key: str | None = IdempotencyKey,
) -> Settled:
    """The second pair of eyes: someone else, whose limit covers the refund
    (a lead's does, up to theirs; two leads together, anything)."""
    fp = fingerprint(request, body)
    if (done := await replayed(repo.s, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    res, row = await _pending(repo, resolution_id)
    if res.by == p.sub:
        raise Forbidden("someone else approves your resolution", code="four_eyes")
    role = staff_role(p, request.app.state.settings)
    if role != "lead" and res.refund_amount > market_of_currency(row.currency).refund_limit(role):
        raise Forbidden("this refund needs a lead to approve it", code="needs_lead")
    now = _now()
    res.status, res.approved_by, res.decided_at = "done", p.sub, now
    await settle(repo, row, res.refund_amount, f"support:{p.sub}", now)
    await audit(repo.s, repo.outbox, p.sub, "approve_resolution", "booking", row.id, body.note or f"approved {res.id}")
    request.app.state.relay.wake()
    answer = Settled(resolution=_resolution(res, row.currency), booking=to_booking(row, ""))
    await remember(repo.s, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


@admin.post("/resolutions/{resolution_id}/reject", response_model=Resolution)
async def reject_resolution(
    resolution_id: str,
    body: DecideIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_admin),
) -> Resolution:
    """Not approved: the booking stays in dispute for another decision."""
    res, row = await _pending(repo, resolution_id)
    if res.by == p.sub:
        raise Forbidden("someone else decides on your resolution", code="four_eyes")
    res.status, res.approved_by, res.decided_at = "rejected", p.sub, _now()
    await audit(repo.s, repo.outbox, p.sub, "reject_resolution", "booking", row.id, body.note or f"rejected {res.id}")
    request.app.state.relay.wake()
    return _resolution(res, row.currency)


# --- the case view (H-9) -------------------------------------------------------------------


class CaseSummary(CamelModel):
    id: str
    status: str
    title: str
    requester_id: str
    owner_id: str
    amount: int
    currency: str
    window_start: Iso
    window_end: Iso
    updated_at: Iso
    dispute: Dispute | None = None
    pending_approval: bool = False
    open_claims: int = 0


class TimelineEntry(CamelModel):
    from_status: str | None = None
    to_status: str
    by: str
    at: Iso


class CaseMessage(CamelModel):
    id: str
    sender_id: str
    body: str
    at: Iso
    flagged: bool


class Case(CamelModel):
    booking: Booking
    requester_id: str
    owner_id: str
    timeline: list[TimelineEntry]
    messages: list[CaseMessage]
    evidence: list[dict]
    payment: dict | None = None
    dispute: Dispute | None = None
    resolutions: list[Resolution]
    claims: list[Claim]


async def _summaries(s: AsyncSession, rows: list[BookingRow]) -> list[CaseSummary]:
    ids = [r.id for r in rows]
    disputes = {
        d.booking_id: d for d in (await s.execute(select(DisputeRow).where(DisputeRow.booking_id.in_(ids)))).scalars()
    }
    pending = set(
        (
            await s.execute(
                select(ResolutionRow.booking_id).where(
                    ResolutionRow.booking_id.in_(ids), ResolutionRow.status == "pending_approval"
                )
            )
        ).scalars()
    )
    claims = dict(
        (
            await s.execute(
                select(ClaimRow.booking_id, func.count())
                .where(ClaimRow.booking_id.in_(ids), ClaimRow.status == "open")
                .group_by(ClaimRow.booking_id)
            )
        ).all()
    )
    return [
        CaseSummary(
            id=r.id,
            status=r.status,
            title=(r.listing_snapshot or {}).get("title", ""),
            requester_id=r.requester_id,
            owner_id=r.owner_id,
            amount=r.amount,
            currency=r.currency,
            window_start=iso_from_datetime(r.window_start),
            window_end=iso_from_datetime(r.window_end),
            updated_at=iso_from_datetime(r.updated_at),
            dispute=_dispute(disputes[r.id], r) if r.id in disputes else None,
            pending_approval=r.id in pending,
            open_claims=claims.get(r.id, 0),
        )
        for r in rows
    ]


@admin.get("/bookings", response_model=Page[CaseSummary])
async def cases(
    request: Request,
    status: str | None = Query(default=None, pattern="^[a-z_]{3,20}$"),
    member: str | None = Query(default=None, max_length=254, description="a member's id or email"),
    booking: str | None = Query(default=None, max_length=40),
    claims: str | None = Query(default=None, pattern="^open$", description="only bookings with open claims"),
    cursor: str | None = None,
    limit: int | None = None,
    repo: BookingRepository = Depends(_repo),
    _: Principal = Depends(require_admin),
) -> Page[CaseSummary]:
    """Find a case: by booking id, by member (id or email, either side), by
    status (``disputed``: escalated ones first), or with open claims. Most
    recently changed first."""
    q = select(BookingRow)
    if booking:
        q = q.where(BookingRow.id == booking)
    if member:
        who = await request.app.state.people.sub_of(member.strip()) if "@" in member else member.strip()
        if who is None:
            return Page(items=[], next_cursor=None)
        q = q.where(or_(BookingRow.requester_id == who, BookingRow.owner_id == who))
    if status:
        q = q.where(BookingRow.status == status)
    if claims:
        q = q.where(BookingRow.id.in_(select(ClaimRow.booking_id).where(ClaimRow.status == "open")))
    key = decode_cursor(cursor)
    if key:
        at = dt_from_iso(key["at"])
        q = q.where(or_(BookingRow.updated_at < at, and_(BookingRow.updated_at == at, BookingRow.id < key["id"])))
    n = clamp_limit(limit)
    rows = list(
        (await repo.s.execute(q.order_by(BookingRow.updated_at.desc(), BookingRow.id.desc()).limit(n + 1))).scalars()
    )
    more, rows = len(rows) > n, rows[:n]
    items = await _summaries(repo.s, rows)
    if status == "disputed":
        # Escalated disputes first (stable within each group).
        items.sort(key=lambda c: not (c.dispute and c.dispute.escalated_at))
    nxt = encode_cursor({"at": rows[-1].updated_at.isoformat(), "id": rows[-1].id}) if more else None
    return Page(items=items, next_cursor=nxt)


@admin.get("/bookings/{booking_id}/case", response_model=Case)
async def case(
    booking_id: str,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_admin),
) -> Case:
    """Everything about a booking on one screen: its timeline, the whole
    conversation as written (staff see what masking hid), the hand-over
    photos as short-lived links, the payment, the dispute and what was
    decided. Reading it is logged (H-7)."""
    from .messages import evidence_views

    row = await repo.get(booking_id)
    s = repo.s
    timeline = (
        await s.execute(select(TransitionRow).where(TransitionRow.booking_id == row.id).order_by(TransitionRow.id))
    ).scalars()
    msgs = (
        await s.execute(select(MessageRow).where(MessageRow.booking_id == row.id).order_by(MessageRow.at).limit(2000))
    ).scalars()
    res = (
        await s.execute(
            select(ResolutionRow).where(ResolutionRow.booking_id == row.id).order_by(ResolutionRow.created_at)
        )
    ).scalars()
    cl = (
        await s.execute(select(ClaimRow).where(ClaimRow.booking_id == row.id).order_by(ClaimRow.created_at))
    ).scalars()
    d = await s.get(DisputeRow, row.id)
    await audit(s, repo.outbox, p.sub, "read_case", "booking", row.id, "opened the case view")
    request.app.state.relay.wake()
    return Case(
        booking=to_booking(row, ""),
        requester_id=row.requester_id,
        owner_id=row.owner_id,
        timeline=[
            TimelineEntry(from_status=t.from_status, to_status=t.to_status, by=t.by, at=iso_from_datetime(t.at))
            for t in timeline
        ],
        messages=[
            CaseMessage(
                id=m.id, sender_id=m.sender_id, body=m.unmasked or m.body, at=iso_from_datetime(m.at), flagged=m.flagged
            )
            for m in msgs
        ],
        evidence=[e.model_dump(mode="json", by_alias=True) for e in await evidence_views(request, s, row.id)],
        payment=await request.app.state.payments.state(row.id),
        dispute=_dispute(d, row) if d else None,
        resolutions=[_resolution(r, row.currency) for r in res],
        claims=[_claim(c) for c in cl],
    )


# --- late returns and extensions (S-12) ----------------------------------------------------


class LateReturnIn(CamelModel):
    minutes_late: int = Field(ge=1, le=7 * 24 * 60)
    note: str | None = Field(default=None, max_length=1000)


def _rate_per_hour(row: BookingRow) -> int:
    quote = row.match.get("quote", {})
    hours = quote.get("hours") or 0
    return round(quote.get("base", 0) / hours) if hours else 0


def late_return_amount(row: BookingRow, minutes_late: int) -> int:
    """The extra time after 30 minutes' grace at the listing's hourly rate
    (rounded up to the quarter hour), plus a fee of one hour's rate capped
    per market. Nothing when within the grace."""
    billable = minutes_late - LATE_GRACE_MINUTES
    if billable <= 0:
        return 0
    rate = _rate_per_hour(row)
    extra = rate * math.ceil(billable / 15) * 15 // 60
    return extra + min(rate, market_of_currency(row.currency).late_fee_cap)


@router.post("/bookings/{booking_id}/late-return", response_model=Claim, status_code=201)
async def report_late_return(
    booking_id: str,
    body: LateReturnIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_principal),
) -> Claim:
    """The owner says the thing came back late, within a day of the end. It
    becomes a claim staff confirm in the case view; nothing is charged
    automatically (that needs a saved card, S-9)."""
    row = await repo.visible(booking_id, p.sub, lock=True)
    if p.sub != row.owner_id:
        raise Forbidden("only the owner reports a late return")
    if row.status not in ("active", "completed", "disputed"):
        raise Conflict("a late return is reported after a hand-over")
    now = _now()
    if not row.window_end <= now <= row.window_end + CLAIM_WITHIN:
        raise Conflict("a late return is reported within 24 hours after the booked end", code="claim_window")
    if await repo.s.scalar(select(ClaimRow.id).where(ClaimRow.booking_id == row.id, ClaimRow.kind == "late_return")):
        raise Conflict("a late return was already reported for this booking", code="claim_exists")
    amount = late_return_amount(row, body.minutes_late)
    if amount == 0:
        raise Invalid(f"up to {LATE_GRACE_MINUTES} minutes late is within the grace", code="within_grace")
    c = ClaimRow(
        id=new_id("cl"),
        booking_id=row.id,
        kind="late_return",
        by=p.sub,
        minutes_late=body.minutes_late,
        amount=amount,
        currency=row.currency,
        note=(body.note or "").strip() or None,
        status="open",
        created_at=now,
    )
    repo.s.add(c)
    await repo.s.flush()
    return _claim(c)


@router.get("/bookings/{booking_id}/claims", response_model=list[Claim])
async def booking_claims(
    booking_id: str, repo: BookingRepository = Depends(_repo), p: Principal = Depends(require_principal)
) -> list[Claim]:
    row = await repo.visible(booking_id, p.sub)
    q = select(ClaimRow).where(ClaimRow.booking_id == row.id).order_by(ClaimRow.created_at)
    return [_claim(c) for c in (await repo.s.execute(q)).scalars()]


class ClaimDecisionIn(CamelModel):
    decision: Literal["confirm", "reject"]
    note: str = Field(default="", max_length=1000)


@admin.post("/claims/{claim_id}/decide", response_model=Claim)
async def decide_claim(
    claim_id: str,
    body: ClaimDecisionIn,
    request: Request,
    repo: BookingRepository = Depends(_repo),
    p: Principal = Depends(require_admin),
) -> Claim:
    """Confirmed means the owner is owed it; collecting it waits for S-9."""
    c = await repo.s.get(ClaimRow, claim_id, with_for_update=True)
    if c is None:
        raise NotFound(f"claim {claim_id} not found")
    if c.status != "open":
        raise Conflict(f"this claim is already {c.status}")
    c.status = "confirmed" if body.decision == "confirm" else "rejected"
    c.decided_by, c.decided_at, c.decision_note = p.sub, _now(), body.note.strip() or None
    await audit(repo.s, repo.outbox, p.sub, f"{body.decision}_claim", "booking", c.booking_id, body.note or c.kind)
    request.app.state.relay.wake()
    return _claim(c)


class ExtendIn(CamelModel):
    hours: float = Field(gt=0, le=24)


@router.post("/bookings/{booking_id}/extend", status_code=201)
async def extend(
    booking_id: str,
    body: ExtendIn,
    request: Request,
    p: Principal = Depends(require_principal),
    idempotency_key: str | None = Header(default=None, max_length=80),
):
    """More time straight after the booking, while it is on: a new booking of
    the same listing by the same renter, instant if the listing is instant
    book, else a request the owner answers. Only if that time is free."""
    from .routes import BookingCreated, CreateBookingIn, create

    async with request.app.state.db.session() as s:
        row = await BookingRepository(s, request.app.state.outbox).visible(booking_id, p.sub)
    if p.sub != row.requester_id:
        raise Forbidden("only the renter extends a booking")
    if row.status not in ("accepted", "active") or _now() >= row.window_end:
        raise Conflict("a booking can be extended while it is on, before it ends", code="not_extendable")
    if row.requirement.get("mode") != "window":
        raise Invalid("only time bookings can be extended", code="not_extendable")
    end = row.window_end + timedelta(hours=body.hours)
    start_iso, end_iso = iso_from_datetime(row.window_end), iso_from_datetime(end)
    requirement = {**row.requirement, "hours": body.hours, "earliest": start_iso, "latest": end_iso}
    new = CreateBookingIn.model_validate(
        {"requirement": requirement, "listingId": row.listing_id, "slotId": "", "start": start_iso, "end": end_iso}
    )
    out: BookingCreated = await create(request, p.sub, new, idempotency_key, extends=row.id)
    return out
