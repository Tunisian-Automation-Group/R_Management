from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request, Response, status
from pydantic import Field, TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.app import ApiRouter
from cappy_common.errors import Conflict, Invalid, NotFound
from cappy_common.events import BOOKING_RATED, BOOKING_REQUESTED, BOOKING_STATUS_CHANGED
from cappy_common.ids import new_id
from cappy_common.models import Booking, CamelModel, Iso, Match, Outcome, Requirement
from cappy_common.timeutil import iso_from_ms, now_iso, now_ms

from .state import Action, check_can_rate, next_status
from .tables import BookingRow

router = ApiRouter()
_requirement = TypeAdapter(Requirement)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.session() as session:
        async with session.begin():
            yield session


def current_user(request: Request) -> str:
    return request.app.state.current_user(request.headers.get("x-cappy-user"))


def to_booking(row: BookingRow, viewer: str) -> Booking:
    """The frontend's ``Booking``. ``requesterId`` is absent when the viewer is
    the requester, present when someone is asking *them*: that presence is what
    the app's Earn inbox keys on."""
    return Booking(
        id=row.id,
        match=Match.model_validate(row.match),
        requirement=_requirement.validate_python(row.requirement),
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        requester_id=None if row.requester_id == viewer else row.requester_id,
        decline_reason=row.decline_reason,
        outcome=Outcome.model_validate(row.outcome) if row.outcome else None,
    )


async def _load(session: AsyncSession, booking_id: str) -> BookingRow:
    row = await session.get(BookingRow, booking_id, with_for_update=True)
    if not row:
        raise NotFound(f"booking {booking_id} not found")
    return row


class CreateBookingIn(CamelModel):
    requirement: Requirement
    listing_id: str
    slot_id: str
    start: Iso
    end: Iso
    # Optional, client-generated, like a listing's. The app navigates to the
    # booking it just built before the server has answered, so the id it chose
    # is kept rather than replaced. Must look like ours; must be new.
    id: str | None = Field(default=None, pattern=r"^bk_[a-z0-9]{6,40}$")


class DeclineIn(CamelModel):
    reason: str


@router.get("/bookings", response_model=list[Booking])
async def list_bookings(
    session: AsyncSession = Depends(get_session), user: str = Depends(current_user)
) -> list[Booking]:
    """Everything the caller asked for or is being asked for, newest first."""
    q = (
        select(BookingRow)
        .where(or_(BookingRow.requester_id == user, BookingRow.owner_id == user))
        .order_by(BookingRow.created_at.desc(), BookingRow.id)
    )
    return [to_booking(r, user) for r in (await session.execute(q)).scalars()]


@router.get("/bookings/{booking_id}", response_model=Booking)
async def get_booking(
    booking_id: str, session: AsyncSession = Depends(get_session), user: str = Depends(current_user)
) -> Booking:
    row = await session.get(BookingRow, booking_id)
    if not row or user not in (row.requester_id, row.owner_id):
        raise NotFound(f"booking {booking_id} not found")
    return to_booking(row, user)


@router.post("/bookings", response_model=Booking, status_code=status.HTTP_201_CREATED)
async def create_booking(
    body: CreateBookingIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    settings = request.app.state.settings
    # The quote is computed by the matching service, never trusted from the client.
    match = await request.app.state.matching.match_for_offer(
        body.requirement, body.listing_id, body.slot_id, body.start, body.end
    )
    if match.owner_id == user:
        raise Invalid("you cannot book your own listing")
    if body.id and await session.get(BookingRow, body.id):
        raise Conflict(f"booking {body.id} already exists")

    now = now_iso()
    simulate = settings.demo_auto_accept_seconds > 0 and match.owner_id != settings.demo_user_id
    row = BookingRow(
        id=body.id or new_id("bk"),
        requester_id=user,
        owner_id=match.owner_id,
        listing_id=match.listing_id,
        status="requested",
        created_at=now,
        updated_at=now,
        requirement=body.requirement.model_dump(mode="json", by_alias=True),
        match=match.model_dump(mode="json", by_alias=True),
        auto_accept_at=(iso_from_ms(now_ms() + int(settings.demo_auto_accept_seconds * 1000)) if simulate else None),
    )
    session.add(row)
    await session.flush()
    await request.app.state.bus.publish(
        BOOKING_REQUESTED,
        {"bookingId": row.id, "requesterId": user, "ownerId": row.owner_id, "listingId": row.listing_id},
    )
    return to_booking(row, user)


async def _transition(
    request: Request, session: AsyncSession, booking_id: str, action: Action, user: str, **extra
) -> Booking:
    row = await _load(session, booking_id)
    before = row.status
    row.status = next_status(action, row.status, user, row.requester_id, row.owner_id)
    row.updated_at = now_iso()
    row.auto_accept_at = None
    for k, v in extra.items():
        setattr(row, k, v)
    await session.flush()
    await request.app.state.bus.publish(
        BOOKING_STATUS_CHANGED,
        {"bookingId": row.id, "from": before, "to": row.status, "by": user},
    )
    return to_booking(row, user)


@router.post("/bookings/{booking_id}/accept", response_model=Booking)
async def accept(
    booking_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    return await _transition(request, session, booking_id, "accept", user)


@router.post("/bookings/{booking_id}/decline", response_model=Booking)
async def decline(
    booking_id: str,
    body: DeclineIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    reason = body.reason.strip()
    if not reason:
        raise Invalid("tell the buyer why, rather than just refusing")
    return await _transition(request, session, booking_id, "decline", user, decline_reason=reason)


@router.post("/bookings/{booking_id}/start", response_model=Booking)
async def start(
    booking_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    return await _transition(request, session, booking_id, "start", user)


@router.post("/bookings/{booking_id}/complete", response_model=Booking)
async def complete(
    booking_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    return await _transition(request, session, booking_id, "complete", user)


@router.post("/bookings/{booking_id}/cancel", response_model=Booking)
async def cancel(
    booking_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    return await _transition(request, session, booking_id, "cancel", user)


@router.post("/bookings/{booking_id}/rate", response_model=Booking)
async def rate(
    booking_id: str,
    outcome: Outcome,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: str = Depends(current_user),
) -> Booking:
    """The write half of the loop. Publishes ``booking.rated``; the catalog folds
    it into the owner's record, which moves where they rank for everyone, and
    writes it up as a review on the listing, which the next buyer reads.

    A review is dated at the end of the booked window, as the app does, not at
    the moment the buyer got round to rating it."""
    row = await _load(session, booking_id)
    check_can_rate(row.status, row.outcome is not None, user, row.requester_id)
    row.outcome = outcome.model_dump(mode="json", by_alias=True, exclude_none=True)
    row.updated_at = now_iso()
    await session.flush()
    await request.app.state.bus.publish(
        BOOKING_RATED,
        {
            "bookingId": row.id,
            "ownerId": row.owner_id,
            "listingId": row.listing_id,
            "requesterId": row.requester_id,
            "outcome": row.outcome,
            "at": row.match["end"],
            "ratedAt": row.updated_at,
        },
    )
    return to_booking(row, user)


@router.post("/admin/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    """Demo only: forget every booking and put the seeded inbox request back."""
    from .workers import seed_inbox, wipe_bookings

    await session.commit()
    await wipe_bookings(request.app)
    await seed_inbox(request.app)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
