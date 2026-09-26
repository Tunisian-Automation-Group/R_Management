"""Every email and push, in English, German and French (France and Québec:
neutral French, « courriel »). Rendered in the recipient's language, Cognito's
`locale` attribute, which the app sets; any other language gets English."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from cappy_common.timeutil import dt_from_iso

TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "paid": (
            "You have been paid {amount}",
            "Your share for {title} is on its way to your bank.\n\n{web}/earn",
        ),
        "requested": (
            "New request: {title}",
            "Someone wants to book {title}{for_amount}. Answer by {deadline}, or the request lapses.\n\n{link}",
        ),
        "requested_extension": (
            "Extension request: {title}",
            "Your renter wants to extend their booking: {title}{for_amount}. Answer by {deadline}, or the request lapses.\n\n{link}",
        ),
        "accepted": (
            "Confirmed: {title}",
            "Your booking of {title} is confirmed.{paid} The hand-over address is in the app.\n\n{link}",
        ),
        # An extension ends with the booking it extends (V6-22, V7-12).
        "extension_cancelled_renter": (
            "Extension cancelled: {title}",
            "Your extension of {title} was cancelled because the booking it extends was cancelled. You get {amount} back to your card.\n\n{link}",
        ),
        "extension_cancelled_owner": (
            "Extension cancelled: {title}",
            "The extension of {title} was cancelled because the booking it extends was cancelled. The renter gets everything back ({amount}).\n\n{link}",
        ),
        "instant_booked": (
            "New booking: {title}",
            "{title} was booked instantly. The details are in the app.\n\n{link}",
        ),
        "declined": (
            "Declined: {title}",
            "Your request for {title} was declined. Nothing was charged.{reason}\n\n{link}",
        ),
        "cancelled": ("Cancelled: {title}", "The booking of {title} was cancelled.\n\n{link}"),
        # Who did what, the money and the next step (V6-11).
        "owner_cancelled": (
            "Cancelled by the owner: {title}",
            "The owner cancelled your booking of {title}. You get {amount} back to your card.\n\n{link}",
        ),
        "no_show_owner_renter": (
            "Refunded: {title}",
            "You reported that the owner did not turn up for {title}. The booking is cancelled and you get the full price back ({amount}).\n\n{link}",
        ),
        "no_show_owner_owner": (
            "Reported as a no-show: {title}",
            "The renter reported that you did not turn up for {title}. The booking is cancelled, the renter gets the full price back ({amount}), and it counts against your reliability. If this is wrong, tell us through Get help on the booking.\n\n{link}",
        ),
        "no_show_renter_owner": (
            "No-show recorded: {title}",
            "You reported that the renter did not turn up for {title}. The booking is cancelled and you are paid as for a late cancellation: nothing is refunded.\n\n{link}",
        ),
        "no_show_renter_renter": (
            "Reported as a no-show: {title}",
            "The owner reported that you did not turn up for {title}. The booking is cancelled and nothing is refunded. If this is wrong, tell us through Get help on the booking.\n\n{link}",
        ),
        "expired": ("Expired: {title}", "Your request for {title} lapsed. Nothing was charged.\n\n{link}"),
        "completed": ("How was {title}?", "Your booking is complete. Rate it to help the next buyer.\n\n{link}"),
        "listing_idle": (
            "No free time next week: {title}",
            "{title} has no free time in the next seven days, so nobody can book it. Add opening hours or windows to keep it bookable.\n\n{link}",
        ),
        "message": ("New message: {title}", "Open the conversation\n\n{link}"),
        "dispute_offer": (
            "An offer to settle: {title}",
            "The other side offers to settle the problem with {title}: {amount} back to the renter. Accept it, or make another offer, by {deadline}; after that we decide.\n\n{link}",
        ),
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
        "dispute_refunded": (
            "Settled: {title}",
            "{how_en} the renter gets the full price back ({amount}). The owner is not paid for this booking.{note}\n\n{link}",
        ),
        "dispute_partial": (
            "Settled: {title}",
            "{how_en} {amount} goes back to the renter, and the owner is paid for the rest.{note}\n\n{link}",
        ),
        # The renter reads it about themselves (V7-23).
        "dispute_refunded_renter": (
            "Settled: {title}",
            "{how_en} you get the full price back ({amount}).{note}\n\n{link}",
        ),
        "dispute_partial_renter": (
            "Settled: {title}",
            "{how_en} you get {amount} back to your card, and the owner is paid for the rest.{note}\n\n{link}",
        ),
        "dispute_owner_paid_renter": (
            "Settled: {title}",
            "{how_en} the owner is paid in full and nothing comes back to you.{note}\n\n{link}",
        ),
        "dispute_owner_paid": (
            "Settled: {title}",
            "{how_en} the owner is paid in full and nothing is refunded.{note}\n\n{link}",
        ),
        "dispute_escalated": (
            "We are deciding now: {title}",
            "There was no agreement in time, so Cappy now looks at what happened with {title} and decides. You will hear from us.\n\n{link}",
        ),
        "claim_filed": (
            "A late return was reported: {title}",
            "The owner reports that {title} came back late and asks for {amount}. Nothing is charged: we look at it and tell you what we decide. If you see it differently, say so in the conversation.\n\n{link}",
        ),
        "claim_confirmed": (
            "Late return: our decision on {title}",
            "We looked at the late return and confirmed it: {amount} is owed to the owner. We will be in touch about paying it.\n\n{link}",
        ),
        "claim_rejected": (
            "Late return: our decision on {title}",
            "We looked at the late return and did not confirm it: nothing is owed.\n\n{link}",
        ),
        "report_outcome_none": (
            "Your report: our decision",
            "Having looked at your report, we found no breach of the law or our terms.\n\n{statement}\n\nReference: {report}",
        ),
    },
    "de": {
        "paid": (
            "Du hast {amount} erhalten",
            "Dein Anteil für {title} ist auf dem Weg zu deiner Bank.\n\n{web}/earn",
        ),
        "requested": (
            "Neue Anfrage: {title}",
            "Jemand möchte {title}{for_amount} buchen. Bitte antworte bis {deadline}, sonst verfällt die Anfrage.\n\n{link}",
        ),
        "requested_extension": (
            "Verlängerungsanfrage: {title}",
            "Die mietende Person möchte ihre Buchung verlängern: {title}{for_amount}. Bitte antworte bis {deadline}, sonst verfällt die Anfrage.\n\n{link}",
        ),
        "accepted": (
            "Bestätigt: {title}",
            "Deine Buchung von {title} ist bestätigt.{paid} Die Übergabeadresse findest du in der App.\n\n{link}",
        ),
        "extension_cancelled_renter": (
            "Verlängerung storniert: {title}",
            "Deine Verlängerung von {title} wurde storniert, weil die Buchung, die sie verlängert, storniert wurde. Du bekommst {amount} auf deine Karte zurück.\n\n{link}",
        ),
        "extension_cancelled_owner": (
            "Verlängerung storniert: {title}",
            "Die Verlängerung von {title} wurde storniert, weil die Buchung, die sie verlängert, storniert wurde. Die mietende Person bekommt alles zurück ({amount}).\n\n{link}",
        ),
        "instant_booked": (
            "Neue Buchung: {title}",
            "{title} wurde sofort gebucht. Alle Details findest du in der App.\n\n{link}",
        ),
        "declined": (
            "Abgelehnt: {title}",
            "Deine Anfrage für {title} wurde abgelehnt. Es wurde nichts berechnet.{reason}\n\n{link}",
        ),
        "cancelled": ("Storniert: {title}", "Die Buchung von {title} wurde storniert.\n\n{link}"),
        "owner_cancelled": (
            "Von der vermietenden Person storniert: {title}",
            "Die vermietende Person hat deine Buchung von {title} storniert. Du bekommst {amount} auf deine Karte zurück.\n\n{link}",
        ),
        "no_show_owner_renter": (
            "Erstattet: {title}",
            "Du hast gemeldet, dass die vermietende Person zu {title} nicht erschienen ist. Die Buchung ist storniert, und du bekommst den vollen Preis zurück ({amount}).\n\n{link}",
        ),
        "no_show_owner_owner": (
            "Als nicht erschienen gemeldet: {title}",
            "Die mietende Person hat gemeldet, dass du zu {title} nicht erschienen bist. Die Buchung ist storniert, die mietende Person bekommt den vollen Preis zurück ({amount}), und es zählt gegen deine Zuverlässigkeit. Wenn das nicht stimmt, sag es uns über die Hilfe in der Buchung.\n\n{link}",
        ),
        "no_show_renter_owner": (
            "Nichterscheinen erfasst: {title}",
            "Du hast gemeldet, dass die mietende Person zu {title} nicht erschienen ist. Die Buchung ist storniert, und du wirst wie bei einer späten Stornierung bezahlt: Es wird nichts erstattet.\n\n{link}",
        ),
        "no_show_renter_renter": (
            "Als nicht erschienen gemeldet: {title}",
            "Die vermietende Person hat gemeldet, dass du zu {title} nicht erschienen bist. Die Buchung ist storniert, und es wird nichts erstattet. Wenn das nicht stimmt, sag es uns über die Hilfe in der Buchung.\n\n{link}",
        ),
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
        "dispute_offer": (
            "Ein Einigungsangebot: {title}",
            "Die andere Seite schlägt vor, das Problem mit {title} so zu lösen: {amount} zurück an die mietende Person. Nimm es an oder mach ein anderes Angebot, bis {deadline}; danach entscheiden wir.\n\n{link}",
        ),
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
            "Dein Inserat ist nicht mehr sichtbar und kann nicht mehr gebucht werden.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; eine unbeteiligte Person prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
        ),
        "suspended": (
            "Wir haben dein Konto gesperrt",
            "Deine Inserate wurden entfernt, und du kannst nichts mehr inserieren oder buchen.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; eine unbeteiligte Person prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
        ),
        "content_removed": (
            "Wir haben einen Beitrag von dir entfernt",
            "Eine Nachricht oder Bewertung von dir wurde entfernt. Dein Konto ist sonst nicht eingeschränkt.\n\nGrund: {statement}\nRechtsgrundlage: {ground_de}\nAutomatisiert entschieden: {automated_de}\n\nWas du tun kannst: Widersprich dieser Entscheidung, indem du innerhalb von 6 Monaten auf diese E-Mail antwortest; eine unbeteiligte Person prüft sie erneut. Du kannst dich auch an eine zertifizierte außergerichtliche Streitbeilegungsstelle (DSA Art. 21) oder an die Gerichte wenden. Kontakt: {web}/legal/impressum",
        ),
        "report_outcome_action": (
            "Deine Meldung: unsere Entscheidung",
            "Wir haben deine Meldung geprüft und Maßnahmen ergriffen.\n\n{statement}\n\nAktenzeichen: {report}",
        ),
        "dispute_refunded": (
            "Geklärt: {title}",
            "{how_de} Die mietende Person bekommt den vollen Preis zurück ({amount}). Für diese Buchung wird nichts ausgezahlt.{note}\n\n{link}",
        ),
        "dispute_partial": (
            "Geklärt: {title}",
            "{how_de} {amount} gehen an die mietende Person zurück, der Rest wird ausgezahlt.{note}\n\n{link}",
        ),
        "dispute_refunded_renter": (
            "Geklärt: {title}",
            "{how_de} Du bekommst den vollen Preis zurück ({amount}).{note}\n\n{link}",
        ),
        "dispute_partial_renter": (
            "Geklärt: {title}",
            "{how_de} Du bekommst {amount} auf deine Karte zurück, der Rest wird an die vermietende Person ausgezahlt.{note}\n\n{link}",
        ),
        "dispute_owner_paid_renter": (
            "Geklärt: {title}",
            "{how_de} Der volle Betrag wird an die vermietende Person ausgezahlt, du bekommst nichts zurück.{note}\n\n{link}",
        ),
        "dispute_owner_paid": (
            "Geklärt: {title}",
            "{how_de} Der volle Betrag wird ausgezahlt, es wird nichts erstattet.{note}\n\n{link}",
        ),
        "dispute_escalated": (
            "Wir entscheiden jetzt: {title}",
            "Es gab keine rechtzeitige Einigung. Deshalb prüft Cappy jetzt, was bei {title} passiert ist, und entscheidet. Wir melden uns.\n\n{link}",
        ),
        "claim_filed": (
            "Eine verspätete Rückgabe wurde gemeldet: {title}",
            "Die vermietende Person meldet, dass {title} verspätet zurückkam, und fordert {amount}. Es wird nichts abgebucht: Wir prüfen es und teilen dir unsere Entscheidung mit. Wenn du es anders siehst, schreib es ins Gespräch.\n\n{link}",
        ),
        "claim_confirmed": (
            "Verspätete Rückgabe: unsere Entscheidung zu {title}",
            "Wir haben die verspätete Rückgabe geprüft und bestätigt: {amount} stehen der vermietenden Person zu. Wir melden uns wegen der Zahlung.\n\n{link}",
        ),
        "claim_rejected": (
            "Verspätete Rückgabe: unsere Entscheidung zu {title}",
            "Wir haben die verspätete Rückgabe geprüft und nicht bestätigt: Es ist nichts zu zahlen.\n\n{link}",
        ),
        "report_outcome_none": (
            "Deine Meldung: unsere Entscheidung",
            "Wir haben deine Meldung geprüft und keinen Verstoß gegen Recht oder unsere Bedingungen festgestellt.\n\n{statement}\n\nAktenzeichen: {report}",
        ),
    },
    "fr": {
        "paid": (
            "Vous avez reçu {amount}",
            "Votre part pour {title} est en route vers votre banque.\n\n{web}/earn",
        ),
        "requested": (
            "Nouvelle demande : {title}",
            "Quelqu’un souhaite réserver {title}{for_amount}. Répondez avant {deadline}, sinon la demande expire.\n\n{link}",
        ),
        "requested_extension": (
            "Demande de prolongation : {title}",
            "La personne locataire souhaite prolonger sa réservation : {title}{for_amount}. Répondez avant {deadline}, sinon la demande expire.\n\n{link}",
        ),
        "accepted": (
            "Confirmé : {title}",
            "Votre réservation de {title} est confirmée.{paid} L’adresse de remise est dans l’application.\n\n{link}",
        ),
        "extension_cancelled_renter": (
            "Prolongation annulée : {title}",
            "Votre prolongation de {title} a été annulée, car la réservation qu’elle prolonge a été annulée. Vous récupérez {amount} sur votre carte.\n\n{link}",
        ),
        "extension_cancelled_owner": (
            "Prolongation annulée : {title}",
            "La prolongation de {title} a été annulée, car la réservation qu’elle prolonge a été annulée. La personne locataire récupère tout ({amount}).\n\n{link}",
        ),
        "instant_booked": (
            "Nouvelle réservation : {title}",
            "{title} a été réservé instantanément. Tous les détails sont dans l’application.\n\n{link}",
        ),
        "declined": (
            "Refusée : {title}",
            "Votre demande pour {title} a été refusée. Rien n’a été facturé.{reason}\n\n{link}",
        ),
        "cancelled": ("Annulée : {title}", "La réservation de {title} a été annulée.\n\n{link}"),
        "owner_cancelled": (
            "Annulée par la personne propriétaire : {title}",
            "La personne propriétaire a annulé votre réservation de {title}. Vous récupérez {amount} sur votre carte.\n\n{link}",
        ),
        "no_show_owner_renter": (
            "Remboursée : {title}",
            "Vous avez signalé l’absence de la personne propriétaire pour {title}. La réservation est annulée et vous récupérez le prix complet ({amount}).\n\n{link}",
        ),
        "no_show_owner_owner": (
            "Absence signalée : {title}",
            "La personne locataire a signalé votre absence pour {title}. La réservation est annulée, la personne locataire récupère le prix complet ({amount}), et cela compte dans votre fiabilité. En cas d’erreur, dites-le-nous via l’aide de la réservation.\n\n{link}",
        ),
        "no_show_renter_owner": (
            "Absence enregistrée : {title}",
            "Vous avez signalé l’absence de la personne locataire pour {title}. La réservation est annulée et le montant vous est versé comme pour une annulation tardive : rien n’est remboursé.\n\n{link}",
        ),
        "no_show_renter_renter": (
            "Absence signalée par la personne propriétaire : {title}",
            "La personne propriétaire a signalé votre absence pour {title}. La réservation est annulée et rien n’est remboursé. En cas d’erreur, dites-le-nous via l’aide de la réservation.\n\n{link}",
        ),
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
        "dispute_offer": (
            "Une offre de règlement : {title}",
            "L’autre partie propose de régler le problème concernant {title} : {amount} remboursés à la personne locataire. Acceptez-la ou faites une autre offre avant {deadline} ; ensuite, c’est nous qui décidons.\n\n{link}",
        ),
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
        "dispute_refunded": (
            "Réglé : {title}",
            "{how_fr} la personne locataire récupère le prix complet ({amount}). Rien n’est versé pour cette réservation.{note}\n\n{link}",
        ),
        "dispute_partial": (
            "Réglé : {title}",
            "{how_fr} {amount} sont remboursés à la personne locataire, et le reste est versé à la personne propriétaire.{note}\n\n{link}",
        ),
        "dispute_refunded_renter": (
            "Réglé : {title}",
            "{how_fr} vous récupérez le prix complet ({amount}).{note}\n\n{link}",
        ),
        "dispute_partial_renter": (
            "Réglé : {title}",
            "{how_fr} vous récupérez {amount} sur votre carte, et le reste est versé à la personne propriétaire.{note}\n\n{link}",
        ),
        "dispute_owner_paid_renter": (
            "Réglé : {title}",
            "{how_fr} le montant complet est versé à la personne propriétaire et rien ne vous est remboursé.{note}\n\n{link}",
        ),
        "dispute_owner_paid": (
            "Réglé : {title}",
            "{how_fr} le montant complet est versé et rien n’est remboursé.{note}\n\n{link}",
        ),
        "dispute_escalated": (
            "Nous décidons maintenant : {title}",
            "Aucun accord n’a été trouvé à temps : Cappy examine maintenant ce qui s’est passé avec {title} et décide. Nous vous recontacterons.\n\n{link}",
        ),
        "claim_filed": (
            "Un retour tardif a été signalé : {title}",
            "La personne propriétaire signale que {title} a été rendu en retard et demande {amount}. Rien n’est prélevé : nous examinons la demande et vous communiquerons notre décision. Si vous voyez les choses autrement, dites-le dans la conversation.\n\n{link}",
        ),
        "claim_confirmed": (
            "Retour tardif : notre décision concernant {title}",
            "Nous avons examiné le retour tardif et l’avons confirmé : {amount} sont dus à la personne propriétaire. Nous vous recontacterons au sujet du paiement.\n\n{link}",
        ),
        "claim_rejected": (
            "Retour tardif : notre décision concernant {title}",
            "Nous avons examiné le retour tardif et ne l’avons pas confirmé : rien n’est dû.\n\n{link}",
        ),
        "report_outcome_none": (
            "Votre signalement : notre décision",
            "Après examen de votre signalement, nous n’avons constaté aucune infraction à la loi ou à nos conditions.\n\n{statement}\n\nRéférence : {report}",
        ),
    },
}


# Decisions about someone's content or account: the app shows the whole
# statement of reasons (DSA Art. 17), as the email does (V5-31).
STATEMENTS = frozenset({"taken_down", "suspended", "content_removed"})


def summary(key: str, text: str) -> str:
    """What the bell shows of a notice: its first paragraph, or for a
    decision the whole statement (why, ground, how to contest). Staff's note
    on a settlement and the reason for a decline are shown with it, as in
    the email (V6-1, V7-4)."""
    if key in STATEMENTS:
        return text
    first, *rest = text.split("\n\n")
    notes = [p for p in rest if p.startswith((*_NOTE.values(), *_REASON.values()))]
    return "\n\n".join([first, *notes])


def language(locale: str | None) -> str:
    """de-DE, de_AT, de → de; fr-FR, fr-CA → fr; anything else → en."""
    code = (locale or "").lower()[:2]
    return code if code in ("de", "fr") else "en"


# Server-made words that reach a reader as params (a decline reason, the default
# clause, the fallback title): told in the reader's language, like the app's
# catalogues do (V5-18). A person's own words (an owner's reason) stay as written.
PHRASES: dict[str, dict[str, str]] = {
    "your booking": {"de": "deine Buchung", "fr": "votre réservation"},
    "The listing was taken down by Cappy": {
        "de": "Das Inserat wurde von Cappy entfernt",
        "fr": "L’annonce a été retirée par Cappy",
    },
    "The listing was removed by its owner": {
        "de": "Die inserierende Person hat das Inserat entfernt",
        "fr": "L’annonce a été retirée par son propriétaire",
    },
    "The account was suspended": {"de": "Das Konto wurde gesperrt", "fr": "Le compte a été suspendu"},
    "The booking it extends was cancelled": {
        "de": "Die Buchung, die verlängert werden sollte, wurde storniert",
        "fr": "La réservation à prolonger a été annulée",
    },
    "Terms of use: rules for listings and conduct": {
        "de": "Nutzungsbedingungen: Regeln für Inserate und Verhalten",
        "fr": "Conditions d’utilisation : règles relatives aux annonces et au comportement",
    },
}
_REASON = {"en": "Reason: ", "de": "Grund: ", "fr": "Motif\u00a0: "}
_FOR = {"en": " for {}", "de": " für {}", "fr": " pour {}"}
_PAID = {"en": " You paid {}.", "de": " Du hast {} bezahlt.", "fr": " Vous avez payé {}."}
_NOTE = {"en": "From Cappy's team: ", "de": "Vom Cappy-Team: ", "fr": "De l\u2019équipe Cappy\u00a0: "}


def phrase(text: str, lang: str) -> str:
    return PHRASES.get(text, {}).get(lang, text)


def french(text: str) -> str:
    """French typography: a no-break space (U+00A0) before ':' and a narrow one
    (U+202F) before ; ? ! (not inside a URL or a time), and never two full
    stops where a reason ended in one (V5-19, V6-17)."""
    text = re.sub(r"(?<![\s\u00a0\u202f/\d])([:;?!])(?=[\s\n]|$)", " \\1", text)
    text = re.sub(r"[ \t\u00a0\u202f]+([;?!])", "\u202f\\1", text)
    text = re.sub(r"[ \t\u00a0\u202f]+(:)", "\u00a0\\1", text)
    return re.sub(r"(?<!\.)\.\.(?!\.)", ".", text)


def render(key: str, locale: str | None, **params) -> tuple[str, str]:
    """Raw params (``_cents``, ``_deadline``, ``_tz``, ``_reason``) are put in the
    reader's words here, so an inbox item stored once reads right in whichever
    language it is read."""
    params = dict(params)
    lang = language(locale)
    # People's own words (an owner's reason, staff's note) are quoted as
    # written: French typography is for our templates, not for them (V7-24).
    theirs: list[str] = []

    def quoted(text: str) -> str:
        theirs.append(text)
        return f"\x00{len(theirs) - 1}\x00"

    raw_reason = params.get("_reason")
    params = {k: phrase(v, lang) if isinstance(v, str) else v for k, v in params.items()}
    if "_reason" in params:
        # Its own paragraph, one full stop whatever the reason ended with (V5-16).
        given = (raw_reason or "").strip().rstrip(".")
        reason = phrase(given, lang)
        reason = reason if given in PHRASES else quoted(reason) if reason else ""
        params.pop("_reason")
        stop = "" if given.endswith(("!", "?")) else "."
        params["reason"] = f"\n\n{_REASON[lang]}{reason}{stop}" if reason else ""
    if "_note" in params:
        # Staff wrote it for both sides: their own paragraph, as written.
        note = (params.pop("_note") or "").strip()
        params["note"] = f"\n\n{_NOTE[lang]}{quoted(note)}" if note else ""
    params.setdefault("note", "")  # inbox items stored before notes existed
    if "_cents" in params:
        params["amount"] = money(*params.pop("_cents"), locale)
    # The price where a notice knows it (V7-23); nothing where it does not
    # (a notice stored before, an event without it).
    paid = params.get("amount")
    params.setdefault("for_amount", _FOR[lang].format(paid) if paid else "")
    params.setdefault("paid", _PAID[lang].format(paid) if paid else "")
    zone = params.pop("_tz", None) or DEFAULT_TIME_ZONE
    if "_start" in params:
        params["title"] = f"{params['title']}, {when(dt_from_iso(params.pop('_start')), locale, zone)}"
    if "_deadline" in params:
        at = params.pop("_deadline")
        params["deadline"] = (
            when(dt_from_iso(at), locale, zone)
            if at
            else {"en": "the booked start", "de": "zum gebuchten Beginn", "fr": "le début réservé"}[language(locale)]
        )
    subject, body = TEXTS[lang][key]
    subject, body = subject.format(**params), body.format(**params)
    if lang == "fr":
        subject, body = french(subject), french(body)
    unquote = lambda t: re.sub(r"\x00(\d+)\x00", lambda m: theirs[int(m.group(1))], t)  # noqa: E731
    return unquote(subject), unquote(body)


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
