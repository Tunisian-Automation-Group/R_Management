"""Which event means an email, to whom, saying what.

Delivery is at least once: the dispatcher records the event as handled in
the same transaction as nothing else, after the send. A crash between the two
sends the email again, which beats never sending it.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime

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
from .prefs import prefs_of, wanted
from .push import Pusher
from .tables import DeviceRow, InboxRow, PrefsRow
from .texts import render

log = logging.getLogger(__name__)


Message = tuple[str | None, str | None, str, dict]  # (sub, explicit email, text key, params)


def messages(event: Event, web: str) -> list[Message]:
    """What an event should tell whom: text keys from texts.py, rendered later
    in each recipient's language."""
    d = event.data
    if event.type == PAYOUT_SENT:
        return [
            (
                d["ownerId"],
                None,
                "paid",
                {"booking": d["bookingId"], "web": web, "_cents": (d["amount"], d["currency"])},
            )
        ]
    if event.type != BOOKING_STATUS_CHANGED:
        return []
    params = {"title": d.get("title", "your booking"), "link": f"{web}/bookings/{d['bookingId']}"}
    if d["to"] == "requested":
        params["_deadline"] = d.get("expiresAt")
        if d.get("timeZone"):
            params["_tz"] = d["timeZone"]
    requester, owner, to, by = d["requesterId"], d["ownerId"], d["to"], d.get("by")
    other = owner if by == requester else requester
    who = {
        "requested": owner,
        "accepted": requester,
        "declined": requester,
        "cancelled": other,
        "expired": requester if d.get("from") == "requested" else None,
        "completed": requester,
    }.get(to)
    out: list[Message] = [(who, None, to, params)] if who else []
    if to == "accepted" and d.get("from") == "awaiting_payment":
        # Instant book: the owner never saw a request, so they hear of the booking.
        out.append((owner, None, "instant_booked", params))
    return out


def chat_push(event: Event, web: str) -> Message | None:
    """A new message: pushed to the other side, never emailed (a conversation
    would fill their inbox)."""
    if event.type != BOOKING_MESSAGE:
        return None
    d = event.data
    return (
        d["recipientId"],
        None,
        "message",
        {"title": d.get("title", "your booking"), "link": f"{web}/bookings/{d['bookingId']}"},
    )


def statement_params(d: dict) -> dict[str, str]:
    """The Art. 17 statement of reasons, in both languages (render picks one)."""
    sor = d.get("statementOfReasons") or {}
    clause = sor.get("clause") or "Terms of use: rules for listings and conduct"
    law = sor.get("ground") == "law"
    auto = bool(sor.get("automated"))
    return {
        "statement": sor.get("facts") or d["statement"],
        "ground_en": f"illegal content under {clause}" if law else f"incompatible with our terms ({clause})",
        "ground_de": f"rechtswidrige Inhalte nach {clause}" if law else f"Verstoß gegen unsere Bedingungen ({clause})",
        "automated_en": "yes" if auto else "no, by a person",
        "automated_de": "ja" if auto else "nein, von einem Menschen",
    }


def moderation_mail(event: Event, web: str) -> list[Message]:
    """Acknowledging a notice and telling the reporter the outcome is DSA Art.
    16(4)/(5); telling the person affected why is Art. 17."""
    d = event.data
    if event.type == REPORT_RECEIVED:
        return [(d.get("reporterId"), d.get("reporterEmail"), "report_received", {"report": d["reportId"]})]
    if event.type != MODERATION_DECISION:
        return []
    out: list[Message] = []
    if d.get("affectedId"):
        key = {"take_down": "taken_down", "suspend": "suspended"}.get(d["action"], "suspended")
        out.append((d["affectedId"], None, key, {"web": web, **statement_params(d)}))
    if d.get("reportId") and (d.get("reporterId") or d.get("reporterEmail")):
        key = "report_outcome_none" if d["action"] == "dismiss" else "report_outcome_action"
        out.append(
            (d.get("reporterId"), d.get("reporterEmail"), key, {"statement": d["statement"], "report": d["reportId"]})
        )
    return out


def handlers(directory: Directory, mailer: Mailer, web: str, pusher: Pusher | None = None) -> dict[str, Handler]:
    web = web.rstrip("/")

    async def deliver(
        session: AsyncSession, event: Event, msg: Message, *, email: bool = True, push: bool = True
    ) -> None:
        sub, explicit, key, params = msg
        address, locale = (explicit, None) if explicit else await directory.person_of(sub) if sub else (None, None)
        subject, text = render(key, locale, **params)
        if sub:
            await _keep(session, event, sub, key, params, subject, text, _app_path(params, web))
            want_push, want_email = wanted(await prefs_of(session, sub), key)
            push, email = push and want_push, email and want_email
        if push and pusher is not None and sub:
            await _push(session, pusher, sub, subject, text)
        if email:
            if address is None:
                log.info("no verified email for %s; skipping %s", sub, key)
                return
            await mailer.send(Email(to=address, subject=subject, text=text))

    async def notify(session: AsyncSession, event: Event) -> None:
        if event.type in (REPORT_RECEIVED, MODERATION_DECISION):
            for msg in moderation_mail(event, web):
                await deliver(session, event, msg, push=False)
            return
        if (chat := chat_push(event, web)) is not None:
            await deliver(session, event, chat, email=False)
            return
        for msg in messages(event, web):
            await deliver(session, event, msg)

    async def forget(session: AsyncSession, event: Event) -> None:
        """Account deleted: no more pushes to their devices."""
        from sqlalchemy import delete

        await session.execute(delete(DeviceRow).where(DeviceRow.user_id == event.data["ownerId"]))
        await session.execute(delete(InboxRow).where(InboxRow.user_id == event.data["ownerId"]))
        await session.execute(delete(PrefsRow).where(PrefsRow.user_id == event.data["ownerId"]))

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


def _app_path(params: dict, web: str) -> str | None:
    """Where tapping the item goes, inside the app."""
    if link := params.get("link"):
        return link.removeprefix(web) or "/"
    return "/earn" if "booking" in params else None


async def _keep(
    session: AsyncSession, event: Event, sub: str, key: str, params: dict, title: str, text: str, link: str | None
):
    """The text key and its params are kept, so the bell renders each item in
    the language it is read in (V3-13); title and body are the words as sent."""
    item_id = "ntf_" + hashlib.sha256(f"{event.id}:{sub}:{key}".encode()).hexdigest()[:32]
    if await session.get(InboxRow, item_id) is None:
        body = text.partition("\n\n")[0]
        session.add(
            InboxRow(
                id=item_id,
                user_id=sub,
                kind=key,
                params=params,
                title=title,
                body=body,
                link=link,
                at=datetime.now(UTC),
            )
        )
