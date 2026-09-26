"""What someone chose to hear about, per category and channel.

The bell always gets everything. Some emails are sent whatever the setting,
because they are the record of a contract or of money, or the law requires
them: a booking confirmed, declined, lapsed or cancelled (the confirmation on
a durable medium, § 312f BGB, and what happened to the money), and every
moderation email (DSA Art. 16/17).
"""

from __future__ import annotations

import re
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
    "requested_extension": "bookings",
    "extension_cancelled_renter": "bookings",
    "extension_cancelled_owner": "bookings",
    "dispute_refunded_renter": "bookings",
    "dispute_partial_renter": "bookings",
    "dispute_owner_paid_renter": "bookings",
    "instant_booked": "bookings",
    "declined": "bookings",
    "cancelled": "bookings",
    "owner_cancelled": "bookings",
    "no_show_owner_renter": "bookings",
    "no_show_owner_owner": "bookings",
    "no_show_renter_owner": "bookings",
    "no_show_renter_renter": "bookings",
    "expired": "bookings",
    "completed": "bookings",
    "payment_failed": "bookings",
    "disputed_owner": "bookings",
    "disputed_renter": "bookings",
    "listing_idle": "bookings",
    "dispute_offer": "bookings",
    "dispute_refunded": "bookings",
    "dispute_partial": "bookings",
    "dispute_owner_paid": "bookings",
    "dispute_escalated": "bookings",
    "claim_filed": "bookings",
    "claim_confirmed": "bookings",
    "claim_rejected": "bookings",
    "message": "messages",
    "paid": "payouts",
}
ALWAYS_EMAILED = frozenset(
    {
        "accepted",
        "instant_booked",
        "declined",
        "cancelled",
        # A cancellation or a no-show says what happens to the money (V6-11).
        "owner_cancelled",
        "no_show_owner_renter",
        "no_show_owner_owner",
        "no_show_renter_owner",
        "no_show_renter_renter",
        "expired",
        "payment_failed",
        "disputed_owner",
        "disputed_renter",
        # How a dispute or a claim about money ended is part of the contract,
        # not a nudge: always emailed.
        "dispute_refunded",
        "dispute_partial",
        "dispute_owner_paid",
        "dispute_refunded_renter",
        "dispute_partial_renter",
        "dispute_owner_paid_renter",
        "extension_cancelled_renter",
        "extension_cancelled_owner",
        "claim_confirmed",
        "claim_rejected",
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


_LOCALE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8}){0,3}$")


async def seen_locale(session: AsyncSession, user_id: str, header: str | None) -> None:
    """Remember the app's locale (its ``Accept-Language``), so emails follow the
    reader, not whoever caused them (V6-6). Written only when it changes."""
    tag = (header or "").split(",")[0].split(";")[0].strip()
    if not _LOCALE.match(tag):
        return
    row = await session.get(PrefsRow, user_id)
    if row is None:
        session.add(
            PrefsRow(
                user_id=user_id,
                prefs=DEFAULTS.model_dump(mode="json", by_alias=True),
                updated_at=datetime.now(UTC),
                locale=tag,
            )
        )
    elif row.locale != tag:
        row.locale = tag


async def locale_of(session: AsyncSession, user_id: str) -> str | None:
    row = await session.get(PrefsRow, user_id)
    return row.locale if row else None
