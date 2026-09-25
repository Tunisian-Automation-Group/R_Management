import { useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useAuthReady, useSession } from '../../data/auth.ts'
import { SignedOut } from '../components/SignedOut.tsx'
import { NotFound } from './NotFound.tsx'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { Booking, BookingStatus, Listing, Outcome, Owner } from '../../domain/types.ts'
import { rating } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { trackRecord } from '../../domain/match.ts'
import { formatEurExact } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import {
  actOnBooking,
  declineBooking,
  disputeBooking,
  getBookingPayment,
  rateBooking,
  useBooking,
  useListing,
  useOwner,
  usePaymentsConfig,
  type BookingAction,
} from '../../data/repo.ts'
import { PayStep } from '../components/PayStep.tsx'
import { DECLINE_REASONS } from './Earn.tsx'
import { messageOf, useToast } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Icon } from '../components/Icon.tsx'
import { Avatar, Banner, Button, Card, Chip, Field, Row, Sheet, Stars, Textarea } from '../components/ui.tsx'
import { REVIEW_TAGS } from '../../domain/reviews.ts'
import { distance, range, relative, responseTime } from '../format.ts'

const STEPS: { id: BookingStatus; label: string; note: string; ownerNote: string }[] = [
  { id: 'requested', label: 'Requested', note: 'Waiting for the owner to accept', ownerNote: 'Waiting for your answer' },
  { id: 'accepted', label: 'Confirmed', note: 'The window is held for you', ownerNote: 'The window is held for them' },
  { id: 'active', label: 'In progress', note: 'You have it now', ownerNote: 'They have it now' },
  { id: 'completed', label: 'Finished', note: 'Handed back', ownerNote: 'Handed back; your payout is on its way' },
]

