"""Which event means an email, to whom, saying what.

Delivery is at least once: the dispatcher records the event as handled in
the same transaction as nothing else, after the send. A crash between the two
sends the email again, which beats never sending it.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import (
    BOOKING_MESSAGE,
    BOOKING_STATUS_CHANGED,
    MODERATION_DECISION,
    PAYOUT_SENT,
    PROFILE_DELETED,
    REPORT_RECEIVED,
    Event,
    Handler,
)

from .mail import Directory, Email, Mailer
from .push import Pusher
from .tables import DeviceRow

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


def chat_push(event: Event, web: str) -> tuple[str, str, str] | None:
    """A new message: pushed to the other side, never emailed (a conversation
    would fill their inbox)."""
    if event.type != BOOKING_MESSAGE:
        return None
    d = event.data
    return (
        d["recipientId"],
        f"New message: {d.get('title', 'your booking')}",
        f"Open the conversation\n\n{web}/bookings/{d['bookingId']}",
    )


def moderation_mail(event: Event, web: str) -> list[tuple[str | None, str | None, str, str]]:
    """(recipient sub, or an explicit email, subject, body) for moderation.
    Acknowledging a notice and telling the reporter the outcome is DSA Art.
    16(4)/(5); telling the person affected why is Art. 17."""
    d = event.data
    if event.type == REPORT_RECEIVED:
        return [
            (
                d.get("reporterId"),
                d.get("reporterEmail"),
                "We received your report",
                f"Thank you. We will look at it and tell you what we decide.\n\nReference: {d['reportId']}",
            )
        ]
    if event.type != MODERATION_DECISION:
        return []
    out = []
    if d.get("affectedId"):
        what = {"take_down": "We removed your listing", "suspend": "We suspended your account"}.get(
            d["action"], "A decision about your account"
        )
        body = f"{d['statement']}\n\nIf you disagree, reply to this email or contact us via {web}/legal/impressum."
        out.append((d["affectedId"], None, what, body))
    if d.get("reportId") and (d.get("reporterId") or d.get("reporterEmail")):
        outcome = "we took action" if d["action"] != "dismiss" else "we found no breach of the law or our terms"
        body = f"Having looked at your report, {outcome}.\n\n{d['statement']}\n\nReference: {d['reportId']}"
        out.append((d.get("reporterId"), d.get("reporterEmail"), "Your report: our decision", body))
    return out


def handlers(directory: Directory, mailer: Mailer, web: str, pusher: Pusher | None = None) -> dict[str, Handler]:
    async def notify(session: AsyncSession, event: Event) -> None:
        if event.type in (REPORT_RECEIVED, MODERATION_DECISION):
            for sub, explicit, subject, text in moderation_mail(event, web.rstrip("/")):
                address = explicit or (await directory.email_of(sub) if sub else None)
                if address:
                    await mailer.send(Email(to=address, subject=subject, text=text))
            return
        if (chat := chat_push(event, web.rstrip("/"))) is not None:
            if pusher is not None:
                await _push(session, pusher, *chat)
            return
        for sub, subject, text in messages(event, web.rstrip("/")):
            if pusher is not None:
                await _push(session, pusher, sub, subject, text)
            address = await directory.email_of(sub)
            if address is None:
                log.info("no verified email for %s; skipping %s", sub, subject)
                continue
            await mailer.send(Email(to=address, subject=subject, text=text))

    async def forget(session: AsyncSession, event: Event) -> None:
        """Account deleted: no more pushes to their devices."""
        from sqlalchemy import delete

        await session.execute(delete(DeviceRow).where(DeviceRow.user_id == event.data["ownerId"]))

    return {
        BOOKING_STATUS_CHANGED: notify,
        PAYOUT_SENT: notify,
        BOOKING_MESSAGE: notify,
        REPORT_RECEIVED: notify,
        MODERATION_DECISION: notify,
        PROFILE_DELETED: forget,
    }


async def _push(session: AsyncSession, pusher: Pusher, sub: str, title: str, text: str) -> None:
    """To every device the person is signed in on; forget devices that are gone."""
    from sqlalchemy import select

    body, _, link = text.partition("\n\n")
    devices = (await session.execute(select(DeviceRow).where(DeviceRow.user_id == sub))).scalars()
    for device in list(devices):
        if device.endpoint and not await pusher.send(device.endpoint, title, body, link):
            log.info("device of %s is gone; forgetting it", sub)
            await session.delete(device)
