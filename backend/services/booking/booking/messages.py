"""Messages between the two sides of a booking, and blocks between people.

Until a booking is accepted, phone numbers, email addresses and links are
masked: taking a deal off the platform before it is agreed is how renters
get scammed and owners go unpaid (Airbnb and Vinted both enforce this).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from fastapi import Depends, Request, Response, status
from pydantic import Field
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, require_principal
from cappy_common.errors import Forbidden, Invalid
from cappy_common.events import BOOKING_MESSAGE
from cappy_common.ids import new_id
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .repository import SHOWS_HANDOVER, BookingRepository
from .tables import BlockRow, MessageRow

router = ApiRouter()
HIDDEN = "[shared once the booking is accepted]"

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(com|de|net|org|io|eu|co|me|info|app)(/\S*)?\b", re.I)
# Seven or more digits, allowing the spaces, dots, dashes and brackets people type.
_PHONE = re.compile(r"(\+?\d[\d\s().-]{5,}\d)")
_HANDLES = re.compile(r"\b(whats\s*app|telegram|signal|instagram|insta|snap(chat)?)\b[^\n]{0,40}", re.I)


def mask(text: str) -> str:
    for pattern in (_EMAIL, _URL, _HANDLES):
        text = pattern.sub(HIDDEN, text)
    return _PHONE.sub(lambda m: HIDDEN if sum(c.isdigit() for c in m.group(0)) >= 7 else m.group(0), text)


class MessageIn(CamelModel):
    body: str = Field(min_length=1, max_length=2000)


class Message(CamelModel):
    id: str
    sender_id: str
    body: str
    at: Iso
    mine: bool


def _view(row: MessageRow, viewer: str) -> Message:
    return Message(
        id=row.id, sender_id=row.sender_id, body=row.body, at=iso_from_datetime(row.at), mine=row.sender_id == viewer
    )


async def blocked_between(session: AsyncSession, a: str, b: str) -> bool:
    q = select(BlockRow).where(
        or_(
            and_(BlockRow.blocker_id == a, BlockRow.blocked_id == b),
            and_(BlockRow.blocker_id == b, BlockRow.blocked_id == a),
        )
    )
    return (await session.execute(q.limit(1))).first() is not None


@router.post("/bookings/{booking_id}/messages", response_model=Message, status_code=status.HTTP_201_CREATED)
async def send(
    booking_id: str,
    body: MessageIn,
    request: Request,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
) -> Message:
    repo = BookingRepository(session, request.app.state.outbox)
    row = await repo.visible(booking_id, p.sub)
    other = row.owner_id if p.sub == row.requester_id else row.requester_id
    if await blocked_between(session, p.sub, other):
        raise Forbidden("you cannot message this person")
    text = body.body.strip()
    if not text:
        raise Invalid("say something")
    if row.status not in SHOWS_HANDOVER:
        text = mask(text)
    msg = MessageRow(id=new_id("msg"), booking_id=row.id, sender_id=p.sub, body=text, at=datetime.now(UTC))
    session.add(msg)
    await session.flush()
    await repo.outbox.add(
        session,
        BOOKING_MESSAGE,
        {"bookingId": row.id, "senderId": p.sub, "recipientId": other, "title": row.listing_snapshot["title"]},
    )
    request.app.state.relay.wake()
    return _view(msg, p.sub)


@router.get("/bookings/{booking_id}/messages", response_model=Page[Message])
async def conversation(
    booking_id: str,
    request: Request,
    cursor: str | None = None,
    limit: int | None = None,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
) -> Page[Message]:
    """Oldest first; the cursor continues towards newer messages."""
    await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    n = clamp_limit(limit)
    q = select(MessageRow).where(MessageRow.booking_id == booking_id)
    key = decode_cursor(cursor)
    if key:
        at = dt_from_iso(key["at"])
        q = q.where(or_(MessageRow.at > at, and_(MessageRow.at == at, MessageRow.id > key["id"])))
    rows = list((await session.execute(q.order_by(MessageRow.at, MessageRow.id).limit(n + 1))).scalars())
    more = len(rows) > n
    rows = rows[:n]
    nxt = encode_cursor({"at": rows[-1].at.isoformat(), "id": rows[-1].id}) if more else None
    return Page(items=[_view(r, p.sub) for r in rows], next_cursor=nxt)


@router.put("/me/blocks/{person}", status_code=status.HTTP_204_NO_CONTENT)
async def block(person: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> Response:
    """No more messages or new bookings between the two of you, either way."""
    if person == p.sub:
        raise Invalid("you cannot block yourself")
    if await session.get(BlockRow, (p.sub, person)) is None:
        session.add(BlockRow(blocker_id=p.sub, blocked_id=person, at=datetime.now(UTC)))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/blocks/{person}", status_code=status.HTTP_204_NO_CONTENT)
async def unblock(person: str, session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> Response:
    await session.execute(delete(BlockRow).where(BlockRow.blocker_id == p.sub, BlockRow.blocked_id == person))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/blocks", response_model=list[str])
async def my_blocks(session: AsyncSession = Tx, p: Principal = Depends(require_principal)) -> list[str]:
    q = select(BlockRow.blocked_id).where(BlockRow.blocker_id == p.sub).order_by(BlockRow.at.desc()).limit(500)
    return list((await session.execute(q)).scalars())


# --- hand-over evidence ---------------------------------------------------------------------

CHECK_IN_FROM = frozenset({"accepted", "active"})
CHECK_OUT_FROM = frozenset({"active", "completed", "disputed"})


class EvidenceIn(CamelModel):
    stage: str = Field(pattern="^(check_in|check_out)$")
    photos: list[str] = Field(min_length=1, max_length=12)
    note: str | None = Field(default=None, max_length=1000)


class Evidence(CamelModel):
    id: str
    by: str
    stage: str
    photos: list[str]
    note: str | None = None
    at: Iso


@router.post("/bookings/{booking_id}/evidence", response_model=Evidence, status_code=status.HTTP_201_CREATED)
async def add_evidence(
    booking_id: str,
    body: EvidenceIn,
    request: Request,
    session: AsyncSession = Tx,
    p: Principal = Depends(require_principal),
) -> Evidence:
    from .tables import EvidenceRow

    row = await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    allowed = CHECK_IN_FROM if body.stage == "check_in" else CHECK_OUT_FROM
    if row.status not in allowed:
        raise Invalid(f"{body.stage.replace('_', '-')} photos are not possible while the booking is {row.status}")
    await request.app.state.catalog.keep_evidence(p.sub, body.photos)
    ev = EvidenceRow(
        id=new_id("evd"),
        booking_id=row.id,
        by=p.sub,
        stage=body.stage,
        photos=body.photos,
        note=(body.note or "").strip() or None,
        at=datetime.now(UTC),
    )
    session.add(ev)
    await session.flush()
    return Evidence(id=ev.id, by=ev.by, stage=ev.stage, photos=ev.photos, note=ev.note, at=iso_from_datetime(ev.at))


@router.get("/bookings/{booking_id}/evidence", response_model=list[Evidence])
async def evidence(
    booking_id: str, request: Request, session: AsyncSession = Tx, p: Principal = Depends(require_principal)
) -> list[Evidence]:
    from .tables import EvidenceRow

    await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    rows = (
        await session.execute(select(EvidenceRow).where(EvidenceRow.booking_id == booking_id).order_by(EvidenceRow.at))
    ).scalars()
    return [
        Evidence(id=r.id, by=r.by, stage=r.stage, photos=r.photos, note=r.note, at=iso_from_datetime(r.at))
        for r in rows
    ]
