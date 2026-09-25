import type { ReactNode } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { Screen } from '../components/AppShell.tsx'
import { Banner } from '../components/ui.tsx'
import { NotFound } from './NotFound.tsx'
import { lang, t } from '../../i18n.ts'

/** The operator's details, from the build (never invented). */
const env = (k: string) => (import.meta.env[k] as string | undefined)?.trim() || undefined
const OPERATOR = {
  company: env('VITE_LEGAL_COMPANY'),
  address: env('VITE_LEGAL_ADDRESS'),
  email: env('VITE_LEGAL_EMAIL'),
  register: env('VITE_LEGAL_REGISTER'),
  vat: env('VITE_LEGAL_VAT'),
}
const complete = Boolean(OPERATOR.company && OPERATOR.address && OPERATOR.email)
// Words, not constants: they follow the language.
const operatorName = () => OPERATOR.company ?? (lang() === 'de' ? 'der im Impressum genannte Betreiber' : 'the operator named in the Impressum')
const contactAddr = () => OPERATOR.email ?? (lang() === 'de' ? 'siehe Impressum' : 'the address in the Impressum')
const FEE = `${PLATFORM_FEE_BPS / 100}%`
const FEE_DE = `${PLATFORM_FEE_BPS / 100} %`

const PAGES: Record<string, { title: string; titleDe: string; body: () => ReactNode }> = {
  impressum: { title: 'Impressum', titleDe: 'Impressum', body: () => <Impressum /> },
  privacy: { title: 'Privacy Policy', titleDe: 'Datenschutz', body: () => (lang() === 'de' ? <PrivacyDe /> : <Privacy />) },
  terms: { title: 'Terms of Use', titleDe: 'AGB', body: () => (lang() === 'de' ? <TermsDe /> : <Terms />) },
  withdrawal: { title: 'Right of withdrawal', titleDe: 'Widerruf', body: () => (lang() === 'de' ? <WithdrawalDe /> : <Withdrawal />) },
  ranking: { title: 'How ranking works', titleDe: 'Ranking', body: () => (lang() === 'de' ? <RankingDe /> : <Ranking />) },
  report: { title: 'Reporting content', titleDe: 'Inhalte melden', body: () => (lang() === 'de' ? <ReportingDe /> : <Reporting />) },
  accessibility: {
    title: 'Accessibility',
    titleDe: 'Barrierefreiheit',
    body: () => (lang() === 'de' ? <AccessibilityDe /> : <Accessibility />),
  },
}

const titleOf = (p: { title: string; titleDe: string }) => (lang() === 'de' ? p.titleDe : p.title)

export function Legal() {
  const { page = '' } = useParams()
  const p = PAGES[page]
  if (!p) return <NotFound />
  return (
    <Screen title={titleOf(p)} back="/profile">
      <nav aria-label={t('Legal pages')} className="mb-6 flex flex-wrap gap-x-5 gap-y-2 text-[14px] font-semibold">
        {Object.entries(PAGES).map(([key, v]) => (
          <NavLink
            key={key}
            to={`/legal/${key}`}
            className={({ isActive }) => (isActive ? 'text-[var(--ink)] underline underline-offset-4' : 'text-[var(--ink-4)]')}
          >
            {titleOf(v)}
          </NavLink>
        ))}
      </nav>
      {!complete && (
        <div className="mb-6">
          <Banner
            tone="warn"
            title={t('Operator details to be completed before launch')}
            body={t('The company name, address and contact for this service are not configured in this build.')}
          />
        </div>
      )}
      <article className="legal space-y-4 pb-8 text-[15px] leading-[24px] text-[var(--ink-2)]">{p.body()}</article>
    </Screen>
  )
}

