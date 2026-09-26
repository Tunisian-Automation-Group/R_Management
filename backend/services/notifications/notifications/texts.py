"""Every email and push, in English, German and French (France and Québec:
neutral French, « courriel »). Rendered in the recipient's language, Cognito's
`locale` attribute, which the app sets; any other language gets English."""

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
        "listing_idle": (
            "No free time next week: {title}",
            "{title} has no free time in the next seven days, so nobody can book it. Add opening hours or windows to keep it bookable.\n\n{link}",
        ),
        "message": ("New message: {title}", "Open the conversation\n\n{link}"),
        "payment_failed": (
            "Payment failed: {title}",
            "The card could not be charged, so the booking of {title} is off. Nothing was taken.\n\n{link}",
        ),
        "disputed_owner": (
            "A problem was reported: {title}",
            "The renter reported a problem with {title}. Your payout waits while we look at it; we will be in touch.\n\n{link}",
        ),
        "disputed_renter": (
            "We received your report: {title}",
            "Thank you. We will look at what happened with {title} and tell you what we decide.\n\n{link}",
        ),
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
        "content_removed": (
            "We removed something you wrote",
            "A message or review of yours was removed. Your account is not otherwise restricted.\n\nWhy: {statement}\nGround: {ground_en}\nDecided by automated means: {automated_en}\n\nWhat you can do: contest this decision by replying to this email within 6 months; someone who was not involved will look at it again. You can also turn to a certified out-of-court dispute settlement body (DSA Art. 21) or to the courts. Contact: {web}/legal/impressum",
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
        "listing_idle": (
            "Nächste Woche nichts frei: {title}",
            "{title} hat in den nächsten sieben Tagen keine freie Zeit, deshalb kann es niemand buchen. Füge Öffnungszeiten oder Zeitfenster hinzu, damit es buchbar bleibt.\n\n{link}",
        ),
        "message": ("Neue Nachricht: {title}", "Zum Gespräch\n\n{link}"),
        "payment_failed": (
            "Zahlung fehlgeschlagen: {title}",
            "Die Karte konnte nicht belastet werden, deshalb findet die Buchung von {title} nicht statt. Es wurde nichts abgebucht.\n\n{link}",
        ),
        "disputed_owner": (
            "Ein Problem wurde gemeldet: {title}",
            "Die mietende Person hat ein Problem mit {title} gemeldet. Deine Auszahlung wartet, bis wir es geprüft haben; wir melden uns.\n\n{link}",
        ),
        "disputed_renter": (
            "Wir haben deine Meldung erhalten: {title}",
            "Danke. Wir prüfen, was bei {title} passiert ist, und teilen dir unsere Entscheidung mit.\n\n{link}",
        ),
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
        "content_removed": (
            "Wir haben einen Beitrag von dir entfernt",
            "Eine Nachricht oder Bewertung von dir wurde entfernt. Dein Konto ist sonst nicht eingeschränkt.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; jemand, der nicht beteiligt war, prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
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
    "fr": {
        "paid": (
            "Vous avez reçu {amount}",
            "Votre part pour la réservation {booking} est en route vers votre banque.\n\n{web}/earn",
        ),
        "requested": (
            "Nouvelle demande : {title}",
            "Quelqu’un souhaite réserver {title}. Répondez avant {deadline}, sinon la demande expire.\n\n{link}",
        ),
        "accepted": ("Confirmé : {title}", "Votre réservation de {title} est confirmée.\n\n{link}"),
        "instant_booked": (
            "Nouvelle réservation : {title}",
            "{title} a été réservé instantanément. Tous les détails sont dans l’application.\n\n{link}",
        ),
        "declined": (
            "Refusée : {title}",
            "Votre demande pour {title} a été refusée. Rien n’a été facturé.\n\n{link}",
        ),
        "cancelled": ("Annulée : {title}", "La réservation de {title} a été annulée.\n\n{link}"),
        "expired": (
            "Expirée : {title}",
            "Votre demande pour {title} a expiré. Rien n’a été facturé.\n\n{link}",
        ),
        "completed": (
            "Comment s’est passé {title}?",
            "Votre réservation est terminée. Évaluez-la pour aider la prochaine personne.\n\n{link}",
        ),
        "listing_idle": (
            "Aucun créneau libre la semaine prochaine : {title}",
            "{title} n’a aucun créneau libre dans les sept prochains jours : personne ne peut le réserver. Ajoutez des horaires d’ouverture ou des créneaux pour qu’il reste réservable.\n\n{link}",
        ),
        "message": ("Nouveau message : {title}", "Ouvrir la conversation\n\n{link}"),
        "payment_failed": (
            "Paiement refusé : {title}",
            "La carte n’a pas pu être débitée, la réservation de {title} n’a donc pas lieu. Rien n’a été prélevé.\n\n{link}",
        ),
        "disputed_owner": (
            "Un problème a été signalé : {title}",
            "La personne locataire a signalé un problème avec {title}. Votre versement attend notre examen ; nous vous recontacterons.\n\n{link}",
        ),
        "disputed_renter": (
            "Nous avons reçu votre signalement : {title}",
            "Merci. Nous examinons ce qui s’est passé avec {title} et vous communiquerons notre décision.\n\n{link}",
        ),
        "report_received": (
            "Nous avons reçu votre signalement",
            "Merci. Nous allons l’examiner et vous communiquerons notre décision.\n\nRéférence : {report}",
        ),
        "taken_down": (
            "Nous avons retiré votre annonce",
            "Votre annonce n’est plus visible et ne peut plus être réservée.\n\nMotif : {statement}\nFondement : {ground_fr}\nDécision automatisée : {automated_fr}\n\nCe que vous pouvez faire : contester cette décision en répondant à ce courriel dans un délai de 6 mois ; une personne qui n’y a pas participé la réexaminera. Vous pouvez aussi vous adresser à un organisme certifié de règlement extrajudiciaire des litiges (DSA art. 21) ou aux tribunaux. Contact : {web}/legal/impressum",
        ),
        "suspended": (
            "Nous avons suspendu votre compte",
            "Vos annonces ont été retirées et vous ne pouvez plus publier ni réserver.\n\nMotif : {statement}\nFondement : {ground_fr}\nDécision automatisée : {automated_fr}\n\nCe que vous pouvez faire : contester cette décision en répondant à ce courriel dans un délai de 6 mois ; une personne qui n’y a pas participé la réexaminera. Vous pouvez aussi vous adresser à un organisme certifié de règlement extrajudiciaire des litiges (DSA art. 21) ou aux tribunaux. Contact : {web}/legal/impressum",
        ),
        "content_removed": (
            "Nous avons retiré l’un de vos contenus",
            "Un message ou un avis de votre part a été retiré. Votre compte n’est pas restreint par ailleurs.\n\nMotif\u00a0: {statement}\nFondement\u00a0: {ground_fr}\nDécision automatisée\u00a0: {automated_fr}\n\nCe que vous pouvez faire\u00a0: contester cette décision en répondant à ce courriel dans un délai de 6 mois ; une personne qui n’y a pas participé la réexaminera. Vous pouvez aussi vous adresser à un organisme certifié de règlement extrajudiciaire des litiges (DSA art. 21) ou aux tribunaux. Contact\u00a0: {web}/legal/impressum",
        ),
        "report_outcome_action": (
            "Votre signalement : notre décision",
            "Après examen de votre signalement, nous avons pris des mesures.\n\n{statement}\n\nRéférence : {report}",
        ),
        "report_outcome_none": (
            "Votre signalement : notre décision",
            "Après examen de votre signalement, nous n’avons constaté aucune infraction à la loi ou à nos conditions.\n\n{statement}\n\nRéférence : {report}",
        ),
    },
}


def language(locale: str | None) -> str:
    """de-DE, de_AT, de → de; fr-FR, fr-CA → fr; anything else → en."""
    code = (locale or "").lower()[:2]
    return code if code in ("de", "fr") else "en"


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
            else {"en": "the booked start", "de": "zum gebuchten Beginn", "fr": "le début réservé"}[language(locale)]
        )
    subject, body = TEXTS[language(locale)][key]
    return subject.format(**params), body.format(**params)


