import { useState, type ReactNode } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import type { Booking, BookingStatus, Listing, Owner, Slot } from '../../domain/types.ts'
import { isWindow, rating } from '../../domain/types.ts'
import { durationLabel } from '../../domain/categories.ts'
import { trackRecord } from '../../domain/match.ts'
import { formatEurExact } from '../../domain/money.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { useCappy, useLookups, type Event } from '../store.tsx'
import { Screen } from '../components/AppShell.tsx'
import { Photo } from '../components/Photo.tsx'
import { Icon } from '../components/Icon.tsx'
import { Avatar, Banner, Button, Card, Chip, Field, Row, Sheet, Stars, Textarea } from '../components/ui.tsx'
import { REVIEW_TAGS } from '../../domain/reviews.ts'
import { distance, range, responseTime } from '../format.ts'

const STEPS: { id: BookingStatus; label: string; note: string }[] = [
  { id: 'requested', label: 'Requested', note: 'Waiting for the owner to accept' },
  { id: 'accepted', label: 'Confirmed', note: 'The window is held for you' },
  { id: 'active', label: 'In progress', note: 'You have it now' },
  { id: 'completed', label: 'Finished', note: 'Handed back' },
]

export function BookingDetail() {
  const { id } = useParams()
  const { state } = useCappy()
  const { listing: findListing, owner: findOwner, slotsFor } = useLookups()

  // A booking is only missing once the store has loaded.
  if (!state.ready) return <Screen back="/bookings">{null}</Screen>

  const booking = state.bookings.find((b) => b.id === id)
  if (!booking) return <Navigate to="/bookings" replace />

  const listing = findListing(booking.match.listingId)
  const owner = findOwner(booking.match.ownerId)
  if (!listing || !owner) return <Navigate to="/bookings" replace />

  // Remount when the booking changes so the rating form never carries over.
  return (
    <Detail
      key={booking.id}
      booking={booking}
      listing={listing}
      owner={owner}
      slots={slotsFor(listing.id)}
    />
  )
}

