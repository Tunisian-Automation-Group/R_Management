"""Messages between the two sides of a booking, and blocks between people.

Until a booking is accepted, phone numbers, email addresses and links are
masked (and shown to both sides once it is accepted): taking a deal off the platform before it is agreed is how renters
get scammed and owners go unpaid (Airbnb and Vinted both enforce this).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, Response, status
from pydantic import Field
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.auth import Principal, is_staff, require_admin, require_principal
from cappy_common.errors import Conflict, Forbidden, Invalid, NotFound, RateLimited
from cappy_common.events import BOOKING_MESSAGE
from cappy_common.idempotency import IdempotencyKey, fingerprint, remember, replayed
from cappy_common.ids import new_id
from cappy_common.models import CamelModel, Iso
from cappy_common.pagination import Page, clamp_limit, decode_cursor, encode_cursor
from cappy_common.runtime import Tx
from cappy_common.timeutil import dt_from_iso, iso_from_datetime

from .repository import SHOWS_HANDOVER, BookingRepository
from .tables import IDEMPOTENCY, BlockRow, MessageRow

log = logging.getLogger(__name__)
router = ApiRouter()
HIDDEN = "[shared once the booking is accepted]"
MESSAGES_PER_WINDOW, MESSAGE_WINDOW = 30, timedelta(minutes=10)

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# "bob at gmail dot com", "bob(at)gmail.com", "bob [at] gmail [dot] com"
_EMAIL_SPELLED = re.compile(
    r"\b[\w.+-]+\s*(\(at\)|\[at\]|\s+at\s+)\s*[\w-]+\s*(\.|\(dot\)|\[dot\]|\s+dot\s+)\s*[a-z]{2,24}\b", re.I
)
# Links, and bare domains on any ending (example.berlin, shop.io/…).
_URL = re.compile(r"(https?://|www\.)\S+|\b[a-z0-9-]{2,}\.(?!\d)[a-z]{2,24}(/\S*)?\b", re.I)
# Dates and times are what booking conversations are about: never masked.
_DATE = re.compile(r"\b\d{1,4}[./-]\d{1,2}[./-]\d{1,4}\b|\b\d{1,2}:\d{2}\b")
# A phone number is written like one: +49…, 0049…, or 0… with 7+ digits in all.
_PHONE = re.compile(r"(?<![\w#])(\+|00|0)\d[\d\s()/.-]{5,}\d")
# A messenger name counts only with a handle or number after it.
_HANDLES = re.compile(
    r"\b(whats\s*app|telegram|signal|instagram|insta|snap(chat)?)\b\s*(me|at|on|via|:)?\s*(@[\w.]+|\+?\d[\d\s-]{5,}\d)",
    re.I,
)
# DE89 3704 0044 0532 0130 00, with or without the spaces.
_IBAN = re.compile(r"\b[a-z]{2}\d{2}(?: ?[a-z0-9]{4}){3,7}(?: ?[a-z0-9]{1,3})?\b", re.I)
# Asking to be paid around Cappy: not blocked (people ask innocently), but
# flagged on the message, warned about in the app and logged for moderation.
_OUTSIDE = re.compile(
    r"\b(pay(ing)?\s+(me\s+)?(outside|directly|in\s+cash|off[- ]?(platform|app|cappy))|paypal|"
    r"(bank|wire)\s*transfer|überweis\w*|außerhalb\s+(von\s+)?cappy|bar\s+bezahl\w*|western\s+union)",
    re.I,
)
_TOKEN = "\u0000{}\u0000"


def flagged(text: str) -> bool:
    return bool(_OUTSIDE.search(text))


def mask(text: str) -> str:
    # Set dates aside so no phone or domain rule can take them.
    kept: list[str] = []

    def keep(m: re.Match) -> str:
        kept.append(m.group(0))
        return _TOKEN.format(len(kept) - 1)

    text = _DATE.sub(keep, text)
    for pattern in (_EMAIL, _EMAIL_SPELLED, _HANDLES, _IBAN, _URL):
        text = pattern.sub(HIDDEN, text)
    text = _PHONE.sub(lambda m: HIDDEN if sum(c.isdigit() for c in m.group(0)) >= 7 else m.group(0), text)
    return re.sub("\u0000(\\d+)\u0000", lambda m: kept[int(m.group(1))], text)


class MessageIn(CamelModel):
    body: str = Field(min_length=1, max_length=2000)


class Message(CamelModel):
    id: str
    sender_id: str
    body: str
    at: Iso
    mine: bool
    # Asks to pay around Cappy: the app warns both sides.
    flagged: bool = False


def _view(row: MessageRow, viewer: str, agreed: bool) -> Message:
    return Message(
        id=row.id,
        sender_id=row.sender_id,
        # ponytail: "agreed" is the booking's status now, so contact details
        # sent before an accept hide again if it is later cancelled.
        body=row.unmasked if agreed and row.unmasked else row.body,
        at=iso_from_datetime(row.at),
        mine=row.sender_id == viewer,
        flagged=row.flagged,
    )


CLOSED = frozenset({"cancelled", "declined", "expired", "payment_failed"})


def open_for_messages(row, now: datetime) -> bool:  # noqa: ANN001
    """FL-18: a conversation stays open while the booking can still happen,
    and after it until the review window closes (questions about the return,
    a lost key); after that, and for bookings that never happened, it is
    read-only."""
    from .repository import REVIEW_WINDOW

    if row.status in CLOSED:
        return False
    return not (row.status == "completed" and row.window_end < now - REVIEW_WINDOW)


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
    key: str | None = IdempotencyKey,
) -> Message:
    fp = fingerprint(request, body)
    if (done := await replayed(session, IDEMPOTENCY, p.sub, key, fp)) is not None:
        return done
    repo = BookingRepository(session, request.app.state.outbox)
    row = await repo.visible(booking_id, p.sub)
    other = row.owner_id if p.sub == row.requester_id else row.requester_id
    if await blocked_between(session, p.sub, other):
        raise Forbidden("you cannot message this person")
    if not open_for_messages(row, datetime.now(UTC)):
        raise Conflict("this booking is closed; its conversation is read-only", code="conversation_closed")
    text = body.body.strip()
    if not text:
        raise Invalid("say something")
    # Every message can push to the other phone: a cap per sender per booking
    # (P-12). ponytail: per booking, on the (booking_id, at) index; booking
    # velocity limits already bound how many bookings one person can hold.
    since = datetime.now(UTC) - MESSAGE_WINDOW
    sent = (
        await session.execute(
            select(func.count()).where(
                MessageRow.booking_id == row.id, MessageRow.sender_id == p.sub, MessageRow.at >= since
            )
        )
    ).scalar_one()
    if sent >= MESSAGES_PER_WINDOW:
        raise RateLimited("that is a lot of messages in a few minutes; wait a little")
    agreed = row.status in SHOWS_HANDOVER
    shown = text if agreed else mask(text)
    suspicious = flagged(body.body)
    if suspicious:
        log.warning("message on %s from %s asks to pay outside Cappy", row.id, p.sub)
    msg = MessageRow(
        id=new_id("msg"),
        booking_id=row.id,
        sender_id=p.sub,
        body=shown,
        unmasked=text if shown != text else None,
        at=datetime.now(UTC),
        flagged=suspicious,
    )
    session.add(msg)
    await session.flush()
    await repo.outbox.add(
        session,
        BOOKING_MESSAGE,
        {"bookingId": row.id, "senderId": p.sub, "recipientId": other, "title": row.listing_snapshot["title"]},
    )
    request.app.state.relay.wake()
    answer = _view(msg, p.sub, agreed)
    await remember(session, IDEMPOTENCY, p.sub, key, fp, answer)
    return answer


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
    booking = await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    agreed = booking.status in SHOWS_HANDOVER
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
    return Page(items=[_view(r, p.sub, agreed) for r in rows], next_cursor=nxt)


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
    """The two sides' hand-over photos, as links that work for a few minutes
    (P-27). Staff (with MFA) see them too, to decide disputes."""
    from .tables import EvidenceRow

    try:
        await BookingRepository(session, request.app.state.outbox).visible(booking_id, p.sub)
    except NotFound:
        if not is_staff(p, request.app.state.settings):
            raise
        await require_admin(request)
    rows = (
        await session.execute(select(EvidenceRow).where(EvidenceRow.booking_id == booking_id).order_by(EvidenceRow.at))
    ).scalars()
    return [
        Evidence(
            id=r.id,
            by=r.by,
            stage=r.stage,
            photos=[_link(request, booking_id, r.id, i, photo) for i, photo in enumerate(r.photos)],
            note=r.note,
            at=iso_from_datetime(r.at),
        )
        for r in rows
    ]


# Hand-over photos are private (P-27): the list above hands out links signed
# for a few minutes, which an <img> can load with no session header. The key
# comes from booking's own internal token, which only booking holds.
LINK_TTL = 900


def _link_key(request: Request) -> bytes:
    token = request.app.state.settings.internal_token.get_secret_value() or "local"
    return hashlib.sha256(b"evidence-links:" + token.encode()).digest()


def _sig(request: Request, booking_id: str, evidence_id: str, index: int, exp: int) -> str:
    msg = f"{booking_id}:{evidence_id}:{index}:{exp}".encode()
    return hmac.new(_link_key(request), msg, hashlib.sha256).hexdigest()


def _link(request: Request, booking_id: str, evidence_id: str, index: int, photo: str) -> str:
    if not photo.startswith("evidence:"):
        return photo  # from before photos were private
    exp = int(time.time()) + LINK_TTL
    sig = _sig(request, booking_id, evidence_id, index, exp)
    return f"/api/bookings/{booking_id}/evidence/{evidence_id}/{index}?exp={exp}&sig={sig}"


@router.get("/bookings/{booking_id}/evidence/{evidence_id}/{index}", include_in_schema=False)
async def evidence_photo(
    booking_id: str, evidence_id: str, index: int, exp: int, sig: str, request: Request, session: AsyncSession = Tx
) -> Response:
    """One hand-over photo, for whoever holds a link the list above signed."""
    from .tables import EvidenceRow

    left = exp - int(time.time())
    if left <= 0 or not hmac.compare_digest(sig, _sig(request, booking_id, evidence_id, index, exp)):
        raise Forbidden("that photo link has expired; open the booking again")
    row = await session.get(EvidenceRow, evidence_id)
    if row is None or row.booking_id != booking_id or not 0 <= index < len(row.photos):
        raise NotFound("no such photo")
    name = row.photos[index].removeprefix("evidence:")
    data = await request.app.state.catalog.evidence_photo(name)
    return Response(data, media_type="image/webp", headers={"Cache-Control": f"private, max-age={min(left, LINK_TTL)}"})