/** Public, signed in or not: how to delete an account (Google Play asks for this URL). */
export function AccountDeletion() {
  const de = lang() === 'de'
  return (
    <Screen title={de ? 'Konto löschen' : 'Delete your Cappy account'} back="/profile">
      <article className="legal space-y-4 pb-8 text-[15px] leading-[24px] text-[var(--ink-2)]">
        {de ? (
          <>
            <p>So löschst du dein Konto, in der App oder auf cappy.app:</p>
            <ol className="list-decimal space-y-2 pl-5">
              <li>Melde dich an.</li>
              <li>Öffne <em>Du</em> (Profil).</li>
              <li>Wähle <em>Konto löschen</em> und bestätige.</li>
            </ol>
            <p>
              Dein Profil wird anonymisiert, deine Inserate werden sofort entfernt, deine Anmeldung wird gelöscht.
              Solange eine Buchung noch offen ist, schließe sie zuerst ab oder storniere sie. Buchungen und Zahlungen
              bewahren wir ohne deinen Namen so lange auf, wie Steuer- und Handelsrecht es verlangen (in Deutschland
              bis zu zehn Jahre). Vorher kannst du unter <em>Du → Deine Daten</em> eine Kopie deiner Daten herunterladen.
            </p>
            <p>Kannst du dich nicht mehr anmelden? Schreib uns (Kontakt: {contactAddr()}); wir löschen dein Konto nach Prüfung.</p>
          </>
        ) : (
          <>
            <p>To delete your account, in the app or on cappy.app:</p>
            <ol className="list-decimal space-y-2 pl-5">
              <li>Sign in.</li>
              <li>Open <em>You</em> (your profile).</li>
              <li>Choose <em>Delete account</em> and confirm.</li>
            </ol>
            <p>
              Your profile is anonymised, your listings are taken down at once and your sign-in is deleted. If a booking
              is still open, finish or cancel it first. Bookings and payments are kept without your name for as long as
              tax and commercial law requires (up to ten years in Germany). Before deleting, you can download a copy of
              your data under <em>You → Your data</em>.
            </p>
            <p>Cannot sign in any more? Write to {contactAddr()} and we will delete the account once we have checked it is yours.</p>
          </>
        )}
      </article>
    </Screen>
  )
}

function H({ children }: { children: ReactNode }) {
  return <h2 className="t-h3 pt-4 text-[var(--ink)]">{children}</h2>
}

function Impressum() {
  return (
    <>
      <p>Angaben gemäß § 5 DDG</p>
      {complete ? (
        <p>
          {OPERATOR.company}
          <br />
          {OPERATOR.address?.split(',').map((line, i) => (
            <span key={i}>
              {line.trim()}
              <br />
            </span>
          ))}
          E-Mail: <a href={`mailto:${OPERATOR.email}`}>{OPERATOR.email}</a>
        </p>
      ) : (
        <p>{t("The operator's name, address and email are added here before launch.")}</p>
      )}
      {OPERATOR.register && <p>{OPERATOR.register}</p>}
      {OPERATOR.vat && <p>USt-IdNr.: {OPERATOR.vat}</p>}
      <p>
        {/* The EU ODR platform was shut down in July 2025 (Regulation (EU) 2024/3228), so no link to it. */}
        Wir sind nicht verpflichtet und nicht bereit, an Streitbeilegungsverfahren vor einer
        Verbraucherschlichtungsstelle teilzunehmen (§ 36 VSBG).
      </p>
    </>
  )
}

function Privacy() {
  return (
    <>
      <p>
        This policy explains what personal data Cappy processes, why, and your rights. Cappy is a
        marketplace where people and businesses rent out idle capacity by the hour.
      </p>
      <H>Who is responsible</H>
      <p>
        The controller is {operatorName()}. Contact: {contactAddr()}.
      </p>
      <H>What we process and why</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>
          <strong>Account</strong>: your email address and password (held by our sign-in provider),
          to create and secure your account. Legal basis: performance of contract (Art. 6(1)(b) GDPR).
        </li>
        <li>
          <strong>Profile and listings</strong>: your name, district, whether you are a person or a
          business, what you list (descriptions, photos, prices, available times, the handover
          address) and your ratings. To run the marketplace. Art. 6(1)(b).
        </li>
        <li>
          <strong>Bookings and payments</strong>: what you booked or rented out, when, for how much,
          and the payment status. Card and bank details are entered with Stripe and never reach us.
          Art. 6(1)(b), and legal obligations for accounting records (Art. 6(1)(c)).
        </li>
        <li>
          <strong>Emails</strong>: sign-up codes and booking updates. Art. 6(1)(b).
        </li>
        <li>
          <strong>Technical data</strong>: IP address, device and request logs, to keep the service
          secure and working, kept for up to 90 days. Legitimate interest (Art. 6(1)(f)).
        </li>
      </ul>
      <H>Who processes it for us</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>Amazon Web Services EMEA (hosting, sign-in with Amazon Cognito, email with Amazon SES), in the EU (Frankfurt, eu-central-1).</li>
        <li>Stripe Payments Europe (card payments and payouts to owners), which acts as an independent controller for payment data.</li>
      </ul>
      <p>We do not sell your data or use it for advertising.</p>
      <H>How long we keep it</H>
      <p>
        Your account and profile for as long as you have the account. When you delete it, your
        profile is anonymised and your listings are taken down at once. Bookings and payments are
        kept for as long as tax and commercial law requires (up to ten years in Germany), without
        your name.
      </p>
      <H>Your rights</H>
      <p>
        You can access, correct, export and delete your data. Export and deletion are in the app
        under <em>You → Your data</em>. You can also object to processing based on legitimate
        interest, restrict processing, and complain to a data protection authority. Write to{' '}
        {contactAddr()} for anything else.
      </p>
    </>
  )
}