# Times are told in the listing's zone when the event carries one
# (``timeZone``). ponytail: listings have no zone yet (Germany only), so Berlin.
DEFAULT_TIME_ZONE = "Europe/Berlin"
_DAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "de": ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."],
    "fr": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
}
_MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# English readers whose region writes the 12-hour clock (the app sends its
# BCP 47 locale, e.g. en-US); everyone else reads 24-hour time.
_TWELVE_HOUR = {"us", "ca"}


def when(t: datetime, locale: str | None, zone: str = DEFAULT_TIME_ZONE) -> str:
    """Sat 26 Sep, 14:00 · Sat, Sep 26, 2:00 PM (en-US/en-CA) · Sa., 26.09., 14:00 Uhr"""
    t, lang = t.astimezone(ZoneInfo(zone)), language(locale)
    day = _DAYS[lang][t.weekday()]
    if lang == "de":
        return f"{day}, {t:%d.%m.}, {t:%H:%M} Uhr"
    if lang == "fr":
        return f"{day} {t.day} {_MOIS[t.month - 1]}, {t:%H:%M}"
    region = (locale or "").lower().replace("_", "-").partition("-")[2][:2]
    if region in _TWELVE_HOUR:
        hour = t.hour % 12 or 12
        return f"{day}, {_MONTHS[t.month - 1]} {t.day}, {hour}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"
    return f"{day} {t.day} {_MONTHS[t.month - 1]}, {t:%H:%M}"


# Minor units per currency (ISO 4217): all of Cappy's markets use 2 but HUF,
# which Stripe still counts in hundredths but shows without decimals.
_SYMBOL = {"eur": "€", "gbp": "£", "usd": "$", "cad": "$", "chf": "CHF"}


def money(cents: int, currency: str, locale: str | None) -> str:
    """12,50 € · €12.50 · 12,50 € (fr) · CA$ is just $ in its own market."""
    currency = currency.lower()
    symbol = _SYMBOL.get(currency, currency.upper())
    places = 0 if currency in ("huf", "isk") else 2
    amount = f"{cents / 100:,.{places}f}"
    lang = language(locale)
    if lang == "de":
        return f"{amount.replace(',', 'X').replace('.', ',').replace('X', '.')} {symbol}"
    if lang == "fr":
        return f"{amount.replace(',', ' ').replace('.', ',')} {symbol}"
    return f"{symbol}{amount}" if len(symbol) == 1 else f"{amount} {symbol}"
