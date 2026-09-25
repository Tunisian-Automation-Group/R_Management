"""Reports and moderation (DSA Art. 16 and 17; Apple 1.2, Google UGC policy).

Anyone can report a listing, a profile, a message or a review; someone
without an account leaves an email so they can hear back. Every report is
acknowledged. Staff (Cognito group "admin") decide; every decision is
recorded, the person affected gets a statement of reasons, and the reporter
hears the outcome.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Query, Request, status
from pydantic import EmailStr, Field
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, optional_principal, require_admin
from cappy_common.errors import Conflict, Invalid, NotFound, RateLimited
from cappy_common.events import MODERATION_DECISION, OWNER_SUSPENDED, REPORT_RECEIVED
from cappy_common.idempotency import IdempotencyKey, fingerprint, remember, replayed
from cappy_common.ids import new_id
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .tables import IDEMPOTENCY, ListingRow, ModerationActionRow, OwnerRow, ReportRow

log = logging.getLogger(__name__)
public = ApiRouter()
admin = ApiRouter(prefix="/admin")

TARGETS = "^(listing|owner|message|review)$"
REASONS = "^(illegal|fraud|unsafe|counterfeit|spam|offensive|privacy|other)$"


class ReportIn(CamelModel):
    target_type: str = Field(pattern=TARGETS)
    target_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(pattern=REASONS)
    details: str = Field(min_length=10, max_length=2000, description="What is wrong, and where exactly")
    # Required without an account (DSA Art. 16(2)(c)), so we can reply.
    email: EmailStr | None = None
    # Art. 16(2)(d): the notifier confirms the notice is accurate and complete.
    good_faith: bool | None = None


# Art. 17(3)(f): what the person affected can do about a decision. The
# notifications service sends it in their language; this is the record.
REDRESS = (
    "You can contest this decision by replying to this email within 6 months; a person who was not "
    "involved will look at it again. You can also turn to a certified out-of-court dispute settlement "
    "body (DSA Art. 21) or to the courts."
)
RESTRICTIONS = {
    "take_down": "The listing was removed and can no longer be seen or booked.",
    "suspend": "The account was suspended: its listings were removed, and it can no longer list or book.",
}
DEFAULT_CLAUSE = "Terms of use: rules for listings and conduct"


class StatementOfReasons(CamelModel):
    """DSA Art. 17(3), one field per point the article lists."""

    restriction: str
    facts: str
    automated: bool
    ground: str
    clause: str
    redress: str


class Report(CamelModel):
    id: str
    target_type: str
    target_id: str
    reason: str
    details: str
    status: str
    created_at: Iso
    decision: str | None = None
    statement: str | None = None
    statement_of_reasons: StatementOfReasons | None = None


class Grounds(CamelModel):
    # The facts and circumstances relied on (Art. 17(3)(b)).
    statement: str = Field(min_length=20, max_length=2000)
    # Illegal content (a law) or incompatible with the terms (a clause), (d)/(e).
    ground: str = Field(default="terms", pattern="^(law|terms)$")
    clause: str | None = Field(default=None, max_length=200)
    # Whether automated means took or detected it (Art. 17(3)(c)).
    automated: bool = False


class DecisionIn(Grounds):
    action: str = Field(pattern="^(dismiss|take_down|suspend)$")


def statement_of_reasons(action: str, g: Grounds) -> dict | None:
    """Only a restriction needs one; a dismissal restricts nobody."""
    if action not in RESTRICTIONS:
        return None
    return StatementOfReasons(
        restriction=RESTRICTIONS[action],
        facts=g.statement.strip(),
        automated=g.automated,
        ground=g.ground,
        clause=(g.clause or "").strip() or (DEFAULT_CLAUSE if g.ground == "terms" else "the applicable law"),
        redress=REDRESS,
    ).model_dump(mode="json", by_alias=True)


def _outbox(request: Request):
    return request.app.state.outbox


def _view(r: ReportRow) -> Report:
    return Report(
        id=r.id,
        target_type=r.target_type,
        target_id=r.target_id,
        reason=r.reason,
        details=r.details,
        status=r.status,
        created_at=iso_from_datetime(r.created_at),
        decision=r.decision,
        statement=r.statement,
        statement_of_reasons=r.statement_of_reasons,
    )


ANONYMOUS_PER_TARGET, MEMBERS_PER_TARGET = 5, 20


@public.post("/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
async def report(
    body: ReportIn,
    request: Request,
    session: AsyncSession = Tx,
    p: Principal | None = Depends(optional_principal),
    key: str | None = IdempotencyKey,
) -> Report:
    # Signed-in only: an anonymous key is nobody's, and a replay would show one
    # stranger's report to another.
    key, fp = (key if p else None), fingerprint(request, body)
    if p and (done := await replayed(session, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    if not body.good_faith:
        raise Invalid("confirm that what you report is accurate and complete to the best of your knowledge")
    if p is None and body.email is None:
        raise Invalid("leave an email so we can tell you what we decide")
    # A signed-in reporter hears back on their own address, never one they type.
    email = None if p is not None else str(body.email)
    day = datetime.now(UTC) - timedelta(days=1)
    if email is not None:
        # Every report sends mail to the address given: bound it, so nobody can
        # use Cappy to flood an inbox (or ruin its sending reputation).
        sent = (
            await session.execute(
                select(func.count()).where(ReportRow.reporter_email == email, ReportRow.created_at >= day)
            )
        ).scalar_one()
        if sent >= 3:
            raise RateLimited("we already have your reports from today; we will be in touch")
    # Anonymous and signed-in reports have their own caps, so strangers filling
    # the anonymous one never turn away a member's report (P-7). The anonymous
    # receipt mail stays: DSA Art. 16(2)(c) asks notices for an email and
    # 16(4) to confirm receipt to it, so a verification mail would be the same
    # one mail; the per-address cap above bounds it instead.
    anonymous = p is None
    about = (
        await session.execute(
            select(func.count()).where(
                ReportRow.target_id == body.target_id,
                ReportRow.created_at >= day,
                ReportRow.reporter_id.is_(None) if anonymous else ReportRow.reporter_id.is_not(None),
            )
        )
    ).scalar_one()
    if about >= (ANONYMOUS_PER_TARGET if anonymous else MEMBERS_PER_TARGET):
        raise RateLimited("this has been reported many times today; it is already being looked at")
    row = ReportRow(
        id=new_id("rp"),
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details.strip(),
        reporter_id=p.sub if p else None,
        reporter_email=email,
        status="open",
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    await _outbox(request).add(
        session,
        REPORT_RECEIVED,
        {
            "reportId": row.id,
            "reporterId": row.reporter_id,
            "reporterEmail": row.reporter_email,
            "targetType": row.target_type,
        },
    )
    answer = _view(row)
    if p:
        await remember(session, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


# --- staff ---------------------------------------------------------------------------------


@admin.get("/reports", response_model=Page[Report])
async def queue(
    state: str = Query(default="open", alias="status", pattern="^(open|actioned|dismissed)$"),
    cursor: str | None = None,
    limit: int | None = None,
    session: AsyncSession = Tx,
    _: Principal = Depends(require_admin),
) -> Page[Report]:
    """Oldest first: the longest-waiting notice is handled first."""
    n = clamp_limit(limit)
    q = select(ReportRow).where(ReportRow.status == state)
    key = decode_cursor(cursor)
    if key:
        at = dt_from_iso(key["at"])
        q = q.where(or_(ReportRow.created_at > at, and_(ReportRow.created_at == at, ReportRow.id > key["id"])))
    rows = list((await session.execute(q.order_by(ReportRow.created_at, ReportRow.id).limit(n + 1))).scalars())
    more = len(rows) > n
    rows = rows[:n]
    nxt = encode_cursor({"at": rows[-1].created_at.isoformat(), "id": rows[-1].id}) if more else None
    return Page(items=[_view(r) for r in rows], next_cursor=nxt)


async def purge(request: Request, listing_ids: list[str]) -> None:
    """Take a removed listing out of the CDN now, not when its cache expires."""
    import asyncio
    import time

    from cappy_common.events import aws_client

    settings = request.app.state.settings
    if not settings.cdn_distribution_id or not listing_ids:
        return
    paths = [f"/api/listings/{lid}*" for lid in listing_ids[:100]] + ["/api/search*"]
    try:
        cf = aws_client("cloudfront", settings)
        await asyncio.to_thread(
            cf.create_invalidation,
            DistributionId=settings.cdn_distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(paths), "Items": paths},
                "CallerReference": f"mod-{time.time_ns()}",
            },
        )
    except Exception as e:  # noqa: BLE001 - the cache expires by itself within minutes anyway
        log.warning("could not purge the CDN for %s: %s", listing_ids, e)


async def _removed(request: Request, session: AsyncSession, listing_ids: list[str]) -> None:
    """Booking declines these listings' pending requests (their card holds are
    released): nobody can accept a request on a listing that was taken down."""
    from cappy_common.events import LISTING_CHANGED

    for lid in listing_ids:
        await _outbox(request).add(session, LISTING_CHANGED, {"listingId": lid, "change": "removed"})
    await purge(request, listing_ids)


async def _take_down(session: AsyncSession, listing_id: str) -> ListingRow:
    row = await session.get(ListingRow, listing_id, with_for_update=True)
    if row is None or row.deleted_at is not None:
        raise NotFound(f"listing {listing_id} not found")
    now = datetime.now(UTC)
    row.moderated_at, row.active, row.updated_at = now, False, now
    return row


async def _suspend(session: AsyncSession, owner_id: str) -> tuple[OwnerRow, list[str]]:
    owner = await session.get(OwnerRow, owner_id, with_for_update=True)
    if owner is None or owner.deleted_at is not None:
        raise NotFound(f"owner {owner_id} not found")
    now = datetime.now(UTC)
    owner.suspended_at = now
    live = select(ListingRow.id).where(
        ListingRow.owner_id == owner_id, ListingRow.deleted_at.is_(None), ListingRow.moderated_at.is_(None)
    )
    taken = list((await session.execute(live)).scalars())
    await session.execute(
        update(ListingRow)
        .where(ListingRow.owner_id == owner_id, ListingRow.deleted_at.is_(None), ListingRow.moderated_at.is_(None))
        .values(moderated_at=now, active=False, updated_at=now)
    )
    return owner, taken


async def _record(
    session: AsyncSession,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    statement: str,
    report_id: str | None = None,
    reasons: dict | None = None,
) -> None:
    session.add(
        ModerationActionRow(
            id=new_id("ma"),
            actor_id=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            report_id=report_id,
            statement=statement,
            statement_of_reasons=reasons,
            at=datetime.now(UTC),
        )
    )


async def _affected_owner(session: AsyncSession, target_type: str, target_id: str) -> str | None:
    if target_type == "owner":
        return target_id
    if target_type == "listing":
        row = await session.get(ListingRow, target_id)
        return row.owner_id if row else None
    return None


@admin.post("/reports/{report_id}/decide", response_model=Report)
async def decide(
    report_id: str,
    body: DecisionIn,
    request: Request,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_admin),
) -> Report:
    r = await session.get(ReportRow, report_id, with_for_update=True)
    if r is None:
        raise NotFound(f"report {report_id} not found")
    if r.status != "open":
        raise Conflict(f"this report was already {r.status}")
    affected = await _affected_owner(session, r.target_type, r.target_id)
    if body.action == "take_down":
        if r.target_type != "listing":
            raise Invalid("only a listing can be taken down; suspend the owner for a profile")
        await _take_down(session, r.target_id)
        await _removed(request, session, [r.target_id])
    elif body.action == "suspend":
        if affected is None:
            raise Invalid("this report does not point at an owner")
        _, taken = await _suspend(session, affected)
        await _removed(request, session, taken)
        await _outbox(request).add(session, OWNER_SUSPENDED, {"ownerId": affected})
    now = datetime.now(UTC)
    r.status = "dismissed" if body.action == "dismiss" else "actioned"
    r.decided_at, r.decided_by, r.decision, r.statement = now, p.sub, body.action, body.statement.strip()
    r.statement_of_reasons = statement_of_reasons(body.action, body)
    await _record(session, p.sub, body.action, r.target_type, r.target_id, r.statement, r.id, r.statement_of_reasons)
    await _outbox(request).add(
        session,
        MODERATION_DECISION,
        {
            "reportId": r.id,
            "action": body.action,
            "targetType": r.target_type,
            "targetId": r.target_id,
            # Art. 17: the person affected is told why (never for a dismissal).
            "affectedId": affected if body.action != "dismiss" else None,
            "reporterId": r.reporter_id,
            "reporterEmail": r.reporter_email,
            "statement": r.statement,
            "statementOfReasons": r.statement_of_reasons,
        },
    )
    return _view(r)


class ActionIn(Grounds):
    pass


class AuditEntry(CamelModel):
    id: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    report_id: str | None = None
    statement: str
    at: Iso


@admin.post("/listings/{listing_id}/take-down", status_code=status.HTTP_204_NO_CONTENT)
async def take_down(
    listing_id: str, body: ActionIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    row = await _take_down(session, listing_id)
    await _removed(request, session, [listing_id])
    reasons = statement_of_reasons("take_down", body)
    await _record(session, p.sub, "take_down", "listing", listing_id, body.statement, reasons=reasons)
    await _outbox(request).add(
        session,
        MODERATION_DECISION,
        {
            "action": "take_down",
            "targetType": "listing",
            "targetId": listing_id,
            "affectedId": row.owner_id,
            "statement": body.statement,
            "statementOfReasons": reasons,
        },
    )


@admin.post("/owners/{owner_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
async def suspend(
    owner_id: str, body: ActionIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    _, taken = await _suspend(session, owner_id)
    await _removed(request, session, taken)
    reasons = statement_of_reasons("suspend", body)
    await _record(session, p.sub, "suspend", "owner", owner_id, body.statement, reasons=reasons)
    await _outbox(request).add(session, OWNER_SUSPENDED, {"ownerId": owner_id})
    await _outbox(request).add(
        session,
        MODERATION_DECISION,
        {
            "action": "suspend",
            "targetType": "owner",
            "targetId": owner_id,
            "affectedId": owner_id,
            "statement": body.statement,
            "statementOfReasons": reasons,
        },
    )


@admin.post("/owners/{owner_id}/reinstate", status_code=status.HTTP_204_NO_CONTENT)
async def reinstate(
    owner_id: str, body: ActionIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    """Lifts the suspension. Their listings stay down; they can list again."""
    owner = await session.get(OwnerRow, owner_id, with_for_update=True)
    if owner is None:
        raise NotFound(f"owner {owner_id} not found")
    owner.suspended_at = None
    await _record(session, p.sub, "reinstate", "owner", owner_id, body.statement)
    from cappy_common.events import OWNER_REINSTATED

    await _outbox(request).add(session, OWNER_REINSTATED, {"ownerId": owner_id})


@admin.get("/audit", response_model=list[AuditEntry])
async def audit(
    limit: int | None = None, session: AsyncSession = Tx, _: Principal = Depends(require_admin)
) -> list[AuditEntry]:
    q = select(ModerationActionRow).order_by(ModerationActionRow.at.desc()).limit(clamp_limit(limit))
    return [
        AuditEntry(
            id=r.id,
            actor_id=r.actor_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            report_id=r.report_id,
            statement=r.statement,
            at=iso_from_datetime(r.at),
        )
        for r in (await session.execute(q)).scalars()
    ]


class HeldListing(CamelModel):
    id: str
    owner_id: str
    title: str
    category: str
    rate_per_hour: int
    held_at: Iso


@admin.get("/listings/held", response_model=list[HeldListing])
async def held(session: AsyncSession = Tx, _: Principal = Depends(require_admin)) -> list[HeldListing]:
    """New owners' expensive listings, oldest first, waiting for a look."""
    q = (
        select(ListingRow)
        .where(ListingRow.held_at.is_not(None), ListingRow.deleted_at.is_(None))
        .order_by(ListingRow.held_at)
    )
    return [
        HeldListing(
            id=r.id,
            owner_id=r.owner_id,
            title=r.title,
            category=r.category,
            rate_per_hour=int(r.spec.get("ratePerHour", 0)),
            held_at=iso_from_datetime(r.held_at),
        )
        for r in (await session.execute(q.limit(200))).scalars()
    ]


