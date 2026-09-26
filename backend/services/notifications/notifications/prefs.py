"""What someone chose to hear about, per category and channel.

The bell always gets everything. Some emails are sent whatever the setting,
because they are the record of a contract or of money, or the law requires
them: a booking confirmed, declined, lapsed or cancelled (the confirmation on
a durable medium, § 312f BGB, and what happened to the money), and every
moderation email (DSA Art. 16/17).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.models import CamelModel

from .tables import PrefsRow


class Channels(CamelModel):
    push: bool
    email: bool


class Categories(CamelModel):
    bookings: Channels
    messages: Channels
    payouts: Channels
    marketing: Channels


class Prefs(CamelModel):
    categories: Categories


DEFAULTS = Prefs(
    categories=Categories(
        bookings=Channels(push=True, email=True),
        messages=Channels(push=True, email=True),
        payouts=Channels(push=True, email=True),
        # Marketing needs a yes first (§ 7 UWG); Cappy sends none today.
        marketing=Channels(push=False, email=False),
    )
)

CATEGORY = {
    "requested": "bookings",
    "accepted": "bookings",
    "instant_booked": "bookings",
    "declined": "bookings",
    "cancelled": "bookings",
    "expired": "bookings",
    "completed": "bookings",
    "payment_failed": "bookings",
    "disputed_owner": "bookings",
    "disputed_renter": "bookings",
    "listing_idle": "bookings",
    "message": "messages",
    "paid": "payouts",
}
ALWAYS_EMAILED = frozenset(
    {
        "accepted",
        "instant_booked",
        "declined",
        "cancelled",
        "expired",
        "payment_failed",
        "disputed_owner",
        "disputed_renter",
    }
)


async def prefs_of(session: AsyncSession, user_id: str) -> Prefs:
    row = await session.get(PrefsRow, user_id)
    return Prefs.model_validate(row.prefs) if row else DEFAULTS


async def save(session: AsyncSession, user_id: str, prefs: Prefs) -> Prefs:
    data = prefs.model_dump(mode="json", by_alias=True)
    row = await session.get(PrefsRow, user_id)
    if row is None:
        session.add(PrefsRow(user_id=user_id, prefs=data, updated_at=datetime.now(UTC)))
    else:
        row.prefs, row.updated_at = data, datetime.now(UTC)
    return prefs


def wanted(prefs: Prefs, key: str) -> tuple[bool, bool]:
    """(push, email) for a text key. Keys outside the categories (moderation)
    always go by email and never by push."""
    category = CATEGORY.get(key)
    if category is None:
        return False, True
    ch: Channels = getattr(prefs.categories, category)
    return ch.push, ch.email or key in ALWAYS_EMAILED
