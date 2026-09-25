"""Every email and push, in English and German (the first market). Rendered
in the recipient's language: Cognito's `locale` attribute, which the app sets."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from cappy_common.timeutil import dt_from_iso

TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "paid": (
            "You have been paid {amount}",
            "Your share for booking {booking} is on its way to your bank.\n\n{web}/earn",
        ),
        "requested": (
            "New request: {title}",
            "Someone wants to book {title}. Answer by {deadline}, or the request lapses.\n\n{link}",
        ),
        "accepted": ("Confirmed: {title}", "Your booking of {title} is confirmed.\n\n{link}"),
        "instant_booked": (
            "New booking: {title}",
            "{title} was booked instantly. The details are in the app.\n\n{link}",
        ),
        "declined": ("Declined: {title}", "Your request for {title} was declined. Nothing was charged.\n\n{link}"),
        "cancelled": ("Cancelled: {title}", "The booking of {title} was cancelled.\n\n{link}"),
        "expired": ("Expired: {title}", "Your request for {title} lapsed. Nothing was charged.\n\n{link}"),
        "completed": ("How was {title}?", "Your booking is complete. Rate it to help the next buyer.\n\n{link}"),
        "message": ("New message: {title}", "Open the conversation\n\n{link}"),
        "report_received": (
            "We received your report",
            "Thank you. We will look at it and tell you what we decide.\n\nReference: {report}",
        ),
        "taken_down": (
            "We removed your listing",
            "Your listing can no longer be seen or booked.\n\nWhy: {statement}\nGround: {ground_en}\nDecided by automated means: {automated_en}\n\nWhat you can do: contest this decision by replying to this email within 6 months; someone who was not involved will look at it again. You can also turn to a certified out-of-court dispute settlement body (DSA Art. 21) or to the courts. Contact: {web}/legal/impressum",
        ),
        "suspended": (
            "We suspended your account",
            "Your listings were removed, and you can no longer list or book.\n\nWhy: {statement}\nGround: {ground_en}\nDecided by automated means: {automated_en}\n\nWhat you can do: contest this decision by replying to this email within 6 months; someone who was not involved will look at it again. You can also turn to a certified out-of-court dispute settlement body (DSA Art. 21) or to the courts. Contact: {web}/legal/impressum",
        ),
        "report_outcome_action": (
            "Your report: our decision",
            "Having looked at your report, we took action.\n\n{statement}\n\nReference: {report}",
        ),
        "report_outcome_none": (
            "Your report: our decision",
            "Having looked at your report, we found no breach of the law or our terms.\n\n{statement}\n\nReference: {report}",
        ),
    },
    "de": {
        "paid": (
            "Du hast {amount} erhalten",
            "Dein Anteil für die Buchung {booking} ist auf dem Weg zu deiner Bank.\n\n{web}/earn",
        ),
        "requested": (
            "Neue Anfrage: {title}",
            "Jemand möchte {title} buchen. Bitte antworte bis {deadline}, sonst verfällt die Anfrage.\n\n{link}",
        ),
        "accepted": ("Bestätigt: {title}", "Deine Buchung von {title} ist bestätigt.\n\n{link}"),
        "instant_booked": (
            "Neue Buchung: {title}",
            "{title} wurde sofort gebucht. Alle Details findest du in der App.\n\n{link}",
        ),
        "declined": (
            "Abgelehnt: {title}",
            "Deine Anfrage für {title} wurde abgelehnt. Es wurde nichts berechnet.\n\n{link}",
        ),
        "cancelled": ("Storniert: {title}", "Die Buchung von {title} wurde storniert.\n\n{link}"),
        "expired": (
            "Abgelaufen: {title}",
            "Deine Anfrage für {title} ist abgelaufen. Es wurde nichts berechnet.\n\n{link}",
        ),
        "completed": (
            "Wie war {title}?",
            "Deine Buchung ist abgeschlossen. Bewerte sie und hilf der nächsten Person.\n\n{link}",
        ),
        "message": ("Neue Nachricht: {title}", "Zum Gespräch\n\n{link}"),
        "report_received": (
            "Wir haben deine Meldung erhalten",
            "Danke. Wir prüfen sie und teilen dir unsere Entscheidung mit.\n\nAktenzeichen: {report}",
        ),
        "taken_down": (
            "Wir haben dein Inserat entfernt",
            "Dein Inserat ist nicht mehr sichtbar und kann nicht mehr gebucht werden.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; jemand, der nicht beteiligt war, prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
        ),
        "suspended": (
            "Wir haben dein Konto gesperrt",
            "Deine Inserate wurden entfernt, und du kannst nichts mehr inserieren oder buchen.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; jemand, der nicht beteiligt war, prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
        ),
        "report_outcome_action": (
            "Deine Meldung: unsere Entscheidung",
            "Wir haben deine Meldung geprüft und Maßnahmen ergriffen.\n\n{statement}\n\nAktenzeichen: {report}",
        ),
        "report_outcome_none": (
            "Deine Meldung: unsere Entscheidung",
            "Wir haben deine Meldung geprüft und keinen Verstoß gegen Recht oder unsere Bedingungen festgestellt.\n\n{statement}\n\nAktenzeichen: {report}",
        ),
    },
}


def language(locale: str | None) -> str:
    """de-DE, de_AT, de → de; anything else → en."""
    return "de" if (locale or "").lower().startswith("de") else "en"


def render(key: str, locale: str | None, **params) -> tuple[str, str]:
    """Raw params (``_cents``, ``_deadline``, ``_tz``) are put in the reader's words here,
    so an inbox item stored once reads right in whichever language it is read."""
    params = dict(params)
    if "_cents" in params:
        params["amount"] = money(*params.pop("_cents"), locale)
    zone = params.pop("_tz", None) or DEFAULT_TIME_ZONE
    if "_deadline" in params:
        at = params.pop("_deadline")
        params["deadline"] = (
            when(dt_from_iso(at), locale, zone)
            if at
            else ("the booked start" if language(locale) == "en" else "zum gebuchten Beginn")
        )
    subject, body = TEXTS[language(locale)][key]
    return subject.format(**params), body.format(**params)


# Times are told in the listing's zone when the event carries one
# (``timeZone``). ponytail: listings have no zone yet (Germany only), so Berlin.
DEFAULT_TIME_ZONE = "Europe/Berlin"
_DAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "de": ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."],
}
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def when(t: datetime, locale: str | None, zone: str = DEFAULT_TIME_ZONE) -> str:
    """Sat 26 Sep, 14:00 · Sa., 26.09., 14:00 Uhr"""
    t, lang = t.astimezone(ZoneInfo(zone)), language(locale)
    day = _DAYS[lang][t.weekday()]
    if lang == "de":
        return f"{day}, {t:%d.%m.}, {t:%H:%M} Uhr"
    return f"{day} {t.day} {_MONTHS[t.month - 1]}, {t:%H:%M}"


def money(cents: int, currency: str, locale: str | None) -> str:
    symbol = {"eur": "€", "gbp": "£", "usd": "$"}.get(currency, currency.upper() + " ")
    if language(locale) == "de":
        whole = f"{cents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{whole} {symbol}"
    return f"{symbol}{cents / 100:,.2f}"