@admin.post("/listings/{listing_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve(
    listing_id: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    from cappy_common.events import LISTING_CHANGED

    row = await session.get(ListingRow, listing_id, with_for_update=True)
    if row is None or row.held_at is None:
        raise NotFound(f"no held listing {listing_id}")
    row.held_at, row.active, row.updated_at = None, True, datetime.now(UTC)
    await _record(session, p.sub, "approve", "listing", listing_id, "Checked and approved")
    await _outbox(request).add(session, LISTING_CHANGED, {"listingId": listing_id, "change": "approved"})


# --- notices from the system (S-17, S-18) --------------------------------------------------

FLAG_REASONS = {"reliability", "linked_to_suspended"}


async def flag(session: AsyncSession, person_id: str, reason: str, details: str) -> None:
    """Queue a person for staff as a report nobody sent. One open notice per
    person and reason: a second signal while staff have not looked is noise."""
    if reason not in FLAG_REASONS:
        raise ValueError(f"unknown flag reason {reason}")
    q = select(func.count()).where(
        ReportRow.target_type == "owner",
        ReportRow.target_id == person_id,
        ReportRow.reason == reason,
        ReportRow.status == "open",
    )
    if (await session.execute(q)).scalar_one():
        return
    session.add(
        ReportRow(
            id=new_id("rp"),
            target_type="owner",
            target_id=person_id,
            reason=reason,
            details=details[:2000],
            status="open",
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()


# --- transparency (DSA Art. 15 and 24) ------------------------------------------------------


class DsaStats(CamelModel):
    month: str
    # People who were a party to a booking made in the month: a lower bound
    # for Art. 24(2); the exact count comes from analytics (docs/analytics.md).
    active_recipients: int
    notices: dict[str, dict[str, int]]
    median_hours_to_decision: float | None = None


@admin.get("/dsa-stats", response_model=DsaStats)
async def dsa_stats(
    request: Request,
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    session: AsyncSession = Tx,
    _: Principal = Depends(require_admin),
) -> DsaStats:
    """What a transparency report needs for one month, on request (S-30)."""
    import statistics

    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1, tzinfo=UTC)
    end = datetime(y + (m == 12), m % 12 + 1, 1, tzinfo=UTC)
    rows = list(
        (
            await session.execute(
                select(ReportRow.reason, ReportRow.decision, ReportRow.created_at, ReportRow.decided_at).where(
                    ReportRow.created_at >= start, ReportRow.created_at < end
                )
            )
        ).all()
    )
    by_reason: dict[str, int] = {}
    by_decision: dict[str, int] = {}
    hours = []
    for reason, decision, created, decided in rows:
        by_reason[reason] = by_reason.get(reason, 0) + 1
        by_decision[decision or "open"] = by_decision.get(decision or "open", 0) + 1
        if decided is not None:
            hours.append((decided - created).total_seconds() / 3600)
    active = await request.app.state.bookings.active_people(start, end)
    return DsaStats(
        month=month,
        active_recipients=active,
        notices={"byReason": by_reason, "byDecision": by_decision},
        median_hours_to_decision=round(statistics.median(hours), 1) if hours else None,
    )