function Terms() {
  return (
    <>
      <H>What Cappy is</H>
      <p>
        Cappy connects owners of idle capacity (machines, workshops, vehicles, space) with people who
        want to use it for a while. The rental contract is between the owner and the buyer; Cappy
        runs the platform and handles the payment. Cappy is operated by {operatorName()}.
      </p>
      <H>Accounts</H>
      <p>
        You must give accurate details and keep your sign-in safe. You can delete your account at
        any time in the app, once you have no booking still open.
      </p>
      <H>Listing</H>
      <p>
        Owners describe what they offer truthfully, only list what they may rent out, keep it safe
        to use, and are present (or make it available) at the times they list. Payment is only taken
        through Cappy; asking for payment outside the platform is not allowed.
      </p>
      <H>Booking and payment</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>When you request a booking, the price is held on your card, not charged.</li>
        <li>The card is charged when the owner accepts. If they decline, or do not answer in time, the hold is released.</li>
        <li>The owner is paid when the booking is complete. Cappy keeps a {FEE} fee, included in the price shown.</li>
      </ul>
      <H>Cancelling and problems</H>
      <p>
        Either side can cancel before the booked time starts; the buyer then gets everything back.
        Once it has started, the buyer can report a problem instead: the owner's payout is held while
        Cappy looks into it and decides on a refund or a payout. Statutory rights are not affected.
      </p>
      <H>Right of withdrawal</H>
      <p>
        If you book as a consumer from an owner who is a business, you may withdraw from the booking
        without giving a reason until the booked time starts: open the booking and press
        “Withdraw from this booking”. You get back everything you paid, in full, within 14 days, to
        the card you paid with. Where you asked for the service to start within the withdrawal
        period and it has started, you pay only for the part already provided. You can also withdraw
        by telling {operatorName()} at {contactAddr()}, for example with this sentence: “I hereby withdraw from
        the contract for the following booking: [booking reference], booked on [date], [name,
        address].” Bookings from private owners have no statutory right of withdrawal; you can
        still cancel before the start for a full refund under these terms. The full instructions and the model form
        are under <NavLink to="/legal/withdrawal" className="underline">Right of withdrawal</NavLink>.
      </p>
      <H>Reviews, ranking and reporting</H>
      <p>
        Reviews come only from completed bookings, written by the buyer. How results are ordered is
        explained under “How ranking works”; nobody can pay to rank higher. Anyone can report a
        listing, profile, message or review with “Report”; we tell the reporter what we decide and
        give reasons to anyone whose content we remove or whose account we restrict.
      </p>
      <H>Liability</H>
      <p>
        Owners are responsible for what they rent out and buyers for how they use it. Cappy is liable
        without limit for intent and gross negligence and for injury to life, body or health;
        otherwise only for breach of essential obligations, limited to the damage typical and
        foreseeable for such contracts.
      </p>
      <H>Changes and law</H>
      <p>
        We tell you about changes to these terms in advance by email. German law applies, without
        taking away protection the law of your country of residence gives you as a consumer.
      </p>
    </>
  )
}

