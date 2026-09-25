import { Link, useParams } from 'react-router-dom'
import { Screen } from '../components/AppShell.tsx'
import { Card } from '../components/ui.tsx'
import { NotFound } from './NotFound.tsx'
import { lang, t } from '../../i18n.ts'

type Article = { title: [string, string]; body: [string[], string[]] }

/** Help, public like the legal pages (U-39). English and German side by side,
 *  as the legal pages are: whole paragraphs, not catalogue strings. */
const ARTICLES: Record<string, Article> = {
  how: {
    title: ['How Cappy works', 'So funktioniert Cappy'],
    body: [
      [
        'Cappy lets you book the hours of things other people own: a workshop, a van, a 3D printer, a studio. You pay for the time you use, not for owning it.',
        'Search by what you need and when. Each listing shows the price for your hours, the owner’s record and the cancellation policy before you ask.',
        'The owner has 24 hours to accept a request, unless the listing is instant book. Nothing can start sooner than 2 hours from now, so the owner always has time to answer.',
      ],
      [
        'Mit Cappy buchst du die Stunden von Dingen, die anderen gehören: eine Werkstatt, einen Transporter, einen 3D-Drucker, ein Studio. Du zahlst für die Zeit, die du nutzt, nicht fürs Besitzen.',
        'Suche nach dem, was du brauchst, und wann. Jedes Inserat zeigt vor der Anfrage den Preis für deine Stunden, die Bilanz des Anbieters und die Stornobedingungen.',
        'Der Anbieter hat 24 Stunden, um eine Anfrage anzunehmen, außer das Inserat ist sofort buchbar. Nichts beginnt früher als in 2 Stunden, damit der Anbieter immer Zeit zum Antworten hat.',
      ],
    ],
  },
  paying: {
    title: ['Booking and paying', 'Buchen und bezahlen'],
    body: [
      [
        'When you send a request your card is authorised for the total, fee included. It is charged only when the owner accepts; if they decline or do not answer, the hold is released.',
        'Always pay on Cappy. A payment made any other way is not protected: no refund, no dispute, no review. Someone asking you to pay outside Cappy is a reason to report them.',
        'Every booking has an invoice under Earn → Invoices for the owner and in the booking for you.',
      ],
      [
        'Mit deiner Anfrage wird der Gesamtbetrag inklusive Gebühr auf deiner Karte reserviert. Abgebucht wird erst, wenn der Anbieter annimmt; lehnt er ab oder antwortet nicht, wird die Reservierung aufgehoben.',
        'Bezahle immer über Cappy. Eine Zahlung auf anderem Weg ist nicht geschützt: keine Erstattung, kein Widerspruch, keine Bewertung. Wer dich bittet, außerhalb von Cappy zu zahlen, sollte gemeldet werden.',
        'Zu jeder Buchung gibt es eine Rechnung.',
      ],
    ],
  },
  cancelling: {
    title: ['Cancelling and refunds', 'Stornieren und Erstattung'],
    body: [
      [
        'You can cancel before the booked time starts. The listing’s policy decides the refund, and the cancel screen shows the exact amount before you confirm.',
        'After the time has started you cannot cancel. If something went wrong, open a problem on the booking instead: the money is held until support has looked at it.',
        'Refunds go back to the card you paid with, usually within 5 to 10 days depending on your bank.',
      ],
      [
        'Du kannst stornieren, bevor die gebuchte Zeit beginnt. Die Bedingungen des Inserats bestimmen die Erstattung; der genaue Betrag steht vor dem Bestätigen da.',
        'Hat die Zeit begonnen, ist keine Stornierung mehr möglich. Ist etwas schiefgelaufen, melde in der Buchung ein Problem: Das Geld wird gehalten, bis der Support es geprüft hat.',
        'Erstattungen gehen auf die Karte, mit der du bezahlt hast, meist innerhalb von 5 bis 10 Tagen, je nach Bank.',
      ],
    ],
  },
  earning: {
    title: ['Listing and getting paid', 'Inserieren und Auszahlung'],
    body: [
      [
        'List something under Earn: what it is, where, the price per hour and the times it is free. You decide on every request unless you turn on instant book.',
        'Payouts go through Stripe to your bank account. Set them up once under Earn; you are paid after each booking is completed. Cappy’s fee is inside the price the renter pays.',
        'A request left unanswered expires after 24 hours. Answering quickly shows on your listing and brings more bookings.',
      ],
      [
        'Inseriere unter Verdienen: was es ist, wo, den Stundenpreis und die freien Zeiten. Du entscheidest über jede Anfrage, außer du schaltest Sofortbuchung ein.',
        'Auszahlungen laufen über Stripe auf dein Bankkonto. Richte sie einmal unter Verdienen ein; ausgezahlt wird nach jeder abgeschlossenen Buchung. Die Gebühr von Cappy steckt im Preis, den der Mieter zahlt.',
        'Eine unbeantwortete Anfrage verfällt nach 24 Stunden. Schnelle Antworten stehen auf deinem Inserat und bringen mehr Buchungen.',
      ],
    ],
  },
  handover: {
    title: ['The hand-over', 'Die Übergabe'],
    body: [
      [
        'The address and access instructions appear on the booking once it is accepted. Use the booking’s messages to agree the details.',
        'Take photos at the start and at the end, in the booking. They carry the time they were added and are what support looks at if there is a disagreement about damage.',
        'Either side can mark the hand-over from 30 minutes before the booked time.',
      ],
      [
        'Adresse und Zugangshinweise erscheinen in der Buchung, sobald sie angenommen ist. Stimmt die Einzelheiten über die Nachrichten der Buchung ab.',
        'Mach zu Beginn und am Ende Fotos in der Buchung. Sie tragen den Zeitpunkt, zu dem sie hinzugefügt wurden, und sind das, was der Support bei einem Streit über Schäden ansieht.',
        'Beide Seiten können die Übergabe ab 30 Minuten vor der gebuchten Zeit bestätigen.',
      ],
    ],
  },
  problems: {
    title: ['When something goes wrong', 'Wenn etwas schiefgeht'],
    body: [
      [
        'Write to the other side first, in the booking. Most things are a misunderstanding about times or access.',
        'If it cannot be settled, open a problem on the booking. The payment is held, the booking does not complete on its own, and a person at Cappy decides whether the owner is paid or you are refunded.',
        'If you feel unsafe, leave and contact the local emergency services (112) first.',
      ],
      [
        'Schreib zuerst der anderen Seite in der Buchung. Meist ist es ein Missverständnis über Zeiten oder Zugang.',
        'Lässt es sich nicht klären, melde in der Buchung ein Problem. Die Zahlung wird gehalten, die Buchung schließt nicht von selbst ab, und ein Mensch bei Cappy entscheidet, ob der Anbieter bezahlt oder dir erstattet wird.',
        'Fühlst du dich unsicher, geh und ruf zuerst den Notruf (112).',
      ],
    ],
  },
  safety: {
    title: ['How we keep you safe', 'Wie wir dich schützen'],
    body: [
      [
        'Members only. Listings are people’s own property, places and times, so nothing is shown until you sign in, and every booking is tied to a real account.',
        'Contact details are hidden in messages until a booking is accepted, so the conversation and the payment stay on Cappy, where they are protected.',
        'Larger bookings need a one-time ID check. Reviews are blind: neither side sees the other’s until both have rated, or 14 days have passed.',
        'You can report any listing, profile, message or review, and block anyone. Reports are read by a person.',
      ],
      [
        'Nur für Mitglieder. Inserate sind Eigentum, Orte und Zeiten von Menschen; deshalb ist nichts sichtbar, bevor du dich anmeldest, und jede Buchung gehört zu einem echten Konto.',
        'Kontaktdaten in Nachrichten sind verborgen, bis eine Buchung angenommen ist, damit Gespräch und Zahlung auf Cappy bleiben, wo sie geschützt sind.',
        'Größere Buchungen brauchen eine einmalige Ausweisprüfung. Bewertungen sind verdeckt: Keine Seite sieht die der anderen, bevor beide bewertet haben oder 14 Tage vergangen sind.',
        'Du kannst jedes Inserat, Profil, jede Nachricht und Bewertung melden und jeden blockieren. Meldungen liest ein Mensch.',
      ],
    ],
  },
  reviews: {
    title: ['Reviews', 'Bewertungen'],
    body: [
      [
        'After a completed booking both sides rate each other: the renter rates the listing, the owner rates the renter.',
        'Reviews are published together, once both have rated or 14 days after the booking, so nobody rates in reply to the other.',
      ],
      [
        'Nach einer abgeschlossenen Buchung bewerten sich beide Seiten: Der Mieter bewertet das Inserat, der Anbieter den Mieter.',
        'Bewertungen erscheinen gemeinsam, sobald beide bewertet haben oder 14 Tage nach der Buchung, damit niemand als Antwort auf den anderen bewertet.',
      ],
    ],
  },
  account: {
    title: ['Your account and data', 'Dein Konto und deine Daten'],
    body: [
      [
        'Download everything Cappy holds about you under You → Your data.',
        'You can delete your account in the app under You. While a booking is open or a payout is pending, finish those first; the app tells you which and until when. Invoices and payment records are kept without your name for as long as tax law requires (up to ten years in Germany).',
        'Signed in on a device you no longer have? Use “Sign out everywhere” under You.',
      ],
      [
        'Lade unter Du → Deine Daten alles herunter, was Cappy über dich speichert.',
        'Dein Konto kannst du in der App unter Du löschen. Solange eine Buchung offen oder eine Auszahlung ausstehend ist, schließe sie zuerst ab; die App sagt dir, welche und bis wann. Rechnungen und Zahlungsbelege bewahren wir ohne deinen Namen so lange auf, wie das Steuerrecht es verlangt (in Deutschland bis zu zehn Jahre).',
        'Auf einem Gerät angemeldet, das du nicht mehr hast? Nutze „Überall abmelden“ unter Du.',
      ],
    ],
  },
  notifications: {
    title: ['Notifications', 'Benachrichtigungen'],
    body: [
      [
        'Cappy notifies you about your bookings and messages only: a new request, an answer, a hand-over, a payout. Never marketing unless you ask for it.',
        'Everything also arrives by email and in the bell in the app, so turning push off loses nothing.',
      ],
      [
        'Cappy benachrichtigt dich nur über deine Buchungen und Nachrichten: eine neue Anfrage, eine Antwort, eine Übergabe, eine Auszahlung. Werbung nie, außer du willst sie.',
        'Alles kommt auch per E-Mail und in der Glocke in der App an; ohne Push verpasst du also nichts.',
      ],
    ],
  },
}

