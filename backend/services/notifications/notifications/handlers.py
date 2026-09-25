"""Which event means an email, to whom, saying what.

Delivery is at least once: the dispatcher records the event as handled in
the same transaction as nothing else, after the send. A crash between the two
sends the email again, which beats never sending it.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import BOOKING_STATUS_CHANGED, PAYOUT_SENT, Event, Handler

from .mail import Directory, Email, Mailer

log = logging.getLogger(__name__)


def _money(cents: int, currency: str) -> str:
    symbol = {"eur": "€", "gbp": "£", "usd": "$"}.get(currency, currency.upper() + " ")
    return f"{symbol}{cents / 100:,.2f}"


def messages(event: Event, web: str) -> list[tuple[str, str, str]]:
    """(recipient sub, subject, body) for each email an event should send."""
    d = event.data
    if event.type == PAYOUT_SENT:
        return [
            (
                d["ownerId"],
                f"You have been paid {_money(d['amount'], d['currency'])}",
                f"Your share for booking {d['bookingId']} is on its way to your bank.\n\n{web}/earn",
            )
        ]
    if event.type != BOOKING_STATUS_CHANGED:
        return []
    title = d.get("title", "your booking")
    link = f"{web}/bookings/{d['bookingId']}"
    requester, owner, to, by = d["requesterId"], d["ownerId"], d["to"], d.get("by")
    other = owner if by == requester else requester
    table = {
        "requested": [
            (owner, f"New request: {title}", f"Someone wants to book {title}. Answer within a day.\n\n{link}")
        ],
        "accepted": [(requester, f"Confirmed: {title}", f"Your booking of {title} is confirmed.\n\n{link}")],
        "declined": [
            (requester, f"Declined: {title}", f"Your request for {title} was declined. Nothing was charged.\n\n{link}")
        ],
        "cancelled": [(other, f"Cancelled: {title}", f"The booking of {title} was cancelled.\n\n{link}")],
        "expired": [
            (requester, f"Expired: {title}", f"Your request for {title} lapsed. Nothing was charged.\n\n{link}")
        ]
        if d.get("from") == "requested"
        else [],
        "completed": [
            (requester, f"How was {title}?", f"Your booking is complete. Rate it to help the next buyer.\n\n{link}")
        ],
    }
    return table.get(to, [])


def handlers(directory: Directory, mailer: Mailer, web: str) -> dict[str, Handler]:
    async def notify(_session: AsyncSession, event: Event) -> None:
        for sub, subject, text in messages(event, web.rstrip("/")):
            address = await directory.email_of(sub)
            if address is None:
                log.info("no verified email for %s; skipping %s", sub, subject)
                continue
            await mailer.send(Email(to=address, subject=subject, text=text))

    return {BOOKING_STATUS_CHANGED: notify, PAYOUT_SENT: notify}