function Ranking() {
  return (
    <>
      <p>
        When you search, Cappy orders results by how well each listing fits what you asked for. The main
        parameters, in rough order of weight, are:
      </p>
      <ul className="list-disc space-y-2 pl-5">
        <li><strong>Time fit</strong>: whether the listing is free when you need it, and how soon.</li>
        <li><strong>Distance</strong> from where you search.</li>
        <li><strong>Price</strong> for the job you described, fee included.</li>
        <li><strong>Rating</strong> from completed bookings.</li>
        <li><strong>Reliability</strong>: finishing on time, answering quickly, not cancelling.</li>
      </ul>
      <p>
        You can re-sort by price, distance or soonest. Nobody can pay for a better position: Cappy has no
        paid ranking and no advertising in results. Listings of owners who cannot receive payouts yet, and
        listings removed under our terms, do not appear.
      </p>
    </>
  )
}

/** The accessibility statement the BFSG asks of a consumer service (since 28 June 2025). */
function Accessibility() {
  return (
    <>
      <p>
        Cappy aims to meet the Web Content Accessibility Guidelines (WCAG) 2.1 at level AA, as EN 301 549 requires, on the
        web and in the iOS and Android apps.
      </p>
      <H>How far we are</H>
      <p>
        Partly conformant. This is our own assessment, not yet an independent audit. What we know is not there yet:
      </p>
      <ul className="list-disc space-y-1 pl-5">
        <li>Panning and zooming the map on Explore needs a pointer or touch; the list shows the same listings.</li>
        <li>Photos that owners upload have their listing’s title as the description, not a description of the photo.</li>
        <li>Very large text sizes are not yet checked on every screen of the apps.</li>
      </ul>
      <H>How the service works</H>
      <p>
        Cappy lets members book the hours of workshops, vehicles, machines and rooms that others own, and list their own.
        Everything works with a keyboard and a screen reader, text can be enlarged to 200% and colours meet the AA
        contrast ratio. Statuses are written out, never shown by colour alone.
      </p>
      <H>Tell us</H>
      <p>
        Found something you cannot use? Write to {contactAddr()} and say what and where. We answer within two weeks.
      </p>
      <H>Enforcement</H>
      <p>
        If our answer does not help, you can turn to the Marktüberwachungsstelle der Länder für die Barrierefreiheit von
        Produkten und Dienstleistungen (MLBF), Magdeburg.
      </p>
      <p className="t-sm text-[var(--ink-4)]">Prepared September 2026.</p>
    </>
  )
}

function AccessibilityDe() {
  return (
    <>
      <p>
        Cappy soll die Richtlinien für barrierefreie Webinhalte (WCAG) 2.1 auf Stufe AA erfüllen, wie es EN 301 549
        verlangt, im Web und in den Apps für iOS und Android.
      </p>
      <H>Stand der Vereinbarkeit</H>
      <p>Teilweise vereinbar. Das ist unsere eigene Bewertung, noch keine unabhängige Prüfung. Bekannt ist:</p>
      <ul className="list-disc space-y-1 pl-5">
        <li>Verschieben und Zoomen der Karte unter Entdecken braucht Maus oder Touch; die Liste zeigt dieselben Inserate.</li>
        <li>Fotos, die Anbieter hochladen, tragen den Titel des Inserats als Beschreibung, keine Bildbeschreibung.</li>
        <li>Sehr große Schriftgrößen sind in den Apps noch nicht auf jedem Bildschirm geprüft.</li>
      </ul>
      <H>Wie der Dienst funktioniert</H>
      <p>
        Mit Cappy buchen Mitglieder die Stunden von Werkstätten, Fahrzeugen, Maschinen und Räumen anderer und inserieren
        ihre eigenen. Alles ist mit Tastatur und Screenreader bedienbar, Text lässt sich auf 200 % vergrößern, die Farben
        erfüllen das AA-Kontrastverhältnis. Status stehen immer als Text da, nie nur als Farbe.
      </p>
      <H>Feedback</H>
      <p>
        Etwas ist für dich nicht nutzbar? Schreib an {contactAddr()}, was und wo. Wir antworten innerhalb von zwei Wochen.
      </p>
      <H>Durchsetzung</H>
      <p>
        Hilft unsere Antwort nicht, kannst du dich an die Marktüberwachungsstelle der Länder für die Barrierefreiheit von
        Produkten und Dienstleistungen (MLBF) in Magdeburg wenden.
      </p>
      <p className="t-sm text-[var(--ink-4)]">Erstellt im September 2026.</p>
    </>
  )
}

