"""Which event means an email, to whom, saying what.

Delivery is at least once: the dispatcher records the event as handled in
the same transaction as nothing else, after the send. A crash between the two
sends the email again, which beats never sending it.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from cappy_common.events import (
    BOOKING_MESSAGE,
    BOOKING_NOTICE,
    BOOKING_STATUS_CHANGED,
    DISPUTE_OFFER,
    LISTING_IDLE,
    MODERATION_DECISION,
    PAYOUT_SENT,
    PERSON_SIGNED_OUT,
    PROFILE_DELETED,
    REPORT_RECEIVED,
    Event,
    Handler,
)

from .mail import Directory, Email, Mailer
from .prefs import locale_of, prefs_of, wanted
from .push import Pusher, drop_devices
from .tables import DeviceRow, InboxRow, PrefsRow
from .texts import phrase, render, summary

log = logging.getLogger(__name__)


Message = tuple[str | None, str | None, str, dict]  # (sub, explicit email, text key, params)


def messages(event: Event, web: str) -> list[Message]:
    """What an event should tell whom: text keys from texts.py, rendered later
    in each recipient's language."""
    d = event.data
    if event.type == PAYOUT_SENT:
        # Named by the listing and its start, never the booking id (V5-13).
        about = {"_start": d["windowStart"]} if d.get("windowStart") else {}
        tz = {"_tz": d["timeZone"]} if d.get("timeZone") else {}
        return [
            (
                d["ownerId"],
                None,
                "paid",
                {
                    "booking": d["bookingId"],
                    "title": d.get("title") or "your booking",
                    "web": web,
                    "_cents": (d["amount"], d["currency"]),
                    **about,
                    **tz,
                },
            )
        ]
    if event.type == BOOKING_NOTICE:
        # V5-7: how a dispute ended, that we decide it now, a late-return
        # claim and its decision: each told to who the event names.
        amount = d.get("refundAmount") if "refundAmount" in d else d.get("claimAmount")
        params = {
            "title": d.get("title") or "your booking",
            "link": f"{web}/bookings/{d['bookingId']}",
            **({"_cents": (amount, d["currency"])} if amount is not None else {}),
            **({"_tz": d["timeZone"]} if d.get("timeZone") else {}),
            **SETTLED_BY[d.get("how", "staff")],
            "_note": d.get("note") or "",
        }
        # The renter reads a settlement about themselves (V7-23).
        own = d["kind"] in RENTER_READS and d.get("requesterId")
        return [(sub, None, f"{d['kind']}_renter" if own and sub == own else d["kind"], params) for sub in d["to"]]
    if event.type == LISTING_IDLE:
        # H-4: the listing has nothing free next week; adding times fixes it.
        return [
            (d["ownerId"], None, "listing_idle", {"title": d["title"], "link": f"{web}/earn/edit/{d['listingId']}"})
        ]
    if event.type == DISPUTE_OFFER:
        # S-21: the other side has 72 hours to answer an offer in a dispute.
        link = f"{web}/bookings/{d['bookingId']}"
        params = {"title": d.get("title") or "your booking", "link": link, "_cents": (d["refundAmount"], d["currency"])}
        tz = {"_tz": d["timeZone"]} if d.get("timeZone") else {}
        return [(d["to"], None, "dispute_offer", {**params, "_deadline": d.get("respondBy"), **tz})]
    if event.type != BOOKING_STATUS_CHANGED:
        return []
    if d.get("from") == "disputed":
        # A dispute settled: booking.notice says how, to both sides; a plain
        # "cancelled" or "how was it?" would contradict it (V5-7).
        return []
    params = {"title": d.get("title", "your booking"), "link": f"{web}/bookings/{d['bookingId']}"}
    if d["to"] == "declined":
        params["_reason"] = d.get("declineReason") or ""
    if d["to"] in ("requested", "accepted") and d.get("amount") is not None:
        # What the mail must say (V7-23): the booked time and the money.
        params["_cents"] = (d["amount"], d.get("currency") or "EUR")
        if d.get("windowStart"):
            params["_start"] = d["windowStart"]
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
    if to == "cancelled" and d.get("noShow") in ("owner", "renter"):
        # A no-show: both sides hear who was reported, the money, and how to
        # contest it (V6-11); the owner not turning up refunds everything.
        refunded = {"_cents": (d.get("refundAmount") or d.get("amount") or 0, d.get("currency") or "EUR")}
        if d["noShow"] == "owner":
            return [
                (requester, None, "no_show_owner_renter", {**params, **refunded}),
                (owner, None, "no_show_owner_owner", {**params, **refunded}),
            ]
        return [(owner, None, "no_show_renter_owner", params), (requester, None, "no_show_renter_renter", params)]
    if to == "cancelled" and by == "system" and d.get("extendsId"):
        # An extension that ended with its booking (V7-12): both hear why and
        # what comes back.
        back = (
            d["refundAmount"] if d.get("refundAmount") is not None else d.get("amount") or 0,
            d.get("currency") or "EUR",
        )
        return [
            (requester, None, "extension_cancelled_renter", {**params, "_cents": back}),
            (owner, None, "extension_cancelled_owner", {**params, "_cents": back}),
        ]
    if to == "requested" and d.get("extendsId"):
        return [(owner, None, "requested_extension", params)]
    if to == "cancelled" and by == owner and d.get("from") in ("accepted", "active"):
        # The owner cancelled a confirmed booking: the renter hears it was them,
        # and how much comes back (V6-11).
        back = d["refundAmount"] if d.get("refundAmount") is not None else d.get("amount") or 0
        return [(requester, None, "owner_cancelled", {**params, "_cents": (back, d.get("currency") or "EUR")})]
    out: list[Message] = [(who, None, to, params)] if who else []
    if to == "accepted" and d.get("from") == "awaiting_payment":
        # Instant book: the owner never saw a request, so they hear of the booking.
        out.append((owner, None, "instant_booked", params))
    if to == "payment_failed":
        # The card step failed: only the renter knew. A capture declined at
        # accept: the owner had said yes, so both hear it is off (FL-2).
        out.append((requester, None, "payment_failed", params))
        if d.get("from") == "accepted":
            out.append((owner, None, "payment_failed", params))
    if to == "disputed":
        out += [(owner, None, "disputed_owner", params), (requester, None, "disputed_renter", params)]
    return out


