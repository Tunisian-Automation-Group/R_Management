import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { NotFound } from './NotFound.tsx'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Booking, BookingStatus, Listing, Outcome, Owner } from '../../domain/types.ts'
import { rating } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { trackRecord } from '../../domain/match.ts'
import { formatMoney } from '../../domain/money.ts'
import { moved, PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import {
  useAttemptKey,
  actOnBooking,
  blockPerson,
  declineBooking,
  type EvidenceStage,
  disputeBooking,
  getBookingPayment,
  rateBooking,
  rateRenter,
  reportNoShow,
  unblockPerson,
  useBlocks,
  REASON_TEXT,
  useCancellationQuote,
  useBooking,
  useListing,
  useOwner,
  usePaymentsConfig,
  useMarket,
  type BookingAction,
} from '../../data/repo.ts'
import { TraderNote } from '../components/BusinessFields.tsx'
import { Conversation } from '../components/Conversation.tsx'
import { EvidencePanel } from '../components/Evidence.tsx'
import { ReportButton } from '../components/Report.tsx'
import { DisputeDecided, DisputeOffers, Extend, LateReturn } from '../components/BookingExtras.tsx'
import { DECLINE_REASONS } from './Earn.tsx'
import { messageOf, useToast } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Ticket } from '../components/Ticket.tsx'
import { Icon } from '../components/Icon.tsx'
import { Avatar, Banner, Button, Card, Chip, DetailSkeleton, Field, Row, Sheet, Stars, Textarea } from '../components/ui.tsx'
import { REVIEW_TAGS } from '../../domain/reviews.ts'
import { formatDistance, percent, range, relative, renterRecord, responseTime, sentence } from '../format.ts'
import { useOnline } from '../components/Offline.tsx'
import { supportHref } from './Help.tsx'
import { plural, t } from '../../i18n.ts'

/** Stripe's card form, fetched only when a payment starts (S-15, V3-1). */
const PayStep = lazy(() => import('../components/PayStep.tsx').then((m) => ({ default: m.PayStep })))

const STEPS: { id: BookingStatus; label: string; note: string; ownerNote: string; pastNote: string }[] = [
  { id: 'requested', label: 'Requested', note: 'Waiting for the owner to accept', ownerNote: 'Waiting for your answer', pastNote: 'Request sent' },
  { id: 'accepted', label: 'Confirmed', note: 'The window is held for you', ownerNote: 'The window is held for them', pastNote: 'Accepted' },
  { id: 'active', label: 'In progress', note: 'You have it now', ownerNote: 'They have it now', pastNote: 'Handed over' },
  { id: 'completed', label: 'Finished', note: 'Handed back', ownerNote: 'Handed back; your payout is on its way', pastNote: 'Handed back' },
]

const DEAD: BookingStatus[] = ['declined', 'cancelled', 'expired', 'payment_failed']
// Used only if the server does not say (canStartFrom): the deployed rule.
const START_EARLY_MS = 30 * 60_000

/** Reasons the server declines with on its own (booking/handlers.py, routes.py):
 *  a headline that does not blame the owner (translated in i18n.de/fr). */
const SYSTEM_DECLINE: Record<string, string> = {
  'The listing was taken down by Cappy': 'Cappy removed this listing',
  'The listing was removed by its owner': 'The listing was removed',
  'The booking it extends was cancelled': 'The booking this extended was cancelled',
  'The account was suspended': 'Cappy stopped this request',
}

/** The reason in the reader's words: by code when the server gives one (V8-3). */
const reasonText = (b: { declineReason?: string; declineReasonCode?: string }) =>
  b.declineReasonCode && REASON_TEXT[b.declineReasonCode] ? t(REASON_TEXT[b.declineReasonCode]) : b.declineReason ? t(b.declineReason) : undefined

export function BookingDetail() {
  const { id } = useParams()
  const session = useSession()
  const authReady = useAuthReady()
  const booking = useBooking(session ? id : undefined)
  // The live listing, for the handover notes. It may have changed or gone since;
  // the booking's own snapshot covers the rest.
  const listing = useListing(booking.data?.match.listingId)
  const owner = useOwner(booking.data?.match.ownerId)
  // Present only when the viewer is the owner: the person asking them.
  const requester = useOwner(booking.data?.requesterId)

  if (authReady && !session) {
    return (
      <Screen title={t('Booking')}>
        <SignedOut what={t('see this booking')} next={`/bookings/${id}`} />
      </Screen>
    )
  }
  // The names are part of the page: wait for them rather than show "a buyer" (V9-12).
  const namesPending = (booking.data?.requesterId && requester.isPending) || (booking.data && owner.isPending)
  if (!authReady || booking.isPending || namesPending) return <Screen back="/bookings"><DetailSkeleton /></Screen>
  if (!booking.data) return <NotFound what="booking" />

  // Remount when the booking changes so the rating form never carries over.
  return (
    <Detail
      key={booking.data.id}
      booking={booking.data}
      listing={listing.data?.listing}
      owner={owner.data}
      requester={requester.data}
    />
  )
}

