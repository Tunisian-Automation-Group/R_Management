import type { ReactNode } from 'react'
import { NavLink, useParams } from 'react-router-dom'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { Screen } from '../components/AppShell.tsx'
import { Banner } from '../components/ui.tsx'
import { NotFound } from './NotFound.tsx'

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
const operator = OPERATOR.company ?? 'the operator named in the Impressum'
const contact = OPERATOR.email ?? 'the address in the Impressum'
const FEE = `${PLATFORM_FEE_BPS / 100}%`

const PAGES: Record<string, { title: string; body: ReactNode }> = {
  impressum: { title: 'Impressum', body: <Impressum /> },
  privacy: { title: 'Privacy Policy', body: <Privacy /> },
  terms: { title: 'Terms of Use', body: <Terms /> },
  ranking: { title: 'How ranking works', body: <Ranking /> },
  report: { title: 'Reporting content', body: <Reporting /> },
}

export function Legal() {
  const { page = '' } = useParams()
  const p = PAGES[page]
  if (!p) return <NotFound />
  return (
    <Screen title={p.title} back="/profile">
      <nav aria-label="Legal pages" className="mb-6 flex gap-5 text-[14px] font-semibold">
        {Object.entries(PAGES).map(([key, v]) => (
          <NavLink
            key={key}
            to={`/legal/${key}`}
            className={({ isActive }) => (isActive ? 'text-[var(--ink)] underline underline-offset-4' : 'text-[var(--ink-4)]')}
          >
            {v.title}
          </NavLink>
        ))}
      </nav>
      {!complete && (
        <div className="mb-6">
          <Banner
            tone="warn"
            title="Operator details to be completed before launch"
            body="The company name, address and contact for this service are not configured in this build."
          />
        </div>
      )}
      <article className="legal space-y-4 pb-8 text-[15px] leading-[24px] text-[var(--ink-2)]">{p.body}</article>
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
        <p>The operator's name, address and email are added here before launch.</p>
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
        The controller is {operator}. Contact: {contact}.
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
        {contact} for anything else.
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
        runs the platform and handles the payment. Cappy is operated by {operator}.
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
        by telling {operator} at {contact}, for example with this sentence: “I hereby withdraw from
        the contract for the following booking: [booking reference], booked on [date], [name,
        address].” Bookings from private owners have no statutory right of withdrawal; you can
        still cancel before the start for a full refund under these terms.
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
        Authorities and anyone else can reach us at {contact}. If someone is in immediate danger, call 112
        first.
      </p>
    </>
  )
}
