"""Reports and moderation (DSA Art. 16 and 17; Apple 1.2, Google UGC policy).

Anyone can report a listing, a profile, a message or a review; someone
without an account leaves an email so they can hear back. Every report is
acknowledged. Staff (Cognito group "admin") decide; every decision is
recorded, the person affected gets a statement of reasons, and the reporter
hears the outcome.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Query, Request, status
from pydantic import EmailStr, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, optional_principal, require_admin
from cappy_common.errors import Conflict, Invalid, NotFound
from cappy_common.events import MODERATION_DECISION, OWNER_SUSPENDED, REPORT_RECEIVED
from cappy_common.ids import new_id
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .tables import ListingRow, ModerationActionRow, OwnerRow, ReportRow

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


class DecisionIn(CamelModel):
    action: str = Field(pattern="^(dismiss|take_down|suspend)$")
    # The statement of reasons (DSA Art. 17): what was decided, on what grounds.
    statement: str = Field(min_length=20, max_length=2000)


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
    )


@public.post("/reports", response_model=Report, status_code=status.HTTP_201_CREATED)
async def report(
    body: ReportIn, request: Request, session: AsyncSession = Tx, p: Principal | None = Depends(optional_principal)
) -> Report:
    if p is None and body.email is None:
        raise Invalid("leave an email so we can tell you what we decide")
    row = ReportRow(
        id=new_id("rp"),
        target_type=body.target_type,
        target_id=body.target_id,
        reason=body.reason,
        details=body.details.strip(),
        reporter_id=p.sub if p else None,
        reporter_email=str(body.email) if body.email else None,
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
    return _view(row)


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


async def _take_down(session: AsyncSession, listing_id: str) -> ListingRow:
    row = await session.get(ListingRow, listing_id, with_for_update=True)
    if row is None or row.deleted_at is not None:
        raise NotFound(f"listing {listing_id} not found")
    now = datetime.now(UTC)
    row.moderated_at, row.active, row.updated_at = now, False, now
    return row


async def _suspend(session: AsyncSession, owner_id: str) -> OwnerRow:
    owner = await session.get(OwnerRow, owner_id, with_for_update=True)
    if owner is None or owner.deleted_at is not None:
        raise NotFound(f"owner {owner_id} not found")
    now = datetime.now(UTC)
    owner.suspended_at = now
    await session.execute(
        update(ListingRow)
        .where(ListingRow.owner_id == owner_id, ListingRow.deleted_at.is_(None), ListingRow.moderated_at.is_(None))
        .values(moderated_at=now, active=False, updated_at=now)
    )
    return owner


async def _record(
    session: AsyncSession,
    actor: str,
    action: str,
    target_type: str,
    target_id: str,
    statement: str,
    report_id: str | None = None,
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
    elif body.action == "suspend":
        if affected is None:
            raise Invalid("this report does not point at an owner")
        await _suspend(session, affected)
        await _outbox(request).add(session, OWNER_SUSPENDED, {"ownerId": affected})
    now = datetime.now(UTC)
    r.status = "dismissed" if body.action == "dismiss" else "actioned"
    r.decided_at, r.decided_by, r.decision, r.statement = now, p.sub, body.action, body.statement.strip()
    await _record(session, p.sub, body.action, r.target_type, r.target_id, r.statement, r.id)
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
        },
    )
    return _view(r)


class ActionIn(CamelModel):
    statement: str = Field(min_length=20, max_length=2000)


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
    await _record(session, p.sub, "take_down", "listing", listing_id, body.statement)
    await _outbox(request).add(
        session,
        MODERATION_DECISION,
        {
            "action": "take_down",
            "targetType": "listing",
            "targetId": listing_id,
            "affectedId": row.owner_id,
            "statement": body.statement,
        },
    )


@admin.post("/owners/{owner_id}/suspend", status_code=status.HTTP_204_NO_CONTENT)
async def suspend(
    owner_id: str, body: ActionIn, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    await _suspend(session, owner_id)
    await _record(session, p.sub, "suspend", "owner", owner_id, body.statement)
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
        },
    )


@admin.post("/owners/{owner_id}/reinstate", status_code=status.HTTP_204_NO_CONTENT)
async def reinstate(
    owner_id: str, body: ActionIn, session: AsyncSession = Tx, p: Principal = Depends(require_admin)
) -> None:
    """Lifts the suspension. Their listings stay down; they can list again."""
    owner = await session.get(OwnerRow, owner_id, with_for_update=True)
    if owner is None:
        raise NotFound(f"owner {owner_id} not found")
    owner.suspended_at = None
    await _record(session, p.sub, "reinstate", "owner", owner_id, body.statement)


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