const SUPPORT = (import.meta.env.VITE_LEGAL_EMAIL as string | undefined)?.trim()

/** Write to support, with the booking attached when there is one. */
export function supportHref(bookingId?: string): string {
  if (!SUPPORT) return '/legal/impressum'
  const subject = bookingId ? `Booking ${bookingId}` : 'Cappy'
  return `mailto:${SUPPORT}?subject=${encodeURIComponent(subject)}`
}

const pick = <T,>(pair: [T, T]): T => (lang() === 'de' ? pair[1] : pair[0])

export function Help() {
  const { topic } = useParams()
  if (topic) {
    const a = ARTICLES[topic]
    if (!a) return <NotFound />
    return (
      <Screen eyebrow={t('Help')} title={pick(a.title)} back="/help">
        <article className="space-y-4 pb-8 text-[15px] leading-[24px] text-[var(--ink-2)]">
          {pick(a.body).map((p) => (
            <p key={p}>{p}</p>
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
            <Link to={`/help/${key}`} className="flex min-h-[52px] items-center justify-between gap-4 py-3 text-[15px] font-semibold">
              {pick(a.title)}
              <span aria-hidden="true" className="text-[var(--ink-4)]">›</span>
            </Link>
          </li>
        ))}
        <li>
          <Link to="/legal/report" className="flex min-h-[52px] items-center justify-between gap-4 py-3 text-[15px] font-semibold">
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
      <a href={supportHref()} className="text-[14px] font-semibold underline">
        {t('Write to Cappy')}
      </a>
    </Card>
  )
}