function Reporting() {
  return (
    <>
      <p>
        See something illegal, unsafe or against our terms? Use “Report” on the listing, profile, message or
        review. You do not need an account; without one, leave an email so we can reply. We acknowledge
        every report, look at it, and tell you what we decided. When we remove content or restrict an account
        we tell the person affected why, and how to disagree.
      </p>
      <p>
        Authorities and anyone else can reach us at {contactAddr()}. If someone is in immediate danger, call 112
        first.
      </p>
    </>
  )
}

function Withdrawal() {
  return (
    <>
      <p>
        This applies when you book as a consumer from an owner who is a business (shown as “Business” on the owner's
        card). Bookings from private people carry no statutory right of withdrawal; you can still cancel them before the
        start for a full refund under our terms.
      </p>
      <H>Right of withdrawal</H>
      <p>
        You have the right to withdraw from this contract within fourteen days without giving any reason. The
        withdrawal period is fourteen days from the day the contract is concluded (when the owner accepts your
        booking). To exercise it, press “Withdraw from this booking” on the booking, or tell {operatorName()} ({contactAddr()})
        by a clear statement, for example by email. You may use the model form below; it is not obligatory. It is enough
        to send your statement before the period ends.
      </p>
      <H>Effects of withdrawal</H>
      <p>
        If you withdraw, we refund all payments received from you without undue delay and at the latest within fourteen
        days, using the same means of payment you used, at no cost to you. If you asked for the service to begin during
        the withdrawal period, you pay an amount proportionate to what was already provided up to the moment you told us
        of the withdrawal. Your right of withdrawal ends once the booked service has been fully provided.
      </p>
      <H>Model withdrawal form</H>
      <p className="whitespace-pre-line rounded-[var(--radius-card)] bg-[var(--sunken)] p-4">
        {`To ${OPERATOR.company ?? '[operator]'}, ${OPERATOR.address ?? '[address]'}, ${OPERATOR.email ?? '[email]'}:
I/We (*) hereby give notice that I/we (*) withdraw from my/our (*) contract for the provision of the following service:
Booking reference:
Ordered on (*) / received on (*):
Name of consumer(s):
Address of consumer(s):
Signature of consumer(s) (only if this form is notified on paper):
Date:
(*) Delete as appropriate.`}
      </p>
    </>
  )
}