function Detail({
  booking,
  listing,
  owner,
  slots,
}: {
  booking: Booking
  listing: Listing
  owner: Owner
  slots: Slot[]
}) {
  const nav = useNavigate()
  const { send } = useCappy()

  const [cancelling, setCancelling] = useState(false)
  const [rateOpen, setRateOpen] = useState(false)
  const [stars, setStars] = useState(0)
  const [onTime, setOnTime] = useState<boolean | null>(null)
  const [tags, setTags] = useState<string[]>([])
  const [note, setNote] = useState('')

  const { quote } = booking.match
  const first = owner.name.split(' ')[0]
  const stepIndex = STEPS.findIndex((s) => s.id === booking.status)
  const dead = booking.status === 'declined' || booking.status === 'cancelled'

  const act = (e: Event, toast?: string) => {
    send(e)
    if (toast) send({ type: 'TOAST', message: toast })
  }

  let footer: ReactNode
  switch (booking.status) {
    case 'requested':
      footer = (
        <Button block size="lg" variant="danger" onClick={() => setCancelling(true)}>
          Cancel request
        </Button>
      )
      break
    case 'accepted':
      footer = (
        <Button
          block
          size="lg"
          onClick={() => act({ type: 'BOOKING_STARTED', id: booking.id }, 'Enjoy it')}
        >
          I have collected it
        </Button>
      )
      break
    case 'active':
      footer = (
        <Button
          block
          size="lg"
          onClick={() => {
            send({ type: 'BOOKING_COMPLETED', id: booking.id })
            setRateOpen(true)
          }}
        >
          Mark as handed back
        </Button>
      )
      break
    case 'completed':
      // A finished booking that went well is the likeliest next booking there is.
      // "Book something else" sent people back to a search they had already done.
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
      footer = (
        <Button block size="lg" variant="secondary" onClick={() => nav('/')}>
          Browse capacity
        </Button>
      )
  }

  return (
    <Screen
      back="/bookings"
      hero={
        <Photo
          src={listing?.photos?.[0]}
          alt={listing?.title ?? 'Booked listing'}
          slots={slots}
          categoryId={booking.requirement.category}
          aspect={2.2}
          priority
          className={`w-full md:rounded-b-[var(--radius-sheet)] ${dead ? 'opacity-55 grayscale' : ''}`}
          style={{ viewTransitionName: 'hero' }}
        />
      }
      footer={footer}
    >
      <header className="-mt-1 mb-6">
        <h1 className="t-h1 text-balance">{listing.title}</h1>
        <p className="t-lede mt-2 text-[var(--ink-3)]">
          {owner.name} · {listing.district}
        </p>
      </header>

      {booking.status === 'declined' ? (
        <Banner
          tone="danger"
          title={`${first} could not take this one`}
          body={booking.declineReason || 'No reason given.'}
          action={
            <Button size="sm" variant="secondary" onClick={() => nav('/')}>
              Find another
            </Button>
          }
        />
      ) : booking.status === 'cancelled' ? (
        <Banner tone="warn" title="You cancelled this request" body="Nothing was charged." />
      ) : booking.status === 'requested' ? (
        <Banner
          tone="warn"
          title={`Waiting for ${first}`}
          body={`${responseTime(owner.responseMins)}. Nothing is charged until they accept.`}
        />
      ) : booking.status === 'accepted' ? (
        <Banner
          tone="accent"
          title="Confirmed"
          body={`${first} is expecting you ${range(booking.match.start, booking.match.end)}.`}
        />
      ) : null}

      {!dead && (
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
                  <p className="t-sm text-[var(--ink-3)]">{step.note}</p>
                </div>
              </li>
            )
          })}
        </ol>
      )}

      {/* Handover detail only appears once there is something to hand over. */}
      {(booking.status === 'accepted' || booking.status === 'active') && (
        <Card className="p-5">
          <h2 className="t-label mb-2.5">Getting in</h2>
          <p className="t-body text-[var(--ink-2)]">{listing.instructions}</p>
          <p className="t-sm tnum mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            <Icon name="pin" size={14} />
            {listing.district} · {distance(booking.match.distanceKm)} away
          </p>
        </Card>
      )}

      <Card className="mt-3 p-5">
        <div className="flex items-center gap-3.5">
          <Avatar initials={owner.initials} size={44} business={owner.kind === 'business'} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[15.5px] font-semibold">{owner.name}</p>
            <p className="t-sm text-[var(--ink-3)]">{trackRecord(owner)}</p>
          </div>
          <Stars value={rating(owner)} count={owner.jobsDone} />
        </div>
      </Card>

      <Card className="mt-3 p-5">
        <h2 className="t-label mb-2">What you agreed</h2>
        <Row label="When" value={range(booking.match.start, booking.match.end)} />
        <Row
          label={isWindow(listing) ? 'Duration' : 'Batch'}
          value={
            booking.requirement.mode === 'batch'
              ? `${booking.requirement.quantity} parts · ${durationLabel(quote.hours)}`
              : durationLabel(quote.hours)
          }
        />
        <div className="my-2 border-t border-[var(--line)]" />
        <Row label="Total" value={formatEurExact(quote.total)} strong />
        <Row
          label={`Cappy fee · ${PLATFORM_FEE_BPS / 100}%`}
          value={formatEurExact(quote.platformFee)}
          tone="muted"
        />
        <Row label={`${first} receives`} value={formatEurExact(quote.ownerNet)} tone="accent" />
      </Card>

      {booking.outcome && (
        <Card className="anim-rise mt-3 p-5">
          <h2 className="t-label mb-2.5">Your rating</h2>
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
            {first}'s record is now {trackRecord(owner)}, and that is what decides where
            they rank for the next person searching.
          </p>
        </Card>
      )}

      <Sheet
        open={cancelling}
        onClose={() => setCancelling(false)}
        title="Cancel this request?"
        footer={
          <div className="space-y-2">
            <Button
              block
              size="lg"
              variant="danger"
              onClick={() => {
                act({ type: 'BOOKING_CANCELLED', id: booking.id }, 'Request cancelled')
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
          {first} will be told the window is free again. Nothing has been charged, so there
          is nothing to refund.
        </p>
      </Sheet>

      <Sheet
        open={rateOpen}
        onClose={() => setRateOpen(false)}
        title={`How did it go with ${first}?`}
        footer={
          <Button
            block
            size="lg"
            disabled={onTime === null || stars === 0}
            onClick={() => {
              if (onTime === null || stars === 0) return
              act(
                {
                  type: 'BOOKING_RATED',
                  id: booking.id,
                  outcome: { onTime, quality: stars, tags, note: note.trim() || undefined },
                },
                // Say where it went. "Thanks" alone leaves you wondering whether
                // anybody will ever see it.
                `Review posted on ${listing?.title ?? 'the listing'}`,
              )
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