const DEAD: BookingStatus[] = ['declined', 'cancelled', 'expired', 'payment_failed']
// Start may be marked from half an hour before the window; the backend refuses earlier.
const START_EARLY_MS = 30 * 60_000

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
      <Screen title="Booking">
        <SignedOut what="see this booking" next={`/bookings/${id}`} />
      </Screen>
    )
  }
  if (!authReady || booking.isPending) return <Screen back="/bookings">{null}</Screen>
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
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const [cancelling, setCancelling] = useState(false)
  const [declining, setDeclining] = useState(false)
  const [reason, setReason] = useState(DECLINE_REASONS[0])
  const [disputing, setDisputing] = useState(false)
  const [problem, setProblem] = useState('')
  const [rateOpen, setRateOpen] = useState(false)
  const [stars, setStars] = useState(0)
  const [onTime, setOnTime] = useState<boolean | null>(null)
  const [tags, setTags] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const { quote } = booking.match
  const title = booking.listing?.title ?? listing?.title ?? 'Booked listing'
  const ownerName = owner?.name ?? booking.listing?.ownerName ?? 'The owner'
  const district = booking.listing?.district ?? listing?.district ?? ''
  const first = ownerName.split(' ')[0]
  const stepIndex = STEPS.findIndex((s) => s.id === booking.status)
  const dead = DEAD.includes(booking.status)
  // requesterId is only ever sent to the owner.
  const asOwner = Boolean(booking.requesterId)
  const buyer = requester?.name.split(' ')[0] ?? 'The buyer'
  const other = asOwner ? requester : owner
  const startsAt = Date.parse(booking.match.start)
  const canStart = Date.now() >= startsAt - START_EARLY_MS
  const begun = Date.now() >= startsAt

  const payments = usePaymentsConfig()
  const payNow =
    !asOwner && booking.status === 'awaiting_payment' && payments.data?.provider === 'stripe'
  const payment = useQuery({
    queryKey: ['bookingPayment', booking.id],
    queryFn: () => getBookingPayment(booking.id),
    enabled: payNow,
    retry: false,
  })

  const done = async (write: () => Promise<unknown>, message?: string) => {
    setBusy(true)
    try {
      await write()
      if (message) toast(message)
    } catch (err) {
      toast(messageOf(err))
    } finally {
      setBusy(false)
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['booking', booking.id] }),
        qc.invalidateQueries({ queryKey: ['bookings'] }),
      ])
    }
  }
  const act = (action: BookingAction, message?: string) => done(() => actOnBooking(booking.id, action), message)
  const rate = (outcome: Outcome) =>
    done(async () => {
      await rateBooking(booking.id, outcome)
      // The owner's record and the listing's reviews change a moment later.
      void qc.invalidateQueries({ queryKey: ['listing', booking.match.listingId] })
      void qc.invalidateQueries({ queryKey: ['reviews', booking.match.listingId] })
    }, `Review posted on ${title}`)

  const cancelButton = (
    <Button block variant="danger" disabled={busy} onClick={() => setCancelling(true)}>
      {booking.status === 'accepted' ? 'Cancel booking' : 'Cancel request'}
    </Button>
  )
  const disputeButton = (
    <Button block variant="quiet" disabled={busy} onClick={() => setDisputing(true)}>
      Report a problem
    </Button>
  )
  const startButton = (
    <div>
      <Button block size="lg" disabled={busy || !canStart} onClick={() => void act('start', asOwner ? 'Marked as handed over' : 'Enjoy it')}>
        {canStart
          ? asOwner
            ? 'I have handed it over'
            : 'I have collected it'
          : `Hand-over opens ${relative(new Date(startsAt - START_EARLY_MS).toISOString())}`}
      </Button>
      {!canStart && (
        <p className="t-sm mt-2 text-center text-[var(--ink-3)]">
          Either of you can mark the hand-over from 30 minutes before the booked time.
        </p>
      )}
    </div>
  )
  const home = asOwner ? (
    <Button block size="lg" variant="secondary" onClick={() => nav('/earn')}>
      Back to Earn
    </Button>
  ) : (
    <Button block size="lg" variant="secondary" onClick={() => nav('/')}>
      Browse capacity
    </Button>
  )

  let footer: ReactNode
  switch (asOwner ? `owner:${booking.status}` : booking.status) {
    case 'owner:requested':
      footer = (
        <div className="space-y-2">
          <Button block size="lg" disabled={busy} onClick={() => void act('accept', `Accepted. ${buyer} has been told`)}>
            Accept
          </Button>
          <Button block variant="quiet" disabled={busy} onClick={() => setDeclining(true)}>
            Decline
          </Button>
        </div>
      )
      break
    case 'owner:accepted':
      footer = (
        <div className="space-y-2">
          {startButton}
          {!begun && cancelButton}
        </div>
      )
      break
    case 'awaiting_payment':
    case 'requested':
      footer = cancelButton
      break
    case 'accepted':
      footer = (
        <div className="space-y-2">
          {startButton}
          {begun ? disputeButton : cancelButton}
        </div>
      )
      break
    case 'active':
      footer = (
        <div className="space-y-2">
          <Button
            block
            size="lg"
            disabled={busy}
            onClick={() => {
              void act('complete')
              setRateOpen(true)
            }}
          >
            Mark as handed back
          </Button>
          {disputeButton}
        </div>
      )
      break
    case 'completed':
      // A finished booking that went well is the likeliest next booking there is.
      footer = booking.outcome ? (
        <div className="space-y-2">
          {listing && listing.active && (
            <Button block size="lg" onClick={() => nav(`/listing/${listing.id}`)}>
              Book again
            </Button>
          )}
          <Button block variant="quiet" onClick={() => nav('/')}>
            Find something else
          </Button>
        </div>
      ) : (
        <Button block size="lg" onClick={() => setRateOpen(true)}>
          Rate {first}
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
        <h1 className="t-h1 text-balance">{title}</h1>
        <p className="t-lede mt-2 text-[var(--ink-3)]">
          {asOwner ? `Booked by ${requester?.name ?? 'a buyer'}` : ownerName}
          {district && ` · ${district}`}
        </p>
      </header>

      {booking.status === 'declined' ? (
        <Banner
          tone="danger"
          title={asOwner ? 'You declined this request' : `${first} could not take this one`}
          body={`${booking.declineReason || 'No reason given.'} The hold on the card is released; nothing was charged.`}
          action={
            <Button size="sm" variant="secondary" onClick={() => nav('/')}>
              Find another
            </Button>
          }
        />
      ) : booking.status === 'disputed' ? (
        <Banner
          tone="warn"
          title="Under review"
          body={
            asOwner
              ? `${buyer} reported a problem with this booking. Your payout is on hold while Cappy looks into it; we will be in touch.`
              : 'You reported a problem. The payment is on hold while Cappy looks into it; we will be in touch.'
          }
        />
      ) : booking.status === 'cancelled' ? (
        <Banner
          tone="warn"
          title="This booking was cancelled"
          body={
            asOwner
              ? 'The buyer gets back everything they paid, and the window is free again.'
              : 'The hold on your card is released, and anything already charged is refunded in full.'
          }
        />
      ) : booking.status === 'expired' ? (
        <Banner tone="warn" title="This request lapsed" body="It was not paid for or answered in time. Nothing was charged." />
      ) : booking.status === 'payment_failed' ? (
        <Banner
          tone="danger"
          title="The payment could not be taken"
          body="Nothing was charged, and the window is free again."
          action={
            asOwner ? undefined : (
              <Button size="sm" variant="secondary" onClick={() => nav(`/listing/${booking.match.listingId}`)}>
                Try again
              </Button>
            )
          }
        />
      ) : booking.status === 'awaiting_payment' ? (
        <Banner
          tone="warn"
          title={payNow ? 'Finish paying to send your request' : 'Authorising your card'}
          body={`${first} is asked as soon as the card is authorised.${booking.expiresAt ? ` It lapses ${relative(booking.expiresAt)} if not.` : ''}`}
        />
      ) : booking.status === 'requested' && asOwner ? (
        <Banner
          tone="warn"
          title={`${buyer} wants this window`}
          body={`${range(booking.match.start, booking.match.end)}. Their card is held and charged when you accept.${booking.expiresAt ? ` Answer ${relative(booking.expiresAt)}, or it lapses.` : ''}`}
        />
      ) : booking.status === 'requested' ? (
        <Banner
          tone="warn"
          title={`Waiting for ${first}`}
          body={`${owner ? `${responseTime(owner.responseMins)}. ` : ''}Your card is held, and charged only if they accept.`}
        />
      ) : booking.status === 'accepted' ? (
        <Banner
          tone="success"
          title="Confirmed"
          body={
            asOwner
              ? `${buyer} is coming ${range(booking.match.start, booking.match.end)}.`
              : `${first} is expecting you ${range(booking.match.start, booking.match.end)}.`
          }
        />
      ) : null}

      {payNow && payment.data && payments.data?.publishableKey && (
        <div className="mt-4">
          <PayStep
            publishableKey={payments.data.publishableKey}
            clientSecret={payment.data.clientSecret}
            bookingId={booking.id}
            onPaid={() => void qc.invalidateQueries({ queryKey: ['booking', booking.id] })}
          />
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
                    className={`grid h-7 w-7 shrink-0 place-items-center rounded-[var(--radius-control)] text-[11.5px] font-bold transition-colors duration-[240ms] ${
                      reached
                        ? 'bg-[var(--success)] text-white'
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
                    className={`text-[15.5px] leading-7 ${current ? 'font-bold' : 'font-semibold'}`}
                  >
                    {step.label}
                  </p>
                  <p className="t-sm text-[var(--ink-3)]">{asOwner ? step.ownerNote : step.note}</p>
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {/* Handover detail only appears once there is something to hand over:
          the address is shared with the buyer when the owner accepts. */}
      {(booking.status === 'accepted' || booking.status === 'active') && (booking.handover || listing) && (
        <Card className="p-5">
          <h2 className="t-label mb-2.5">Getting in</h2>
          {booking.handover?.address && (
            <p className="text-[15.5px] font-semibold text-[var(--ink)]">{booking.handover.address}</p>
          )}
          <p className="t-body mt-1 text-[var(--ink-2)]">{booking.handover?.instructions ?? listing?.instructions}</p>
          <p className="t-sm tnum mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            <Icon name="pin" size={14} />
            {district}
            {!asOwner && ` · ${distance(booking.match.distanceKm)} away`}
          </p>
        </Card>
      )}

      {other && (
        <Card className="mt-3 p-5">
          <div className="flex items-center gap-3.5">
            <Avatar initials={other.initials} size={44} business={other.kind === 'business'} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15.5px] font-semibold">{other.name}</p>
              <p className="t-sm text-[var(--ink-3)]">{asOwner ? 'Booked this window' : trackRecord(other)}</p>
            </div>
            {!asOwner && <Stars value={rating(other)} count={other.jobsDone} />}
          </div>
        </Card>
      )}

      <Card className="mt-3 p-5">
        <h2 className="t-label mb-2">What you agreed</h2>
        <Row label="When" value={range(booking.match.start, booking.match.end)} />
        <Row
          label={booking.requirement.mode === 'window' ? 'Duration' : 'Batch'}
          value={
            booking.requirement.mode === 'batch'
              ? `${booking.requirement.quantity} parts · ${durationLabel(quote.hours)}`
              : durationLabel(quote.hours)
          }
        />
        <div className="my-2 border-t border-[var(--line)]" />
        {dead ? (
          <Row
            label="Charged"
            value={booking.status === 'cancelled' ? 'Nothing: released or refunded' : 'Nothing: hold released'}
            strong
          />
        ) : (
          <>
            <Row label="Total" value={formatEurExact(quote.total)} strong />
            <Row
              label={`Cappy fee · ${PLATFORM_FEE_BPS / 100}%`}
              value={formatEurExact(quote.platformFee)}
              tone="muted"
            />
            <Row label={asOwner ? 'You receive' : `${first} receives`} value={formatEurExact(quote.ownerNet)} tone="accent" />
          </>
        )}
      </Card>

      {booking.outcome && (
        <Card className="anim-rise mt-3 p-5">
          <h2 className="t-label mb-2.5">{asOwner ? `${buyer}'s rating` : 'Your rating'}</h2>
          <div className="flex items-center gap-2">
            <span className="flex" aria-label={`${booking.outcome.quality} out of 5`}>
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
              {booking.outcome.onTime ? 'On time' : 'Late'}
            </span>
          </div>
          <p className="t-sm mt-4 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            Ratings decide where {first} ranks for the next person searching.
          </p>
        </Card>
      )}

      <Sheet
        open={cancelling}
        onClose={() => setCancelling(false)}
        title={booking.status === 'accepted' ? 'Cancel this booking?' : 'Cancel this request?'}
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              disabled={busy}
              onClick={() => {
                void act('cancel', 'Cancelled')
                setCancelling(false)
              }}
            >
              Yes, cancel it
            </Button>
            <Button block variant="quiet" onClick={() => setCancelling(false)}>
              Keep it
            </Button>
          </div>
        }
      >
        <p className="t-body pb-3 text-[var(--ink-2)]">
          {asOwner
            ? `${buyer} will be told, and gets back everything they paid.`
            : booking.status === 'accepted'
              ? `${first} will be told the window is free again, and you get back everything you paid.`
              : `${first} will be told the window is free again. The hold on your card is released; nothing is charged.`}
        </p>
      </Sheet>

      <Sheet
        open={declining}
        onClose={() => setDeclining(false)}
        title={`Decline ${buyer}'s request?`}
        footer={
          <Button
            block
            size="lg"
            variant="danger"
            disabled={busy}
            onClick={() => {
              void done(() => declineBooking(booking.id, reason), 'Declined. They have been told')
              setDeclining(false)
            }}
          >
            Decline
          </Button>
        }
      >
        <div className="flex flex-wrap gap-2 pb-3">
          {DECLINE_REASONS.map((r) => (
            <Chip key={r} selected={reason === r} onClick={() => setReason(r)}>
              {r}
            </Chip>
          ))}
        </div>
      </Sheet>

      <Sheet
        open={disputing}
        onClose={() => setDisputing(false)}
        title="What went wrong?"
        footer={
          <Button
            block
            size="lg"
            disabled={busy || !problem.trim()}
            onClick={() => {
              void done(() => disputeBooking(booking.id, problem.trim()), 'Reported. The payment is on hold')
              setDisputing(false)
            }}
          >
            Report the problem
          </Button>
        }
      >
        <div className="space-y-3 pb-3">
          <p className="t-body text-[var(--ink-2)]">
            The payment to {first} is held while Cappy looks into it.
          </p>
          <Textarea
            value={problem}
            onChange={(e) => setProblem(e.target.value)}
            rows={4}
            maxLength={500}
            placeholder="They did not turn up, it was broken…"
          />
        </div>
      </Sheet>

      <Sheet
        open={rateOpen}
        onClose={() => setRateOpen(false)}
        title={`How did it go with ${first}?`}
        footer={
          <Button
            block
            size="lg"
            disabled={onTime === null || stars === 0 || busy}
            onClick={() => {
              if (onTime === null || stars === 0) return
              void rate({ onTime, quality: stars, tags, note: note.trim() || undefined })
              setRateOpen(false)
            }}
          >
            Submit rating
          </Button>
        }
      >
        <div className="space-y-5 pb-3">
          <div>
            <p className="mb-3 text-[14px] font-semibold text-[var(--ink-2)]">
              Was it ready when they said?
            </p>
            <div className="flex gap-2">
              {[
                { v: true, label: 'On time' },
                { v: false, label: 'Late' },
              ].map((o) => (
                <button
                  key={o.label}
                  onClick={() => setOnTime(o.v)}
                  aria-pressed={onTime === o.v}
                  className={`min-h-[48px] flex-1 rounded-[var(--radius-control)] border text-[14.5px] font-semibold transition-colors duration-[160ms] ${
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
            <p className="mb-3 text-[14px] font-semibold text-[var(--ink-2)]">
              How was the thing itself?
            </p>
            <div className="flex justify-between gap-1">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => setStars(n)}
                  aria-label={`${n} star${n === 1 ? '' : 's'}`}
                  aria-pressed={stars === n}
                  className="grid h-12 w-12 place-items-center rounded-[var(--radius-control)] transition-colors duration-[160ms] hover:bg-[var(--sunken)]"
                >
                  <Icon
                    name="star"
                    size={30}
                    strokeWidth={0}
                    className={`transition-colors duration-[160ms] ${n <= stars ? 'fill-[var(--ink)]' : 'fill-[var(--line-strong)]'}`}
                  />
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-3 text-[14px] font-semibold text-[var(--ink-2)]">
              What stood out? <span className="font-normal text-[var(--ink-4)]">Pick any</span>
            </p>
            <div className="flex flex-wrap gap-2">
              {REVIEW_TAGS.map((t) => (
                <Chip
                  key={t}
                  selected={tags.includes(t)}
                  onClick={() =>
                    setTags((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : [...cur, t]))
                  }
                >
                  {t}
                </Chip>
              ))}
            </div>
          </div>

          <Field
            label="Anything the next person should know?"
            hint="Optional. Shown on the listing."
            htmlFor="review-note"
          >
            <Textarea
              id="review-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              maxLength={400}
              placeholder="Handover was quick, bring your own blades…"
            />
          </Field>

          <p className="t-sm text-[var(--ink-4)]">
            Your rating changes who shows up first for the next person searching, and your
            words are what they read before they decide.
          </p>
        </div>
      </Sheet>
    </Screen>
  )
}