function WithdrawalDe() {
  return (
    <>
      <p>
        Das gilt, wenn du als Verbraucher bei einem Anbieter buchst, der Unternehmer ist (auf der Karte als
        „Unternehmen“ gekennzeichnet). Buchungen bei Privatpersonen haben kein gesetzliches Widerrufsrecht; du kannst sie
        nach unseren AGB aber vor Beginn stornieren und bekommst alles zurück.
      </p>
      <H>Widerrufsbelehrung</H>
      <p>
        <strong>Widerrufsrecht.</strong> Du hast das Recht, binnen vierzehn Tagen ohne Angabe von Gründen diesen Vertrag
        zu widerrufen. Die Widerrufsfrist beträgt vierzehn Tage ab dem Tag des Vertragsschlusses (wenn der Anbieter deine
        Buchung annimmt). Um dein Widerrufsrecht auszuüben, tippe bei der Buchung auf „Von dieser Buchung zurücktreten“
        oder informiere uns (Kontakt: {contactAddr()}) mittels einer eindeutigen Erklärung, zum Beispiel per E-Mail,
        über deinen Entschluss, diesen Vertrag zu widerrufen. Du kannst dafür das unten stehende Muster-Widerrufsformular
        verwenden, das jedoch nicht vorgeschrieben ist. Zur Wahrung der Widerrufsfrist reicht es aus, dass du die
        Mitteilung vor Ablauf der Frist absendest.
      </p>
      <H>Folgen des Widerrufs</H>
      <p>
        Wenn du diesen Vertrag widerrufst, zahlen wir dir alle Zahlungen, die wir von dir erhalten haben, unverzüglich und
        spätestens binnen vierzehn Tagen ab dem Tag zurück, an dem die Mitteilung über deinen Widerruf bei uns eingegangen
        ist. Für diese Rückzahlung verwenden wir dasselbe Zahlungsmittel, das du bei der ursprünglichen Transaktion
        eingesetzt hast; dir werden dafür keine Entgelte berechnet. Hast du verlangt, dass die Dienstleistung während der
        Widerrufsfrist beginnen soll, so hast du uns einen angemessenen Betrag zu zahlen, der dem Anteil der bis zu dem
        Zeitpunkt, zu dem du uns von der Ausübung des Widerrufsrechts unterrichtest, bereits erbrachten Leistungen
        entspricht. Das Widerrufsrecht erlischt, wenn die gebuchte Leistung vollständig erbracht ist.
      </p>
      <H>Muster-Widerrufsformular</H>
      <p className="whitespace-pre-line rounded-[var(--radius-card)] bg-[var(--sunken)] p-4">
        {`An ${OPERATOR.company ?? '[Betreiber]'}, ${OPERATOR.address ?? '[Anschrift]'}, ${OPERATOR.email ?? '[E-Mail]'}:
Hiermit widerrufe(n) ich/wir (*) den von mir/uns (*) abgeschlossenen Vertrag über die Erbringung der folgenden Dienstleistung:
Buchungsnummer:
Bestellt am (*) / erhalten am (*):
Name des/der Verbraucher(s):
Anschrift des/der Verbraucher(s):
Unterschrift des/der Verbraucher(s) (nur bei Mitteilung auf Papier):
Datum:
(*) Unzutreffendes streichen.`}
      </p>
    </>
  )
}

function PrivacyDe() {
  return (
    <>
      <p>
        Diese Erklärung beschreibt, welche personenbezogenen Daten Cappy verarbeitet, warum, und welche Rechte du hast.
        Cappy ist ein Marktplatz, auf dem Menschen und Unternehmen ungenutzte Kapazität stundenweise vermieten.
      </p>
      <H>Verantwortlicher</H>
      <p>
        Verantwortlich ist {operatorName()}. Kontakt: {contactAddr()}.
      </p>
      <H>Was wir verarbeiten und warum</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>
          <strong>Konto</strong>: deine E-Mail-Adresse und dein Passwort (bei unserem Anmeldedienst gespeichert), um dein
          Konto einzurichten und zu schützen. Rechtsgrundlage: Vertragserfüllung (Art. 6 Abs. 1 lit. b DSGVO).
        </li>
        <li>
          <strong>Profil und Inserate</strong>: dein Name, dein Stadtteil, ob du Privatperson oder Unternehmen bist, was
          du inserierst (Beschreibungen, Fotos, Preise, freie Zeiten, die Übergabeadresse) und deine Bewertungen, um den
          Marktplatz zu betreiben. Art. 6 Abs. 1 lit. b DSGVO.
        </li>
        <li>
          <strong>Buchungen und Zahlungen</strong>: was du gebucht oder vermietet hast, wann, zu welchem Preis, und der
          Zahlungsstatus. Karten- und Bankdaten gibst du bei Stripe ein; sie erreichen uns nie. Art. 6 Abs. 1 lit. b
          DSGVO sowie gesetzliche Aufbewahrungspflichten (Art. 6 Abs. 1 lit. c DSGVO).
        </li>
        <li>
          <strong>Nachrichten, Übergabefotos und Meldungen</strong>: was du über eine Buchung schreibst, Fotos bei
          Übergabe und Rückgabe und Meldungen an uns, um Buchungen abzuwickeln, Streitfälle zu klären und rechtswidrige
          Inhalte zu bearbeiten. Art. 6 Abs. 1 lit. b und c DSGVO.
        </li>
        <li>
          <strong>Identitätsprüfung</strong> (nur für hochwertige Buchungen): Stripe prüft ein Ausweisdokument und ein
          Selfie; wir erhalten nur das Ergebnis. Art. 6 Abs. 1 lit. b und f DSGVO.
        </li>
        <li>
          <strong>E-Mails und Push-Mitteilungen</strong>: Bestätigungscodes und Neuigkeiten zu Buchungen. Art. 6 Abs. 1
          lit. b DSGVO.
        </li>
        <li>
          <strong>Technische Daten</strong>: IP-Adresse, Gerät und Protokolle der Anfragen, um den Dienst sicher und
          funktionsfähig zu halten, bis zu 90 Tage lang. Berechtigtes Interesse (Art. 6 Abs. 1 lit. f DSGVO).
        </li>
      </ul>
      <H>Wer die Daten für uns verarbeitet</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>Amazon Web Services EMEA (Hosting, Anmeldung mit Amazon Cognito, E-Mail mit Amazon SES) in der EU (Frankfurt, eu-central-1).</li>
        <li>Stripe Payments Europe (Kartenzahlungen, Auszahlungen an Anbieter, Identitätsprüfung), als eigenständig Verantwortlicher für Zahlungsdaten.</li>
        <li>Apple und Google, wenn du Push-Mitteilungen in der App erlaubst.</li>
      </ul>
      <p>Wir verkaufen deine Daten nicht und nutzen sie nicht für Werbung.</p>
      <H>Wie lange wir sie speichern</H>
      <p>
        Konto und Profil, solange du das Konto hast. Löschst du es, wird dein Profil anonymisiert und deine Inserate
        werden sofort entfernt. Buchungen und Zahlungen bewahren wir ohne deinen Namen so lange auf, wie Steuer- und
        Handelsrecht es verlangen (in Deutschland bis zu zehn Jahre).
      </p>
      <H>Deine Rechte</H>
      <p>
        Du kannst Auskunft über deine Daten verlangen, sie berichtigen, exportieren und löschen lassen. Export und Löschung
        findest du in der App unter <em>Du → Deine Daten</em>. Du kannst außerdem einer Verarbeitung auf Grundlage
        berechtigter Interessen widersprechen, die Verarbeitung einschränken lassen und dich bei einer
        Datenschutz-Aufsichtsbehörde beschweren. Für alles andere schreib uns (Kontakt: {contactAddr()}).
      </p>
    </>
  )
}