function Detail({
  booking,
  listing,
  owner,
  requester,
}: {
  booking: Booking
  listing?: Listing
  owner?: Owner
  requester?: Owner
}) {
  const blocks = useBlocks()
  const qc = useQueryClient()
  const toast = useToast()

  const [cancelling, setCancelling] = useState(false)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState(DECLINE_REASONS[0])
  const [disputing, setDisputing] = useState(false)
  const [problem, setProblem] = useState('')
  const [rateOpen, setRateOpen] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const [stars, setStars] = useState(0)
  const [onTime, setOnTime] = useState<boolean | null>(null)
  const [tags, setTags] = useState<string[]>([])
  const [note, setNote] = useState('')
  const online = useOnline()
  const [busy, setBusy] = useState(false)
  const [evidencePrompt, setEvidencePrompt] = useState<EvidenceStage | null>(null)
  const backToFinish = useRef(false)
  const [blocking, setBlocking] = useState(false)
  const [ratingRenter, setRatingRenter] = useState(false)
  const [renterStars, setRenterStars] = useState(0)
  const [noShowOpen, setNoShowOpen] = useState(false)
  // One key per rating (U-6, FL-1): a double tap or a retry after a 5xx posts one rating.
  const attempt = useAttemptKey()
  /** A keyed write: the key follows the body and is kept only while an answer is unknown. */
  const keyed = async <T,>(body: unknown, call: (key: string) => Promise<T>): Promise<T> => {
    try {
      const out = await call(attempt.keyFor(body))
      attempt.settle()
      return out
    } catch (err) {
      attempt.settle(err)
      throw err
    }
  }

  // Arrived straight from sending it (VD-15): the ticket, once. Dropping the
  // state on close means a reload or Back never plays it again.
  const loc = useLocation()
  const nav = useNavigate()
  const [ticket, setTicket] = useState(() => Boolean((loc.state as { fresh?: boolean } | null)?.fresh))
  const closeTicket = () => {
    setTicket(false)
    nav(loc.pathname, { replace: true, state: null })
  }

  const { quote } = booking.match
  const cur = booking.currency ?? quote.currency ?? listing?.currency
  const title = booking.listing?.title ?? listing?.title ?? t('Booked listing')
  const ownerName = owner?.name ?? booking.listing?.ownerName ?? t('The owner')
  const district = booking.listing?.district ?? listing?.district ?? ''
  const first = ownerName.split(' ')[0]
  const stepIndex = STEPS.findIndex((s) => s.id === booking.status)
  const dead = DEAD.includes(booking.status)
  const money = moved(booking)
  // requesterId is only ever sent to the owner.
  const asOwner = Boolean(booking.requesterId)
  const buyer = requester?.name.split(' ')[0] ?? t('The buyer')
  const other = asOwner ? requester : owner
  const startsAt = Date.parse(booking.match.start)
  const startFrom = booking.canStartFrom ? Date.parse(booking.canStartFrom) : startsAt - START_EARLY_MS
  const canStart = Date.now() >= startFrom
  const begun = Date.now() >= startsAt
  // S-11: the renter may report the owner from the start, the owner the renter
  // from 30 minutes in (they may just be late), both until 2 hours in.
  const sinceStart = Date.now() - startsAt
  const canReportNoShow =
    booking.status === 'accepted' && sinceStart >= (asOwner ? 30 * 60_000 : 0) && sinceStart <= 2 * 3_600_000

  // What cancelling now would refund, fetched only while the sheet is open.
  // `charged` says whether any money was taken; when not, only the hold goes.
  const refund = useCancellationQuote(booking.id, cancelling)
  const charged = refund.data ? refund.data.charged ?? booking.status === 'accepted' : booking.status === 'accepted'
  // Where the hand-over is: its market's emergency number (112, 911…).
  const market = useMarket(listing?.country)
  const evidenceRef = useRef<HTMLDivElement>(null)
  const payments = usePaymentsConfig()
  // Between Stripe saying yes and its webhook reaching Cappy the booking still
  // reads awaiting_payment: the card form must not come back meanwhile (FL-16).
  // The booking is re-read every 2 s for a minute instead.
  const [confirming, setConfirming] = useState(false)
  useEffect(() => {
    if (!confirming || booking.status !== 'awaiting_payment') return
    const tick = setInterval(() => void qc.invalidateQueries({ queryKey: ['booking', booking.id] }), 2000)
    const stop = setTimeout(() => setConfirming(false), 60_000)
    return () => {
      clearInterval(tick)
      clearTimeout(stop)
    }
  }, [confirming, booking.status, booking.id, qc])
  const payNow =
    !asOwner && booking.status === 'awaiting_payment' && payments.data?.provider === 'stripe' && !confirming
  const payment = useQuery({
    queryKey: ['bookingPayment', booking.id],
    queryFn: () => getBookingPayment(booking.id),
    enabled: payNow,
    retry: false,
  })

  const done = async (write: () => Promise<unknown>, message?: string) => {
    setBusy(true)
    try {
      const said = await write()
      const text = typeof said === 'string' ? said : message
      if (text) toast(text)
    } catch (err) {
      toast(messageOf(err), 'error')
    } finally {
      setBusy(false)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['booking', booking.id] }),
        qc.invalidateQueries({ queryKey: ['bookings'] }),
        qc.invalidateQueries({ queryKey: ['blocks'] }),
      ])
    }
  }
  const act = (action: BookingAction, message?: string) => done(() => actOnBooking(booking.id, action), message)
  // Blind reviews (V5-6): what is said depends on whether the other side has
  // rated already, which the answer shows (their rating is visible once published).
  const rate = (outcome: Outcome) =>
    done(async () => {
      const b = await keyed(outcome, (key) => rateBooking(booking.id, outcome, key))
      // The owner's record and the listing's reviews change a moment later.
      void qc.invalidateQueries({ queryKey: ['listing', booking.match.listingId] })
      void qc.invalidateQueries({ queryKey: ['reviews', booking.match.listingId] })
      return b.renterRating != null
        ? t('Review posted on {title}', { title })
        : t('Thanks. {name} will see it once they have rated too.', { name: first })
    })
  const rateTheRenter = (quality: number) =>
    done(async () => {
      const b = await keyed({ quality }, (key) => rateRenter(booking.id, quality, key))
      return b.outcome
        ? t('Thanks. Both ratings are published now.')
        : t('Thanks. {name} will see it once they have rated too.', { name: buyer })
    })

  // For the buyer, cancelling before the start is also their right of
  // withdrawal (EU consumer law), so the button says so.
  const cancelButton = (
    <Button block variant="danger" disabled={!online || busy} onClick={() => setCancelling(true)}>
      {asOwner ? t('Cancel booking') : t('Withdraw from this booking')}
    </Button>
  )
  const disputeButton = (
    <Button block variant="quiet" disabled={!online || busy} onClick={() => setDisputing(true)}>
      {t('Report a problem')}
    </Button>
  )
  const startButton = (
    <div>
      {/* The primary follows the clock (UX-25): before the hand-over window it
          is a quiet, disabled line that says when it opens, not the loudest
          button on the page. */}
      <Button
        block
        size="lg"
        variant={canStart ? 'primary' : 'secondary'}
        disabled={!online || busy || !canStart}
        onClick={() =>
          void done(async () => {
            await actOnBooking(booking.id, 'start')
            setEvidencePrompt('check_in')
          }, asOwner ? t('Marked as handed over') : t('Enjoy it'))
        }
      >
        {canStart
          ? asOwner
            ? t('I have handed it over')
            : t('I have collected it')
          : t('Hand-over opens {when}', { when: relative(new Date(startFrom).toISOString()) })}
      </Button>
      {!canStart && (
        <p className="t-sm mt-2 text-center text-[var(--ink-3)]">
          {t('Either of you can mark the hand-over from 30 minutes before the booked time.')}
        </p>
      )}
    </div>
  )
  const noShowButton = canReportNoShow && (
    <Button block variant="quiet" disabled={!online || busy} onClick={() => setNoShowOpen(true)}>
      {asOwner ? t('{name} did not show up', { name: buyer }) : t('{name} did not show up', { name: first })}
    </Button>
  )
  const home = asOwner ? (
    <Button block size="lg" variant="secondary" to={'/earn'}>
      {t('Back to Earn')}
    </Button>
  ) : (
    <Button block size="lg" variant="secondary" to={'/'}>
      {t('Find something to rent')}
    </Button>
  )

  let footer: ReactNode
  switch (asOwner ? `owner:${booking.status}` : booking.status) {
    case 'owner:requested':
      footer = (
        <div className="space-y-2">
          <Button block size="lg" disabled={!online || busy} onClick={() => void act('accept', t('Accepted. {name} has been told', { name: buyer }))}>
            {t('Accept')}
          </Button>
          <Button block variant="quiet" disabled={!online || busy} onClick={() => setDeclining(true)}>
            {t('Decline')}
          </Button>
        </div>
      )
      break
    case 'owner:accepted':
      footer = (
        <div className="space-y-2">
          {startButton}
          {!begun && cancelButton}
          {noShowButton}
        </div>
      )
      break
    case 'awaiting_payment':
      footer = cancelButton
      break
    case 'requested':
      // While it waits, talking is the useful next step, not leaving (UX-51):
      // Withdraw stays one tap away, quiet, behind its own confirm sheet.
      footer = (
        <div className="space-y-2">
          <Button
            block
            size="lg"
            onClick={() => {
              const h = document.getElementById('messages')
              h?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' })
              h?.parentElement?.querySelector<HTMLElement>('textarea')?.focus({ preventScroll: true })
            }}
          >
            {t('Message {name}', { name: first })}
          </Button>
          <Button block variant="quiet" disabled={!online || busy} onClick={() => setCancelling(true)}>
            {t('Withdraw request')}
          </Button>
        </div>
      )
      break
    case 'accepted':
      footer = (
        <div className="space-y-2">
          {startButton}
          {begun ? disputeButton : cancelButton}
          {noShowButton}
        </div>
      )
      break
    case 'active':
      footer = (
        <div className="space-y-2">
          <Button
            block
            size="lg"
            disabled={!online || busy}
            onClick={() => setFinishing(true)}
          >
            {t('Mark as handed back')}
          </Button>
          {disputeButton}
        </div>
      )
      break
    case 'disputed':
    case 'owner:disputed':
      // Still held while it is sorted out: no "browse" as the main action (V5-32).
      footer = (
        <Button block size="lg" variant="secondary" onClick={() => (location.href = supportHref(booking.id))}>
          {t('Get help with this booking')}
        </Button>
      )
      break
    case 'completed':
      // A finished booking that went well is the likeliest next booking there is.
      footer = booking.outcome ? (
        <div className="space-y-2">
          {listing && listing.active && (
            <Button block size="lg" to={`/listing/${listing.id}`}>
              {t('Book again')}
            </Button>
          )}
          <Button block variant="quiet" to={'/'}>
            {t('Find something else')}
          </Button>
        </div>
      ) : (
        <Button block size="lg" onClick={() => setRateOpen(true)}>
          {t('Rate {name}', { name: first })}
        </Button>
      )
      break
    case 'owner:completed':
      footer = booking.renterRating ? home : (
        <Button block size="lg" onClick={() => setRatingRenter(true)}>
          {t('Rate {name}', { name: buyer })}
        </Button>
      )
      break
    default:
      footer = home
  }

  return (
    <Screen
      back={asOwner ? '/bookings?as=hosting' : '/bookings'}
      docTitle={title}
      hero={
        <Photo
          alt={title}
          src={booking.listing?.photo ?? listing?.photos?.[0]}
          categoryId={booking.requirement.category}
          aspect={2.2}
          priority
          className={`w-full md:rounded-[var(--radius-sheet)] ${dead ? 'opacity-55 grayscale' : ''}`}
          style={{ viewTransitionName: 'hero' }}
        />
      }
      footer={footer}
    >
      <header className="-mt-1 mb-6">
        <h1 className="t-title-user text-balance">{title}</h1>
        <p className="t-lede mt-2 text-[var(--ink-3)]">
          {asOwner ? t('Booked by {name}', { name: requester?.name ?? t('a buyer') }) : ownerName}
          {district && ` · ${district}`}
        </p>
      </header>

      {booking.status === 'declined' ? (
        <Banner
          tone="danger"
          title={
            // Declined by the system, not the owner: say what happened (V7-14).
            (() => { const k = (booking.declineReasonCode && REASON_TEXT[booking.declineReasonCode]) || booking.declineReason; return k && SYSTEM_DECLINE[k] ? t(SYSTEM_DECLINE[k]) : null })() ||
            (asOwner ? t('You declined this request') : t('{name} could not take this one', { name: first }))
          }
          body={
            <>
              <span className="block">{reasonText(booking) ? t('Reason: {reason}.', { reason: reasonText(booking)! }) : t('No reason given.')}</span>
              <span className="block">{t('The hold on the card is released; nothing was charged.')}</span>
            </>
          }
          action={
            asOwner ? undefined : (
              <Button size="sm" variant="secondary" to={'/'}>
                {t('Find another')}
              </Button>
            )
          }
        />
      ) : booking.status === 'disputed' ? (
        <>
        <Banner
          tone="warn"
          title={t('Under review')}
          body={
            asOwner
              ? t('{name} reported a problem with this booking. Your payout is on hold while Cappy looks into it; we will be in touch.', { name: buyer })
              : t('You reported a problem. The payment is on hold while Cappy looks into it; we will be in touch.')
          }
        />
        <DisputeOffers booking={booking} asOwner={asOwner} otherName={asOwner ? buyer : first} />
        </>
      ) : booking.status === 'cancelled' && booking.noShow ? (
        <Banner
          tone="warn"
          title={
            booking.noShow === 'owner'
              ? asOwner
                ? t('Reported: you did not show up')
                : t('Reported: {name} did not show up', { name: first })
              : asOwner
                ? t('Reported: {name} did not show up', { name: buyer })
                : t('Reported: you did not show up')
          }
          body={
            booking.noShow === 'owner'
              ? asOwner
                ? t('{name} gets everything back{amount}, and a no-show counts against you. If this is wrong, get help with this booking.', {
                    name: buyer,
                    amount: booking.refundAmount ? ` (${formatMoney(booking.refundAmount, cur)})` : '',
                  })
                : t('You get everything back{amount}. A no-show counts against the owner.', {
                    amount: booking.refundAmount ? ` (${formatMoney(booking.refundAmount, cur)})` : '',
                  })
              : asOwner
                ? t('You are paid for the missed booking. {name} can contest it with Cappy.', { name: buyer })
                : t('Nothing is refunded for a missed booking; the owner is paid. If this is wrong, get help with this booking.')
          }
        />
      ) : booking.status === 'cancelled' ? (
        <Banner
          tone="warn"
          title={t('This booking was cancelled')}
          body={
            <>
            {/* A cancellation the system made says why, as the mails do (V8-5). */}
            {reasonText(booking) && <span className="block">{t('Reason: {reason}.', { reason: reasonText(booking)! })}</span>}
            {booking.refundAmount
              ? t('{amount} is refunded to the card.', { amount: formatMoney(booking.refundAmount, cur) })
              : // No refund means nothing was charged: it ended before the owner
                // accepted, which is when the card is charged (FL-8).
                asOwner
                ? t('Nothing was charged, and the window is free again.')
                : t('The hold on your card is released; nothing was charged.')}
            </>
          }
        />
      ) : booking.status === 'expired' ? (
        <Banner tone="warn" title={t('This request lapsed')} body={t('It was not paid for or answered in time. Nothing was charged.')} />
      ) : booking.status === 'payment_failed' ? (
        <Banner
          tone="danger"
          title={t('The payment could not be taken')}
          body={t('Nothing was charged, and the window is free again.')}
          action={
            asOwner ? undefined : (
              <Button size="sm" variant="secondary" to={`/listing/${booking.match.listingId}`}>
                {t('Try again')}
              </Button>
            )
          }
        />
      ) : booking.status === 'awaiting_payment' ? (
        <Banner
          tone="warn"
          title={confirming ? t('Confirming your payment…') : payNow ? t('Finish paying to send your request') : t('Authorising your card')}
          body={`${t('{name} is asked as soon as the card is authorised.', { name: first })}${booking.expiresAt ? ` ${t('It lapses {when} if not.', { when: relative(booking.expiresAt) })}` : ''}`}
        />
      ) : booking.status === 'requested' && asOwner ? (
        <Banner
          tone="warn"
          title={t('{name} wants this window', { name: buyer })}
          body={`${range(booking.match.start, booking.match.end)}. ${t('Their card is held and charged when you accept.')}${booking.expiresAt ? ` ${t('Answer {when}, or it lapses.', { when: relative(booking.expiresAt) })}` : ''}`}
        />
      ) : booking.status === 'requested' ? (
        <Banner
          tone="neutral"
          title={t('Waiting for {name}', { name: first })}
          // The status header says how long it can take (UX-51).
          body={`${owner && responseTime(owner.responseMins) ? sentence(responseTime(owner.responseMins)!) : ''}${booking.expiresAt ? sentence(t('{name} has to answer {when}', { name: first, when: relative(booking.expiresAt) })) : ''}${t('Your card is held, and charged only if they accept.')}`}
        />
      ) : booking.status === 'accepted' ? (
        <Banner
          tone="success"
          title={t("Confirmed")}
          body={
            asOwner
              ? Date.now() >= Date.parse(booking.match.start)
                ? t('{name} was due {when}.', { name: buyer, when: range(booking.match.start, booking.match.end) })
                : t('{name} is coming {when}.', { name: buyer, when: range(booking.match.start, booking.match.end) })
              : t('{name} is expecting you {when}.', { name: first, when: range(booking.match.start, booking.match.end) })
          }
        />
      ) : null}

      {booking.extendsId && (
        <p className="t-sm mt-3 text-[var(--ink-3)]">
          <Link className="underline" to={`/bookings/${booking.extendsId}`}>
            {t('This extends your booking before it.')}
          </Link>
        </p>
      )}

      {/* A report that was decided says how (V5-7): upheld or not, and the money. */}
      {(booking.status === 'completed' || booking.status === 'cancelled') && <DisputeDecided booking={booking} asOwner={asOwner} />}

      {payNow && payment.data && payments.data?.publishableKey && (
        <div className="mt-4">
          <Suspense fallback={null}>
            <PayStep
              publishableKey={payments.data.publishableKey}
              clientSecret={payment.data.clientSecret}
              bookingId={booking.id}
              onPaid={() => {
                setConfirming(true)
                void qc.invalidateQueries({ queryKey: ['booking', booking.id] })
              }}
            />
          </Suspense>
        </div>
      )}

      {!dead && booking.status !== 'disputed' && (
        <ol className="mt-6">
          {STEPS.map((step, i) => {
            const reached = i <= stepIndex
            const current = i === stepIndex
            return (
              <li key={step.id} className="flex gap-3.5">
                <div className="flex flex-col items-center">
                  <span
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-[var(--radius-control)] text-caption font-bold transition-colors duration-[var(--dur-medium)] ${
                      reached
                        ? 'bg-[var(--success)] text-[var(--on-status)]'
                        : 'border border-[var(--line-strong)] text-[var(--ink-4)]'
                    }`}
                  >
                    {reached ? <Icon name="check" size={14} strokeWidth={3} /> : i + 1}
                  </span>
                  {i < STEPS.length - 1 && (
                    <span
                      className={`w-[2px] flex-1 ${i < stepIndex ? 'bg-[var(--success)]' : 'bg-[var(--line)]'}`}
                    />
                  )}
                </div>
                <div className={`pb-6 ${reached ? '' : 'opacity-40'}`}>
                  <p
                    className={`text-body leading-7 ${current ? 'font-bold' : 'font-semibold'}`}
                  >
                    {/* Nobody requested an instant booking: it was booked (V4-23). */}
                    {step.id === 'requested' && booking.listing?.instantBook ? t('Booked') : t(step.label)}
                  </p>
                  <p className="t-sm text-[var(--ink-3)]">
                    {step.id === 'requested' && booking.listing?.instantBook
                      ? t('Instant book: confirmed as soon as the card was held')
                      : i < stepIndex
                        ? t(step.pastNote)
                        : t(asOwner ? step.ownerNote : step.note)}
                  </p>
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {/* Handover detail only appears once there is something to hand over:
          the address is shared with the buyer when the owner accepts. */}
      {(booking.status === 'accepted' || booking.status === 'active' || booking.status === 'disputed') && (booking.handover || listing) && (
        <Card className="p-5">
          <h2 className="t-label mb-2.5">{t('Getting in')}</h2>
          {booking.handover?.address && (
            <p className="text-body font-semibold text-[var(--ink)]">
              {booking.handover.address}
              {booking.handover.postalCode && `, ${booking.handover.postalCode}`}
            </p>
          )}
          {/* The exact point, now the booking is accepted (M-6); others only ever see ~500 m. */}
          {booking.handover?.location && (
            <a
              className="t-sm mt-1 inline-block font-semibold underline"
              href={`https://www.openstreetmap.org/?mlat=${booking.handover.location.lat}&mlon=${booking.handover.location.lng}#map=17/${booking.handover.location.lat}/${booking.handover.location.lng}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t('Open in a map')}
            </a>
          )}
          <p className="t-body mt-1 text-[var(--ink-2)]">{booking.handover?.instructions}</p>
          <p className="t-sm tnum mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            <Icon name="pin" size={14} />
            {district}
            {!asOwner && ` · ${t('{distance} away', { distance: formatDistance(booking.match.distanceKm) })}`}
          </p>
        </Card>
      )}

      {other && (
        <Card className="mt-3 p-5">
          <div className="flex items-center gap-3.5">
            <Avatar initials={other.initials} size={44} business={other.kind === 'business'} />
            <div className="min-w-0 flex-1">
              <p className="[overflow-wrap:anywhere] text-body font-semibold">{other.name}</p>
              <p className="t-sm text-[var(--ink-3)]">
                {asOwner ? renterRecord(other.renterRatingSum, other.renterJobs) : trackRecord(other)}
              </p>
            </div>
            {!asOwner && <Stars value={rating(other)} count={other.jobsDone} />}
          </div>
          <div className="mt-3 flex flex-wrap gap-1 border-t border-[var(--line)] pt-3">
            <ReportButton targetType="owner" targetId={other.id} />
            {/* One button, the one that applies (V8-16). */}
            {blocks.data?.includes(other.id) ? (
              <Button variant="quiet" onClick={() => void done(() => unblockPerson(other.id), t('Unblocked'))}>
                {t('Unblock')}
              </Button>
            ) : (
              <Button variant="quiet" icon="close" onClick={() => setBlocking(true)}>
                {t('Block')}
              </Button>
            )}
          </div>
        </Card>
      )}

      {booking.status !== 'awaiting_payment' && (
        <Conversation
          bookingId={booking.id}
          status={booking.status}
          otherName={asOwner ? buyer : first}
          otherId={other?.id}
          accepted={['accepted', 'active', 'completed', 'disputed'].includes(booking.status)}
          // Also a completed booking once its 14-day review window has passed (booking/messages.py).
          closed={dead || (booking.status === 'completed' && Date.now() > Date.parse(booking.match.end) + 14 * 86_400_000)}
        />
      )}

      {booking.status === 'accepted' && (
        // U-34: before the first hand-over, the four things that prevent most problems.
        <Card className="mt-3 p-5">
          <h2 className="t-label mb-2">{t('Before the hand-over')}</h2>
          <ul className="t-sm list-disc space-y-1.5 pl-5 text-[var(--ink-2)]">
            <li>{t('Meet at the address in the booking, and check it is the thing in the listing.')}</li>
            <li>{t('Take check-in photos together: every side, any marks, the meter if it has one.')}</li>
            <li>{t('Keep messages and payments on Cappy. Nobody from Cappy asks for money or codes elsewhere.')}</li>
            <li>{t('If you feel unsafe, leave and call {number} first, then tell us.', { number: market.emergencyNumber })}</li>
          </ul>
          <Link to="/help/safety" className="t-sm mt-3 inline-block font-semibold underline">
            {t('How we keep you safe')}
          </Link>
        </Card>
      )}

      {/* A sheet that opened on its own has no button to go back to: focus lands
          on the photos it was about (V4-22). */}
      <div ref={evidenceRef} tabIndex={-1} className="outline-none">
        <EvidencePanel
          asOwner={asOwner}
          bookingId={booking.id}
          status={booking.status}
          otherName={asOwner ? buyer : first}
          prompt={evidencePrompt}
          onPromptClosed={(saved) => {
            setEvidencePrompt(null)
            // Photos first, then the question they came from (V7-22).
            if (saved && backToFinish.current) setFinishing(true)
            backToFinish.current = false
            // After the sheet has handed focus back to its opener, which may be gone (V5-14).
            setTimeout(() => evidenceRef.current?.focus({ preventScroll: false }), 60)
          }}
        />
      </div>

      {!asOwner && <Extend booking={booking} />}
      <LateReturn booking={booking} renterName={buyer} asOwner={asOwner} />

      <Card className="mt-3 flex flex-wrap items-center justify-between gap-3 p-5">
        <p className="t-sm text-[var(--ink-3)]">{t('Something not right? Tell us, and we see this booking with it.')}</p>
        <div className="flex flex-wrap gap-x-5 text-body font-semibold">
          <Link to="/help/problems" className="inline-flex min-h-[44px] min-w-[44px] items-center underline">
            {t('Help')}
          </Link>
          <a href={supportHref(booking.id)} className="inline-flex min-h-[44px] items-center underline">
            {t('Get help with this booking')}
          </a>
        </div>
      </Card>

      <Card className="mt-3 p-5">
        <h2 className="t-label mb-2">{t('What you agreed')}</h2>
        {!asOwner && booking.listing?.ownerBusiness && (
          <div className="mb-2">
            <TraderNote business={booking.listing.ownerBusiness} />
          </div>
        )}
        <Row label={t('When')} value={range(booking.match.start, booking.match.end)} />
        <Row
          label={booking.requirement.mode === 'window' ? t('Duration') : t('Batch')}
          value={
            booking.requirement.mode === 'batch'
              ? `${t('{n} parts', { n: booking.requirement.quantity })} · ${durationLabel(quote.hours)}`
              : durationLabel(quote.hours)
          }
        />
        <div className="my-2 border-t border-[var(--line)]" />
        {money.charged === 0 && ['awaiting_payment', 'requested'].includes(booking.status) ? (
          // Held, not charged yet: the price as agreed, and when it becomes a charge (V8-1).
          <>
            <Row label={t('Total')} value={formatMoney(quote.total, cur)} strong />
            {asOwner ? (
              <>
                <Row label={`${t('Service fee')} · ${percent(PLATFORM_FEE_BPS / 10_000)}`} value={`−${formatMoney(quote.platformFee, cur)}`} tone="muted" />
                <Row label={t('You receive')} value={<span className="text-[var(--money)]">{formatMoney(quote.ownerNet, cur)}</span>} strong />
                <p className="t-sm text-[var(--ink-4)]">{t('Their card is held and charged when you accept.')}</p>
              </>
            ) : (
              <p className="t-sm text-[var(--ink-4)]">{t('Held on your card, charged when {name} accepts.', { name: first })}</p>
            )}
          </>
        ) : money.charged === 0 ? (
          <Row label={t('Charged')} value={t('Nothing: hold released')} strong />
        ) : money.refunded >= money.charged ? (
          <Row label={t('Refunded')} value={formatMoney(money.refunded, cur)} strong />
        ) : (
          <>
            <Row label={t('Total')} value={formatMoney(money.charged, cur)} strong />
            {money.refunded > 0 && <Row label={t('Refunded')} value={`−${formatMoney(money.refunded, cur)}`} />}
            {/* One name for the fee; the renter never sees the owner's net (UX-23). */}
            {asOwner ? (
              <>
                <Row label={`${t('Service fee')} · ${percent(PLATFORM_FEE_BPS / 10_000)}`} value={`−${formatMoney(money.fee, cur)}`} tone="muted" />
                <Row label={t('You receive')} value={<span className="text-[var(--money)]">{formatMoney(money.ownerNet, cur)}</span>} strong />
              </>
            ) : (
              <>
                {money.refunded > 0 && <Row label={t('You paid')} value={formatMoney(money.charged - money.refunded, cur)} strong />}
                <p className="t-sm tnum text-[var(--ink-4)]">{t('Includes the service fee of {fee}', { fee: formatMoney(money.fee, cur) })}</p>
              </>
            )}
          </>
        )}
      </Card>

      {/* The owner sees the rating they gave, as the renter sees theirs (V4-23). */}
      {asOwner && booking.renterRating ? (
        <Card className="mt-3 p-5">
          <h2 className="t-label mb-2.5">{t('Your rating of {name}', { name: buyer })}</h2>
          <span className="flex" aria-label={t('{n} out of 5', { n: booking.renterRating })}>
            {[1, 2, 3, 4, 5].map((n) => (
              <Icon key={n} name="star" size={17} strokeWidth={0} className={n <= booking.renterRating! ? 'fill-[var(--ink)]' : 'fill-[var(--line)]'} />
            ))}
          </span>
        </Card>
      ) : null}

      {booking.outcome && (
        <Card className="anim-rise mt-3 p-5">
          <h2 className="t-label mb-2.5">{asOwner ? t('Rating from {name}', { name: buyer }) : t('Your rating')}</h2>
          <div className="flex items-center gap-2">
            <span className="flex" aria-label={t('{n} out of 5', { n: booking.outcome.quality })}>
              {[1, 2, 3, 4, 5].map((n) => (
                <Icon
                  key={n}
                  name="star"
                  size={17}
                  strokeWidth={0}
                  className={
                    n <= booking.outcome!.quality ? 'fill-[var(--ink)]' : 'fill-[var(--line)]'
                  }
                />
              ))}
            </span>
            <span className="t-sm text-[var(--ink-3)]">
              {booking.outcome.onTime ? t('On time') : t('Late')}
            </span>
          </div>
          <p className="t-sm mt-4 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            {t('Ratings decide where {name} ranks for the next person searching.', { name: first })}
          </p>
        </Card>
      )}

      <Sheet
        open={finishing}
        onClose={() => setFinishing(false)}
        title={t('Handed back and all fine?')}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              disabled={!online || busy}
              onClick={() => {
                setFinishing(false)
                void act('complete')
                setRateOpen(true)
              }}
            >
              {t('Yes, it is done')}
            </Button>
            <Button
              block
              variant="secondary"
              icon="camera"
              onClick={() => {
                setFinishing(false)
                backToFinish.current = true
                setEvidencePrompt('check_out')
              }}
            >
              {t('Add check-out photos first')}
            </Button>
            <Button block variant="quiet" onClick={() => setFinishing(false)}>
              {t('Not yet')}
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {t('This completes the booking and pays {name}. If something went wrong, report a problem instead: the payment is held until it is sorted out.', { name: first })}
        </p>
      </Sheet>

      <Sheet
        open={cancelling}
        onClose={() => setCancelling(false)}
        title={asOwner ? t('Cancel this booking?') : t('Withdraw from this booking?')}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              disabled={!online || busy}
              onClick={() => {
                void act('cancel', t('Cancelled'))
                setCancelling(false)
              }}
            >
              {asOwner ? t('Yes, cancel it') : t('Yes, withdraw')}
            </Button>
            <Button block variant="quiet" onClick={() => setCancelling(false)}>
              {t('Keep it')}
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {asOwner
            ? charged
              ? t('{name} will be told, and gets back everything they paid.', { name: buyer })
              : t('{name} will be told. The hold on their card is released; nothing was charged.', { name: buyer })
            : !charged
              ? t('This is your withdrawal from the booking. {name} will be told the window is free again. The hold on your card is released; nothing is charged.', { name: first })
              : refund.data && refund.data.refundAmount < quote.total
                ? t('This is your withdrawal from the booking. {name} will be told the window is free again. What you get back is below.', { name: first })
                : t('This is your withdrawal from the booking. {name} will be told the window is free again, and you get back everything you paid, in full.', { name: first })}
        </p>
        {charged && (
          <Card className="mb-3 bg-[var(--sunken)] p-4 shadow-none">
            <Row
              label={asOwner ? t('{name} gets back', { name: buyer }) : t('You get back')}
              value={refund.data ? formatMoney(refund.data.refundAmount, cur) : '…'}
              strong
            />
            {refund.data && refund.data.refundAmount < quote.total && (
              <p className="t-sm mt-1 text-[var(--ink-3)]">
                {t('Of {total}, under the listing\'s cancellation policy.', { total: formatMoney(quote.total, cur) })}
              </p>
            )}
          </Card>
        )}
      </Sheet>

      <Sheet
        open={blocking}
        onClose={() => setBlocking(false)}
        title={t('Block {name}?', { name: asOwner ? buyer : first })}
        footer={
          <Button
            block
            size="lg"
            variant="danger"
            disabled={!online || busy || !other}
            onClick={() => {
              if (other) void done(() => blockPerson(other.id), t('{name} is blocked', { name: other.name.split(' ')[0] }))
              setBlocking(false)
            }}
          >
            {t('Block')}
          </Button>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {t('Neither of you can message the other or make new bookings with each other. This booking itself stays as it is; cancel it if you need to. You can unblock them from your profile. To tell Cappy about something wrong, report them as well.')}
        </p>
      </Sheet>

      <Sheet
        open={declining}
        onClose={() => setDeclining(false)}
        title={t('Decline the request from {name}?', { name: buyer })}
        footer={
          <Button
            block
            size="lg"
            variant="danger"
            disabled={!online || busy}
            onClick={() => {
              void done(() => declineBooking(booking.id, reason), t('Declined. They have been told'))
              setDeclining(false)
            }}
          >
            {t('Send decline')}
          </Button>
        }
      >
        <div className="flex flex-wrap gap-2 pb-3">
          {DECLINE_REASONS.map((r) => (
            <Chip key={r} selected={reason === r} onClick={() => setReason(r)}>
              {t(r)}
            </Chip>
          ))}
        </div>
      </Sheet>

      <Sheet
        open={disputing}
        onClose={() => setDisputing(false)}
        title={t('What went wrong?')}
        footer={
          <Button
            block
            size="lg"
            disabled={!online || busy || !problem.trim()}
            onClick={() =>
              void (async () => {
                // On a refusal the sheet stays open with what was typed (V4-4).
                setBusy(true)
                try {
                  await disputeBooking(booking.id, problem.trim())
                  setDisputing(false)
                  setProblem('')
                  toast(t('Reported. The payment is on hold'))
                } catch (err) {
                  toast(messageOf(err), 'error')
                } finally {
                  setBusy(false)
                  await Promise.all([
                    qc.invalidateQueries({ queryKey: ['booking', booking.id] }),
                    qc.invalidateQueries({ queryKey: ['bookings'] }),
                  ])
                }
              })()
            }
          >
            {t('Report the problem')}
          </Button>
        }
      >
        <div className="space-y-3 pb-3">
          <p className="t-body text-[var(--ink-2)]">
            {t('The payment to {name} is held while Cappy looks into it.', { name: first })}
          </p>
          <Textarea
            value={problem}
            onChange={(e) => setProblem(e.target.value)}
            rows={4}
            maxLength={500}
            placeholder={t('They did not turn up, it was broken…')}
          />
        </div>
      </Sheet>

      <Sheet
        open={rateOpen}
        onClose={() => setRateOpen(false)}
        title={t('How did it go with {name}?', { name: first })}
        footer={
          <Button
            block
            size="lg"
            disabled={!online || onTime === null || stars === 0 || busy}
            onClick={() => {
              if (onTime === null || stars === 0) return
              void rate({ onTime, quality: stars, tags, note: note.trim() || undefined })
              setRateOpen(false)
            }}
          >
            {t('Submit rating')}
          </Button>
        }
      >
        <div className="space-y-5 pb-3">
          <div>
            <p className="mb-3 text-body font-semibold text-[var(--ink-2)]">
              {t('Was it ready when they said?')}
            </p>
            <div className="flex gap-2">
              {[
                { v: true, label: t('On time') },
                { v: false, label: t('Late') },
              ].map((o) => (
                <button
                  key={o.label}
                  onClick={() => setOnTime(o.v)}
                  aria-pressed={onTime === o.v}
                  className={`min-h-[48px] flex-1 rounded-[var(--radius-capsule)] border text-body font-semibold transition-colors duration-[var(--dur-short)] ${
                    onTime === o.v
                      ? 'border-[var(--field)] bg-[var(--field)] text-[var(--on-field)]'
                      : 'border-[var(--line)] hover:border-[var(--ink-4)]'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-3 text-body font-semibold text-[var(--ink-2)]">
              {t('How was the thing itself?')}
            </p>
            <StarPicker value={stars} onChange={setStars} label={t('How was the thing itself?')} />
          </div>

          <div>
            <p className="mb-3 text-body font-semibold text-[var(--ink-2)]">
              {t('What stood out?')} <span className="font-normal text-[var(--ink-4)]">{t('Pick any')}</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {REVIEW_TAGS.map((tag) => (
                <Chip
                  key={tag}
                  selected={tags.includes(tag)}
                  onClick={() =>
                    setTags((cur) => (cur.includes(tag) ? cur.filter((x) => x !== tag) : [...cur, tag]))
                  }
                >
                  {t(tag)}
                </Chip>
              ))}
            </div>
          </div>

          <Field
            label={t('Anything the next person should know?')}
            hint={t('Optional. Shown on the listing.')}
            htmlFor="review-note"
          >
            <Textarea
              id="review-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={400}
              placeholder={t('Handover was quick, bring your own blades…')}
            />
          </Field>

          <p className="t-sm text-[var(--ink-4)]">
            {t('Your rating changes who shows up first for the next person searching, and your words are what they read before they decide.')}{' '}
            {t('Reviews are blind: yours is published once you have both rated, or 14 days after the booking.')}
          </p>
        </div>
      </Sheet>

      <Sheet
        open={ratingRenter}
        onClose={() => setRatingRenter(false)}
        title={t('How was {name} as a renter?', { name: buyer })}
        footer={
          <Button
            block
            size="lg"
            disabled={!online || busy || renterStars === 0}
            onClick={() => {
              void rateTheRenter(renterStars)
              setRatingRenter(false)
            }}
          >
            {t('Submit rating')}
          </Button>
        }
      >
        <div className="pb-3">
          <StarPicker value={renterStars} onChange={setRenterStars} label={t('How was {name} as a renter?', { name: buyer })} />
        </div>
        <p className="t-sm pb-3 text-[var(--ink-4)]">
          {t('Only owners see renter ratings, when that person asks to book. Reviews are blind: yours is published once you have both rated, or 14 days after the booking.')}
        </p>
      </Sheet>
      <Sheet
        open={noShowOpen}
        onClose={() => setNoShowOpen(false)}
        title={t('{name} did not show up?', { name: asOwner ? buyer : first })}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              disabled={!online || busy}
              onClick={() => {
                void done(() => reportNoShow(booking.id), t('Reported'))
                setNoShowOpen(false)
              }}
            >
              {t('Yes, report the no-show')}
            </Button>
            <Button block variant="quiet" onClick={() => setNoShowOpen(false)}>
              {t('Not yet')}
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {asOwner
            ? t('The booking ends and {name} gets nothing back; you are paid for it. Only report this if they really did not come: they can contest it.', { name: buyer })
            : t('The booking ends and you get back everything you paid, {amount}. It counts against {name}. Only report this if they really did not come.', {
                amount: formatMoney(quote.total, cur),
                name: first,
              })}
        </p>
      </Sheet>
      {ticket && !asOwner && (
        <Ticket
          booking={booking}
          title={title}
          instant={Boolean(booking.listing?.instantBook ?? listing?.instantBook)}
          ownerName={first}
          responseMins={owner?.responseMins}
          onDone={closeTicket}
          onMessage={() => {
            closeTicket()
            requestAnimationFrame(() => document.getElementById('messages')?.scrollIntoView({ block: 'start' }))
          }}
        />
      )}
    </Screen>
  )
}

/** Tap a star, then submit: a mis-tap is corrected before anything is posted (V3-8). */
function StarPicker({ value, onChange, label }: { value: number; onChange: (n: number) => void; label: string }) {
  const [hover, setHover] = useState(0)
  const shown = hover || value
  return (
    <div role="radiogroup" aria-label={label} className="flex justify-between gap-1" onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          role="radio"
          aria-checked={value === n}
          aria-label={plural(n, '{n} star', '{n} stars')}
          onClick={() => onChange(n)}
          onMouseEnter={() => setHover(n)}
          className="grid h-12 w-12 place-items-center rounded-[var(--radius-control)] transition-colors duration-[var(--dur-short)] hover:bg-[var(--sunken)]"
        >
          <Icon
            name="star"
            size={30}
            strokeWidth={0}
            className={`transition-colors duration-[var(--dur-short)] ${n <= shown ? 'fill-[var(--ink)]' : 'fill-[var(--line-strong)]'}`}
          />
        </button>
      ))}
    </div>
  )
}
