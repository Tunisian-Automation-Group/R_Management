"""The inbox: every conversation a person has, as renter or owner, newest
first, with what is unread (UX-12). Masked as each booking's status says,
the same as the conversation itself."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Depends, Request, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_principal
from cappy_common.db import insert_or_ignore
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso

from .messages import _view
from .repository import SHOWS_HANDOVER, BookingRepository, _owner_sees
from .tables import BookingRow, MessageReadRow, MessageRow

router = ApiRouter()


class LastMessage(CamelModel):
    body: str
    at: Iso
    mine: bool


class Conversation(CamelModel):
    booking_id: str
    # The other side's name as the booking knows it; absent when unknown.
    other_name: str | None = None
    listing_title: str
    photo: str | None = None
    status: str
    last_message: LastMessage
    unread: int


class Inbox(CamelModel):
    items: list[Conversation]
    next: str | None = None
    # Across every conversation: the dock's badge.
    unread: int


def _mine(person: str):
    return or_(BookingRow.requester_id == person, and_(BookingRow.owner_id == person, _owner_sees()))


def _unread(person: str):
    """The other side's messages since the person last opened the conversation."""
    return (
        select(MessageRow.booking_id, func.count().label("n"))
        .join(BookingRow, BookingRow.id == MessageRow.booking_id)
        .outerjoin(
            MessageReadRow, and_(MessageReadRow.booking_id == MessageRow.booking_id, MessageReadRow.person_id == person)
        )
        .where(
            _mine(person),
            MessageRow.sender_id != person,
            or_(MessageReadRow.read_at.is_(None), MessageRow.at > MessageReadRow.read_at),
        )
        .group_by(MessageRow.booking_id)
    )


@router.get("/inbox", response_model=Inbox, response_model_exclude_none=True)
async def inbox(
    cursor: str | None = None,
    limit: int | None = None,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
) -> Inbox:
    me = p.sub
    last = select(MessageRow.booking_id, func.max(MessageRow.at).label("at")).group_by(MessageRow.booking_id).subquery()
    q = select(BookingRow, last.c.at).join(last, last.c.booking_id == BookingRow.id).where(_mine(me))
    key = decode_cursor(cursor)
    if key:
        at = dt_from_iso(key["at"])
        q = q.where(or_(last.c.at < at, and_(last.c.at == at, BookingRow.id < key["id"])))
    n = clamp_limit(limit)
    rows = list((await session.execute(q.order_by(last.c.at.desc(), BookingRow.id.desc()).limit(n + 1))).all())
    more, rows = len(rows) > n, rows[:n]
    counts = dict((await session.execute(_unread(me))).tuples().all())
    items = []
    for booking, _ in rows:
        latest = await session.scalar(
            select(MessageRow)
            .where(MessageRow.booking_id == booking.id)
            .order_by(MessageRow.at.desc(), MessageRow.id.desc())
            .limit(1)
        )
        shown = _view(latest, me, booking.status in SHOWS_HANDOVER)
        snap = booking.listing_snapshot or {}
        other = snap.get("ownerName") if me == booking.requester_id else snap.get("renterName")
        items.append(
            Conversation(
                booking_id=booking.id,
                other_name=other,
                listing_title=snap.get("title", ""),
                photo=snap.get("photo"),
                status=booking.status,
                last_message=LastMessage(body=shown.body, at=shown.at, mine=shown.mine),
                unread=counts.get(booking.id, 0),
            )
        )
    nxt = encode_cursor({"at": rows[-1][1].isoformat(), "id": rows[-1][0].id}) if more else None
    return Inbox(items=items, next=nxt, unread=sum(counts.values()))


@router.post("/inbox/{booking_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read(
    booking_id: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> Response:
    """The conversation was opened: everything in it until now is read."""
    await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    now = datetime.now(UTC)
    row = await session.get(MessageReadRow, (booking_id, p.sub))
    if row is None:
        await insert_or_ignore(session, MessageReadRow, booking_id=booking_id, person_id=p.sub, read_at=now)
    else:
        row.read_at = now
    return Response(status_code=status.HTTP_204_NO_CONTENT)