function TermsDe() {
  return (
    <>
      <H>Was Cappy ist</H>
      <p>
        Cappy bringt Anbieter ungenutzter Kapazität (Maschinen, Werkstätten, Fahrzeuge, Flächen) mit Menschen zusammen, die
        sie für eine Weile nutzen wollen. Der Mietvertrag kommt zwischen Anbieter und Buchendem zustande; Cappy betreibt
        die Plattform und wickelt die Zahlung ab. Betreiber von Cappy ist {operatorName()}.
      </p>
      <H>Konten</H>
      <p>
        Du machst richtige Angaben und schützt deine Anmeldedaten. Du kannst dein Konto jederzeit in der App löschen,
        sobald keine Buchung mehr offen ist.
      </p>
      <H>Inserieren</H>
      <p>
        Anbieter beschreiben ihr Angebot wahrheitsgemäß, inserieren nur, was sie vermieten dürfen, halten es sicher
        nutzbar und sind zu den angegebenen Zeiten da (oder stellen es bereit). Bezahlt wird nur über Cappy; Zahlungen
        außerhalb der Plattform zu verlangen, ist nicht erlaubt.
      </p>
      <H>Buchen und Bezahlen</H>
      <ul className="list-disc space-y-2 pl-5">
        <li>Wenn du eine Buchung anfragst, wird der Preis auf deiner Karte reserviert, nicht belastet.</li>
        <li>Belastet wird die Karte, wenn der Anbieter annimmt. Lehnt er ab oder antwortet nicht rechtzeitig, wird die Reservierung aufgehoben.</li>
        <li>Der Anbieter wird bezahlt, wenn die Buchung abgeschlossen ist. Cappy behält eine Gebühr von {FEE_DE}; sie ist im angezeigten Preis enthalten.</li>
      </ul>
      <H>Stornieren und Probleme</H>
      <p>
        Beide Seiten können stornieren, bevor die gebuchte Zeit beginnt; der Buchende bekommt dann alles zurück. Hat sie
        begonnen, kann der Buchende stattdessen ein Problem melden: Die Auszahlung an den Anbieter wird zurückgehalten,
        während Cappy den Fall prüft und über Erstattung oder Auszahlung entscheidet. Gesetzliche Rechte bleiben unberührt.
      </p>
      <H>Widerrufsrecht</H>
      <p>
        Buchst du als Verbraucher bei einem Anbieter, der Unternehmer ist, hast du ein gesetzliches Widerrufsrecht. Die
        Einzelheiten und das Muster-Widerrufsformular findest du unter <NavLink to="/legal/withdrawal" className="underline">Widerruf</NavLink>.
        Buchungen bei Privatpersonen haben kein gesetzliches Widerrufsrecht; vor Beginn kannst du sie trotzdem nach diesen
        AGB stornieren und bekommst alles zurück.
      </p>
      <H>Bewertungen, Ranking und Meldungen</H>
      <p>
        Bewertungen stammen nur aus abgeschlossenen Buchungen und werden vom Buchenden geschrieben. Wie Ergebnisse sortiert
        werden, erklären wir unter „Ranking“; bessere Platzierungen kann niemand kaufen. Jeder kann ein Inserat, ein Profil,
        eine Nachricht oder eine Bewertung mit „Melden“ melden; wir teilen der meldenden Person unsere Entscheidung mit und
        begründen sie gegenüber jedem, dessen Inhalte wir entfernen oder dessen Konto wir einschränken.
      </p>
      <H>Haftung</H>
      <p>
        Anbieter sind verantwortlich für das, was sie vermieten, Buchende für die Nutzung. Cappy haftet unbeschränkt bei
        Vorsatz und grober Fahrlässigkeit sowie bei Verletzung von Leben, Körper oder Gesundheit; im Übrigen nur bei
        Verletzung wesentlicher Vertragspflichten, begrenzt auf den vertragstypischen, vorhersehbaren Schaden.
      </p>
      <H>Änderungen und Recht</H>
      <p>
        Über Änderungen dieser AGB informieren wir dich vorab per E-Mail. Es gilt deutsches Recht; der Schutz, den dir als
        Verbraucher das Recht deines Wohnsitzlandes gibt, bleibt unberührt.
      </p>
    </>
  )
}

