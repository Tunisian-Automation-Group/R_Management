import { Link, useParams } from 'react-router-dom'
import { Screen } from '../components/AppShell.tsx'
import { Card } from '../components/ui.tsx'
import { NotFound } from './NotFound.tsx'
import { lang, t } from '../../i18n.ts'
import { useMarket } from '../../data/repo.ts'

type Lang3 = 'en' | 'de' | 'fr'
type Article = { title: Record<Lang3, string>; body: Record<Lang3, string[]> }

/** Help, public like the legal pages (U-39). Whole paragraphs per language, as
 *  the legal pages are, not catalogue strings. `{emergency}` is the reader's
 *  market's emergency number (112, 911…). */
const ARTICLES: Record<string, Article> = {
  how: {
    title: { en: 'How Cappy works', de: 'So funktioniert Cappy', fr: 'Comment fonctionne Cappy' },
    body: {
      en: [
        'Cappy lets you book the hours of things other people own: a workshop, a van, a 3D printer, a studio. You pay for the time you use, not for owning it.',
        'Search by what you need and when. Each listing shows the price for your hours, the owner’s record and the cancellation policy before you ask.',
        'The owner has 24 hours to accept a request, unless the listing is instant book. Nothing can start sooner than 2 hours from now, so the owner always has time to answer.',
      ],
      de: [
        'Mit Cappy buchst du die Stunden von Dingen, die anderen gehören: eine Werkstatt, einen Transporter, einen 3D-Drucker, ein Studio. Du zahlst für die Zeit, die du nutzt, nicht fürs Besitzen.',
        'Suche nach dem, was du brauchst, und wann. Jedes Inserat zeigt vor der Anfrage den Preis für deine Stunden, die Bilanz des Anbieters und die Stornobedingungen.',
        'Der Anbieter hat 24 Stunden, um eine Anfrage anzunehmen, außer das Inserat ist sofort buchbar. Nichts beginnt früher als in 2 Stunden, damit der Anbieter immer Zeit zum Antworten hat.',
      ],
      fr: [
        'Cappy vous permet de réserver les heures de choses qui appartiennent à d’autres\u00a0: un atelier, une camionnette, une imprimante 3D, un studio. Vous payez le temps que vous utilisez, pas la propriété.',
        'Cherchez selon ce dont vous avez besoin et quand. Chaque annonce affiche, avant votre demande, le prix pour vos heures, le bilan du propriétaire et les conditions d’annulation.',
        'Le propriétaire a 24\u00a0heures pour accepter une demande, sauf si l’annonce est en réservation instantanée. Rien ne peut commencer avant 2\u00a0heures, pour que le propriétaire ait toujours le temps de répondre.',
      ],
    },
  },
  paying: {
    title: { en: 'Booking and paying', de: 'Buchen und bezahlen', fr: 'Réserver et payer' },
    body: {
      en: [
        'When you book, your card is authorised for the total, fee included. With instant book it is charged at once; otherwise it is charged only when the owner accepts, and if they decline or do not answer, the hold is released.',
        'Always pay on Cappy. A payment made any other way is not protected: no refund, no dispute, no review. Someone asking you to pay outside Cappy is a reason to report them.',
        'Each booking shows its full price, with Cappy’s fee inside it. Owners get an invoice for Cappy’s fee under Earn → Invoices.',
      ],
      de: [
        'Mit deiner Buchung wird der Gesamtbetrag inklusive Gebühr auf deiner Karte reserviert. Bei Sofortbuchung wird sofort abgebucht; sonst erst, wenn der Anbieter annimmt. Lehnt er ab oder antwortet nicht, wird die Reservierung aufgehoben.',
        'Bezahle immer über Cappy. Eine Zahlung auf anderem Weg ist nicht geschützt: keine Erstattung, kein Widerspruch, keine Bewertung. Wer dich bittet, außerhalb von Cappy zu zahlen, sollte gemeldet werden.',
        'Jede Buchung zeigt ihren vollen Preis, die Gebühr von Cappy ist darin enthalten. Anbieter bekommen unter Verdienen → Rechnungen eine Rechnung über die Gebühr von Cappy.',
      ],
      fr: [
        'Lorsque vous réservez, le montant total, frais compris, est bloqué sur votre carte. En réservation instantanée, il est débité aussitôt\u00a0; sinon, il ne l’est que lorsque le propriétaire accepte, et s’il refuse ou ne répond pas, le blocage est levé.',
        'Payez toujours sur Cappy. Un paiement fait autrement n’est pas protégé\u00a0: pas de remboursement, pas de litige, pas d’évaluation. Quelqu’un qui vous demande de payer hors de Cappy doit être signalé.',
        'Chaque réservation affiche son prix complet, frais de Cappy inclus. Les propriétaires reçoivent une facture pour les frais de Cappy sous Revenus → Factures.',
      ],
    },
  },
  cancelling: {
    title: { en: 'Cancelling and refunds', de: 'Stornieren und Erstattung', fr: 'Annulation et remboursement' },
    body: {
      en: [
        'You can cancel before the booked time starts. The listing’s policy decides the refund, and the cancel screen shows the exact amount before you confirm.',
        'After the time has started you cannot cancel. If something went wrong, open a problem on the booking instead: the money is held until support has looked at it.',
        'Refunds go back to the card you paid with, usually within 5 to 10 days depending on your bank.',
      ],
      de: [
        'Du kannst stornieren, bevor die gebuchte Zeit beginnt. Die Bedingungen des Inserats bestimmen die Erstattung; der genaue Betrag steht vor dem Bestätigen da.',
        'Hat die Zeit begonnen, ist keine Stornierung mehr möglich. Ist etwas schiefgelaufen, melde in der Buchung ein Problem: Das Geld wird gehalten, bis der Support es geprüft hat.',
        'Erstattungen gehen auf die Karte, mit der du bezahlt hast, meist innerhalb von 5 bis 10 Tagen, je nach Bank.',
      ],
      fr: [
        'Vous pouvez annuler avant le début du créneau réservé. Les conditions de l’annonce fixent le remboursement, et l’écran d’annulation affiche le montant exact avant que vous confirmiez.',
        'Une fois le créneau commencé, vous ne pouvez plus annuler. Si quelque chose s’est mal passé, signalez un problème dans la réservation\u00a0: l’argent est retenu jusqu’à ce que le support l’ait examiné.',
        'Les remboursements reviennent sur la carte utilisée pour payer, en général sous 5 à 10\u00a0jours selon votre banque.',
      ],
    },
  },
  earning: {
    title: { en: 'Listing and getting paid', de: 'Inserieren und Auszahlung', fr: 'Publier une annonce et être payé' },
    body: {
      en: [
        'List something under Earn: what it is, where, the price per hour and when it is free, as a weekly pattern or exact dates. You decide on every request unless you turn on instant book.',
        'Payouts go through Stripe to your bank account. Set them up once under Earn; you are paid after each booking is completed. Cappy’s fee is inside the price the renter pays.',
        'A request left unanswered expires after 24 hours. Once you have answered a few, your listing shows how quickly you usually answer.',
      ],
      de: [
        'Inseriere unter Verdienen: was es ist, wo, den Stundenpreis und wann es frei ist, als wöchentliches Muster oder mit genauen Daten. Du entscheidest über jede Anfrage, außer du schaltest Sofortbuchung ein.',
        'Auszahlungen laufen über Stripe auf dein Bankkonto. Richte sie einmal unter Verdienen ein; ausgezahlt wird nach jeder abgeschlossenen Buchung. Die Gebühr von Cappy steckt im Preis, den der Mieter zahlt.',
        'Eine unbeantwortete Anfrage verfällt nach 24 Stunden. Sobald du einige beantwortet hast, zeigt dein Inserat, wie schnell du meist antwortest.',
      ],
      fr: [
        'Publiez une annonce sous Revenus\u00a0: ce que c’est, où, le prix à l’heure et quand c’est libre, selon un rythme hebdomadaire ou des dates précises. Vous décidez de chaque demande, sauf si vous activez la réservation instantanée.',
        'Les versements passent par Stripe vers votre compte bancaire. Configurez-les une fois sous Revenus\u00a0; vous êtes payé après chaque réservation terminée. Les frais de Cappy sont inclus dans le prix payé par le locataire.',
        'Une demande sans réponse expire après 24\u00a0heures. Une fois que vous avez répondu à quelques-unes, votre annonce indique en combien de temps vous répondez d’habitude.',
      ],
    },
  },
  handover: {
    title: { en: 'The hand-over', de: 'Die Übergabe', fr: 'La remise' },
    body: {
      en: [
        'The address and access instructions appear on the booking once it is accepted. Use the booking’s messages to agree the details.',
        'Take photos at the start and at the end, in the booking. They carry the time they were added and are what support looks at if there is a disagreement about damage.',
        'Either side can mark the hand-over from 30 minutes before the booked time.',
      ],
      de: [
        'Adresse und Zugangshinweise erscheinen in der Buchung, sobald sie angenommen ist. Stimmt die Einzelheiten über die Nachrichten der Buchung ab.',
        'Mach zu Beginn und am Ende Fotos in der Buchung. Sie tragen den Zeitpunkt, zu dem sie hinzugefügt wurden, und sind das, was der Support bei einem Streit über Schäden ansieht.',
        'Beide Seiten können die Übergabe ab 30 Minuten vor der gebuchten Zeit bestätigen.',
      ],
      fr: [
        'L’adresse et les instructions d’accès apparaissent dans la réservation dès qu’elle est acceptée. Utilisez les messages de la réservation pour convenir des détails.',
        'Prenez des photos au début et à la fin, dans la réservation. Elles portent l’heure à laquelle elles ont été ajoutées et c’est ce que le support examine en cas de désaccord sur un dommage.',
        'Chaque partie peut confirmer la remise à partir de 30\u00a0minutes avant l’heure réservée.',
      ],
    },
  },
  problems: {
    title: { en: 'When something goes wrong', de: 'Wenn etwas schiefgeht', fr: 'Quand quelque chose ne va pas' },
    body: {
      en: [
        'Write to the other side first, in the booking. Most things are a misunderstanding about times or access.',
        'If it cannot be settled, open a problem on the booking. The payment is held, the booking does not complete on its own, and a person at Cappy decides whether the owner is paid or you are refunded.',
        'If you feel unsafe, leave and call the emergency services ({emergency}) first.',
      ],
      de: [
        'Schreib zuerst der anderen Seite in der Buchung. Meist ist es ein Missverständnis über Zeiten oder Zugang.',
        'Lässt es sich nicht klären, melde in der Buchung ein Problem. Die Zahlung wird gehalten, die Buchung schließt nicht von selbst ab, und ein Mensch bei Cappy entscheidet, ob der Anbieter bezahlt oder dir erstattet wird.',
        'Fühlst du dich unsicher, geh und ruf zuerst den Notruf ({emergency}).',
      ],
      fr: [
        'Écrivez d’abord à l’autre partie, dans la réservation. La plupart du temps, c’est un malentendu sur les horaires ou l’accès.',
        'Si cela ne se règle pas, signalez un problème dans la réservation. Le paiement est retenu, la réservation ne se termine pas d’elle-même, et une personne chez Cappy décide si le propriétaire est payé ou si vous êtes remboursé.',
        'Si vous ne vous sentez pas en sécurité, partez et appelez d’abord les services d’urgence ({emergency}).',
      ],
    },
  },
  safety: {
    title: { en: 'How we keep you safe', de: 'Wie wir dich schützen', fr: 'Comment nous vous protégeons' },
    body: {
      en: [
        'Members only. Listings are people’s own property, places and times, so nothing is shown until you sign in, and every booking is tied to a real account.',
        'Contact details are hidden in messages until a booking is accepted, so the conversation and the payment stay on Cappy, where they are protected.',
        'Larger bookings need a one-time ID check. Reviews are blind: neither side sees the other’s until both have rated, or 14 days have passed.',
        'You can report any listing, profile, message or review, and block anyone. Reports are read by a person.',
      ],
      de: [
        'Nur für Mitglieder. Inserate sind Eigentum, Orte und Zeiten von Menschen; deshalb ist nichts sichtbar, bevor du dich anmeldest, und jede Buchung gehört zu einem echten Konto.',
        'Kontaktdaten in Nachrichten sind verborgen, bis eine Buchung angenommen ist, damit Gespräch und Zahlung auf Cappy bleiben, wo sie geschützt sind.',
        'Größere Buchungen brauchen eine einmalige Ausweisprüfung. Bewertungen sind verdeckt: Keine Seite sieht die der anderen, bevor beide bewertet haben oder 14 Tage vergangen sind.',
        'Du kannst jedes Inserat, Profil, jede Nachricht und Bewertung melden und jeden blockieren. Meldungen liest ein Mensch.',
      ],
      fr: [
        'Réservé aux membres. Les annonces sont les biens, les lieux et les horaires de vraies personnes\u00a0; rien n’est donc visible avant la connexion, et chaque réservation est liée à un vrai compte.',
        'Les coordonnées sont masquées dans les messages jusqu’à l’acceptation d’une réservation, pour que la conversation et le paiement restent sur Cappy, où ils sont protégés.',
        'Les réservations importantes demandent une vérification d’identité unique. Les évaluations sont à l’aveugle\u00a0: aucune partie ne voit celle de l’autre avant que les deux aient évalué, ou que 14\u00a0jours soient passés.',
        'Vous pouvez signaler toute annonce, tout profil, message ou évaluation, et bloquer n’importe qui. Les signalements sont lus par une personne.',
      ],
    },
  },
  reviews: {
    title: { en: 'Reviews', de: 'Bewertungen', fr: 'Évaluations' },
    body: {
      en: [
        'After a completed booking both sides rate each other: the renter rates the listing, the owner rates the renter.',
        'Reviews are published together, once both have rated or 14 days after the booking, so nobody rates in reply to the other.',
      ],
      de: [
        'Nach einer abgeschlossenen Buchung bewerten sich beide Seiten: Der Mieter bewertet das Inserat, der Anbieter den Mieter.',
        'Bewertungen erscheinen gemeinsam, sobald beide bewertet haben oder 14 Tage nach der Buchung, damit niemand als Antwort auf den anderen bewertet.',
      ],
      fr: [
        'Après une réservation terminée, les deux parties s’évaluent\u00a0: le locataire évalue l’annonce, le propriétaire évalue le locataire.',
        'Les évaluations sont publiées ensemble, dès que les deux ont évalué ou 14\u00a0jours après la réservation, pour que personne n’évalue en réponse à l’autre.',
      ],
    },
  },
  account: {
    title: { en: 'Your account and data', de: 'Dein Konto und deine Daten', fr: 'Votre compte et vos données' },
    body: {
      en: [
        'Download everything Cappy holds about you under You → Your data.',
        'You can delete your account in the app under You. While a booking is open or a payout is pending, finish those first; the app tells you which and until when. Invoices and payment records are kept without your name for as long as tax law requires (up to ten years in Germany).',
        'Signed in on a device you no longer have? Use “Sign out everywhere” under You.',
      ],
      de: [
        'Lade unter Du → Deine Daten alles herunter, was Cappy über dich speichert.',
        'Dein Konto kannst du in der App unter Du löschen. Solange eine Buchung offen oder eine Auszahlung ausstehend ist, schließe sie zuerst ab; die App sagt dir, welche und bis wann. Rechnungen und Zahlungsbelege bewahren wir ohne deinen Namen so lange auf, wie das Steuerrecht es verlangt (in Deutschland bis zu zehn Jahre).',
        'Auf einem Gerät angemeldet, das du nicht mehr hast? Nutze „Überall abmelden“ unter Du.',
      ],
      fr: [
        'Téléchargez tout ce que Cappy conserve à votre sujet sous Vous → Vos données.',
        'Vous pouvez supprimer votre compte dans l’application, sous Vous. Tant qu’une réservation est en cours ou qu’un versement est en attente, terminez-les d’abord\u00a0; l’application vous dit lesquels et jusqu’à quand. Les factures et justificatifs de paiement sont conservés sans votre nom aussi longtemps que le droit fiscal l’exige (jusqu’à dix ans en Allemagne).',
        'Connecté sur un appareil que vous n’avez plus\u00a0? Utilisez «\u00a0Se déconnecter partout\u00a0» sous Vous.',
      ],
    },
  },
  notifications: {
    title: { en: 'Notifications', de: 'Benachrichtigungen', fr: 'Notifications' },
    body: {
      en: [
        'Cappy notifies you about your bookings and messages only: a new request, an answer, a hand-over, a payout. Never marketing unless you ask for it.',
        'Booking changes always arrive by email as well, and everything is in the bell in the app, so turning push off loses nothing. Messages come by email too, at most once every 15 minutes per conversation; you can turn that off under You.',
      ],
      de: [
        'Cappy benachrichtigt dich nur über deine Buchungen und Nachrichten: eine neue Anfrage, eine Antwort, eine Übergabe, eine Auszahlung. Werbung nie, außer du willst sie.',
        'Änderungen an Buchungen kommen immer auch per E-Mail, und alles steht in der Glocke in der App; ohne Push verpasst du also nichts. Nachrichten kommen ebenfalls per E-Mail, höchstens einmal alle 15 Minuten pro Unterhaltung; das kannst du unter Du abschalten.',
      ],
      fr: [
        'Cappy vous prévient uniquement au sujet de vos réservations et messages\u00a0: une nouvelle demande, une réponse, une remise, un versement. Jamais de publicité, sauf si vous la demandez.',
        'Les changements de réservation arrivent toujours aussi par courriel, et tout se trouve dans la cloche de l’application\u00a0; désactiver les notifications push ne fait donc rien perdre. Les messages arrivent aussi par courriel, au plus une fois toutes les 15\u00a0minutes par conversation\u00a0; vous pouvez le désactiver sous Vous.',
      ],
    },
  },
}