# Settlement notices with a text the renter reads about themselves.
RENTER_READS = frozenset({"dispute_refunded", "dispute_partial", "dispute_owner_paid"})

# Who settled a dispute, in each language (the text picks its own).
SETTLED_BY = {
    "agreement": {
        "how_en": "You agreed a settlement:",
        "how_de": "Ihr habt euch geeinigt:",
        "how_fr": "Vous vous êtes mis d’accord\u00a0:",
    },
    "staff": {"how_en": "Cappy decided:", "how_de": "Cappy hat entschieden:", "how_fr": "Cappy a décidé\u00a0:"},
}

MESSAGE_EMAIL_EVERY = timedelta(minutes=15)


async def _recently_told(session: AsyncSession, sub: str | None, link: str | None) -> bool:
    """Whether this conversation already reached them in the last 15 minutes
    (the inbox holds every message notice it sent)."""
    from sqlalchemy import select

    if not sub:
        return False
    since = datetime.now(UTC) - MESSAGE_EMAIL_EVERY
    q = select(InboxRow.id).where(
        InboxRow.user_id == sub, InboxRow.kind == "message", InboxRow.link == link, InboxRow.at > since
    )
    return (await session.execute(q.limit(1))).first() is not None


def chat_push(event: Event, web: str) -> Message | None:
    """A new message: pushed to the other side, and emailed unless the
    conversation already emailed them in the last 15 minutes."""
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
    clause = sor.get("clause") or ""
    clauses = {
        lang: clause or phrase("Terms of use: rules for listings and conduct", lang) for lang in ("en", "de", "fr")
    }
    law = sor.get("ground") == "law"
    auto = bool(sor.get("automated"))
    return {
        "statement": sor.get("facts") or d["statement"],
        "ground_en": f"illegal content under {clauses['en']}"
        if law
        else f"incompatible with our terms ({clauses['en']})",
        "ground_de": f"rechtswidrige Inhalte nach {clauses['de']}"
        if law
        else f"Verstoß gegen unsere Bedingungen ({clauses['de']})",
        "ground_fr": f"contenu illicite au titre de {clauses['fr']}"
        if law
        else f"contraire à nos conditions ({clauses['fr']})",
        "automated_en": "yes" if auto else "no, by a person",
        "automated_de": "ja" if auto else "nein, von einem Menschen",
        "automated_fr": "oui" if auto else "non, par une personne",
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
        key = {"take_down": "taken_down", "suspend": "suspended", "remove_content": "content_removed"}[d["action"]]
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
        # The reader's own locale, as their app last said it; never the
        # triggering person's (V6-6).
        locale = (await locale_of(session, sub) if sub else None) or locale
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
            # Pushed every time; emailed at most once a conversation every 15
            # minutes, so a lively chat is one email, not twenty (FL-3).
            quiet = not await _recently_told(session, chat[0], _app_path(chat[3], web))
            await deliver(session, event, chat, email=quiet)
            return
        for msg in messages(event, web):
            await deliver(session, event, msg)

    async def _drop_all(session: AsyncSession, sub: str) -> None:
        from sqlalchemy import select

        rows = (await session.execute(select(DeviceRow).where(DeviceRow.user_id == sub))).scalars()
        if pusher is not None:
            await drop_devices(session, pusher, rows)
        else:
            for row in list(rows):
                await session.delete(row)

    async def forget(session: AsyncSession, event: Event) -> None:
        """Account deleted: no more pushes to their devices, and the sign-in
        itself goes, so the email address is not kept in Cognito (P-23)."""
        from sqlalchemy import delete

        await directory.delete_person(event.data["ownerId"])
        await _drop_all(session, event.data["ownerId"])
        await session.execute(delete(InboxRow).where(InboxRow.user_id == event.data["ownerId"]))
        await session.execute(delete(PrefsRow).where(PrefsRow.user_id == event.data["ownerId"]))

    async def signed_out(session: AsyncSession, event: Event) -> None:
        """Sign out everywhere (catalog took the request): every refresh token
        revoked in Cognito, and no device gets their pushes any more."""

        await directory.sign_out_everywhere(event.data["personId"])
        await _drop_all(session, event.data["personId"])

    return {
        PERSON_SIGNED_OUT: signed_out,
        BOOKING_STATUS_CHANGED: notify,
        PAYOUT_SENT: notify,
        BOOKING_MESSAGE: notify,
        REPORT_RECEIVED: notify,
        MODERATION_DECISION: notify,
        LISTING_IDLE: notify,
        DISPUTE_OFFER: notify,
        BOOKING_NOTICE: notify,
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
            await drop_devices(session, pusher, [device])


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
        # The column holds 2000; the bell renders from params anyway.
        body = summary(key, text)[:2000]
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