function RankingDe() {
  return (
    <>
      <p>
        Bei einer Suche sortiert Cappy die Ergebnisse danach, wie gut jedes Inserat zu deiner Anfrage passt. Die wichtigsten
        Kriterien, ungefähr nach Gewicht:
      </p>
      <ul className="list-disc space-y-2 pl-5">
        <li><strong>Zeitliche Passung</strong>: ob das Inserat frei ist, wenn du es brauchst, und wie bald.</li>
        <li><strong>Entfernung</strong> vom Ort deiner Suche.</li>
        <li><strong>Preis</strong> für den beschriebenen Auftrag, Gebühr inklusive.</li>
        <li><strong>Bewertung</strong> aus abgeschlossenen Buchungen.</li>
        <li><strong>Zuverlässigkeit</strong>: pünktlich fertig, schnelle Antworten, keine Stornierungen.</li>
      </ul>
      <p>
        Du kannst nach Preis, Entfernung oder frühestem Termin umsortieren. Eine bessere Position kann niemand kaufen: Cappy
        hat kein bezahltes Ranking und keine Werbung in den Ergebnissen. Inserate von Anbietern, die noch keine
        Auszahlungen empfangen können, und nach unseren AGB entfernte Inserate erscheinen nicht.
      </p>
    </>
  )
}

function ReportingDe() {
  return (
    <>
      <p>
        Siehst du etwas Rechtswidriges, Gefährliches oder etwas, das gegen unsere AGB verstößt? Nutze „Melden“ beim
        Inserat, Profil, bei der Nachricht oder Bewertung. Du brauchst dafür kein Konto; ohne Konto hinterlässt du eine
        E-Mail-Adresse, damit wir antworten können. Wir bestätigen jede Meldung, prüfen sie und teilen dir unsere
        Entscheidung mit. Entfernen wir Inhalte oder schränken wir ein Konto ein, sagen wir der betroffenen Person, warum,
        und wie sie widersprechen kann.
      </p>
      <p>
        Behörden und alle anderen erreichen uns ebenfalls (Kontakt: {contactAddr()}). Ist jemand in unmittelbarer Gefahr, ruf zuerst die
        112 an.
      </p>
    </>
  )
}