const SUPPORT = (import.meta.env.VITE_LEGAL_EMAIL as string | undefined)?.trim()

/** Write to support, with the booking attached when there is one. */
export function supportHref(bookingId?: string): string {
  if (!SUPPORT) return '/legal/impressum'
  const subject = bookingId ? `Booking ${bookingId}` : 'Cappy'
  return `mailto:${SUPPORT}?subject=${encodeURIComponent(subject)}`
}

const pick = <T,>(by: Record<Lang3, T>): T => by[lang() as Lang3] ?? by.en

export function Help() {
  const { topic } = useParams()
  const emergency = useMarket().emergencyNumber
  if (topic) {
    const a = ARTICLES[topic]
    if (!a) return <NotFound />
    return (
      <Screen eyebrow={t('Help')} title={pick(a.title)} back="/help">
        <article className="space-y-4 pb-8 text-[0.9375rem] leading-[1.5rem] text-[var(--ink-2)]">
          {pick(a.body).map((p) => (
            <p key={p}>{p.replace('{emergency}', emergency)}</p>
          ))}
        </article>
        <ContactCard />
      </Screen>
    )
  }
  return (
    <Screen title={t('Help')} sub={t('Short answers to what people ask most.')} back="/profile">
      <ul className="divide-y divide-[var(--line)] border-y border-[var(--line)]">
        {Object.entries(ARTICLES).map(([key, a]) => (
          <li key={key}>
            <Link to={`/help/${key}`} className="flex min-h-[52px] items-center justify-between gap-4 py-3 text-[0.9375rem] font-semibold">
              {pick(a.title)}
              <span aria-hidden="true" className="text-[var(--ink-4)]">›</span>
            </Link>
          </li>
        ))}
        <li>
          <Link to="/legal/report" className="flex min-h-[52px] items-center justify-between gap-4 py-3 text-[0.9375rem] font-semibold">
            {t('Reporting content')}
            <span aria-hidden="true" className="text-[var(--ink-4)]">›</span>
          </Link>
        </li>
      </ul>
      <div className="mt-6">
        <ContactCard />
      </div>
    </Screen>
  )
}

function ContactCard() {
  return (
    <Card className="p-5">
      <h2 className="t-label mb-1">{t('Still stuck?')}</h2>
      <p className="t-sm mb-3 text-[var(--ink-3)]">
        {t('About a booking? Open it and use “Get help with this booking”, so we see which one.')}
      </p>
      <a href={supportHref()} className="text-[0.875rem] font-semibold underline">
        {t('Write to Cappy')}
      </a>
    </Card>
  )
}
