import { useMemo, useState } from 'react'
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Booking, Requirement } from '../../domain/types.ts'
import { isWindow, rating } from '../../domain/types.ts'
import { category, durationLabel } from '../../domain/categories.ts'
import { offersFor, type Offer } from '../../domain/availability.ts'
import { distanceKm, matchForOffer, trackRecord } from '../../domain/match.ts'
import { hoursFor, quoteFor, PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { formatEur, formatEurExact } from '../../domain/money.ts'
import { HOME_DISTRICT } from '../../data/seed.ts'
import { ME, useCappy, useLookups } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { CapacityBar } from '../components/CapacityBar.tsx'
import { Plate, WhenBadge } from '../components/Cover.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Reviews } from '../components/Reviews.tsx'
import { Icon } from '../components/Icon.tsx'
import {
  Avatar,
  Banner,
  Button,
  Card,
  Chip,
  EmptyState,
  Row,
  Sheet,
  Stars,
} from '../components/ui.tsx'
import { day, distance, range, relative, responseTime, time } from '../format.ts'

const QUANTITY_STEPS = [10, 25, 50, 100, 250, 500, 1000]

export function Listing() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const { state, send } = useCappy()
  const { listing: findListing, owner: findOwner, slotsFor, reviewsFor } = useLookups()

  const listing = id ? findListing(id) : undefined
  const owner = listing ? findOwner(listing.ownerId) : undefined

  const [hours, setHours] = useState(() =>
    listing && isWindow(listing) ? Math.max(listing.minHours, state.search.hours) : 0,
  )
  const [quantity, setQuantity] = useState(state.search.quantity)
  const [picked, setPicked] = useState<Offer | null>(null)
  const [dayPick, setDayPick] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  const now = useMemo(() => new Date(), [])
  const slots = listing ? slotsFor(listing.id) : []

  const requirement: Requirement | null = useMemo(() => {
    if (!listing) return null
    const until = new Date(now.getTime() + 28 * 86_400_000).toISOString()
    return isWindow(listing)
      ? {
          mode: 'window',
          category: listing.category,
          hours,
          earliest: now.toISOString(),
          latest: until,
          district: HOME_DISTRICT,
          maxDistanceKm: 500,
        }
      : {
          mode: 'batch',
          category: listing.category,
          quantity,
          deadline: until,
          district: HOME_DISTRICT,
          maxDistanceKm: 500,
        }
  }, [listing, hours, quantity, now])

  const needed = listing && requirement ? hoursFor(requirement, listing) : null

  const offers = useMemo(() => {
    if (!listing || needed === null) return []
    return offersFor(
      slots,
      needed,
      now.toISOString(),
      new Date(now.getTime() + 28 * 86_400_000).toISOString(),
      60,
    )
  }, [slots, needed, now, listing])

  // Pre-select whatever brought them here: the slot from the results list, else
  // the soonest. Nobody should land on this screen with nothing chosen.
  const selected = useMemo(() => {
    if (picked) return picked
    const fromResults = params.get('slot')
    return offers.find((o) => o.slotId === fromResults) ?? offers[0] ?? null
  }, [picked, offers, params])

  // A listing is only missing once the store has loaded. Before that the lookup
  // is empty for every id, including real ones.
  if (!state.ready) return <Screen back="/">{null}</Screen>
  if (!listing || !owner) return <Navigate to="/" replace />

  const meta = category(listing.category)
  const quote = requirement ? quoteFor(requirement, listing) : null
  const km = distanceKm(
    state.world.districts[HOME_DISTRICT],
    state.world.districts[listing.district],
  )
  const stars = rating(owner)
  const mine = owner.id === ME

  const byDay = offers.reduce<Record<string, Offer[]>>((acc, o) => {
    const k = day(o.start)
    ;(acc[k] ??= []).push(o)
    return acc
  }, {})

  const book = () => {
    if (!requirement || !selected) return
    const match = matchForOffer(requirement, listing, owner, selected, km)
    if (!match) return
    const booking: Booking = {
      id: `bk_${Date.now().toString(36)}`,
      match,
      requirement,
      status: 'requested',
      createdAt: new Date().toISOString(),
    }
    send({ type: 'BOOKING_REQUESTED', booking })
    send({ type: 'TOAST', message: `Request sent to ${owner.name.split(' ')[0]}` })
    setConfirming(false)
    nav(`/bookings/${booking.id}`, { replace: true })
  }

  return (
    <Screen
      back="/"
      hero={
        <Photo
          src={listing.photos?.[0]}
          alt={listing.title}
          slots={slots}
          categoryId={listing.category}
          aspect={16 / 10}
          priority
          className="w-full md:rounded-b-[var(--radius-sheet)]"
          style={{ viewTransitionName: 'hero' }}
        >
          <span
            className="absolute right-5 flex items-center gap-2"
            style={{ top: 'calc(var(--safe-top) + 14px)' }}
          >
            <span className="glass glass-dark rounded-full px-3 py-1 text-[12px] font-semibold">
              {meta.label}
            </span>
            <WhenBadge
              freeNow={Boolean(selected && Date.parse(selected.start) <= Date.now())}
              text={selected ? `Free ${relative(selected.start)}` : 'No window'}
            />
            {!mine && <SaveButton id={listing.id} title={listing.title} className="" />}
          </span>
        </Photo>
      }
      // One row in the phone's bottom bar, a stacked buy box in the page's side
      // panel. Same content, and the panel has the room to label it.
      footer={
        mine ? undefined : (
          <div className="flex items-center gap-4 md:block">
            <div className="min-w-0 flex-1">
              <p className="t-label hidden md:block">Your booking</p>
              <p className="tnum text-[19px] font-bold leading-tight md:mt-2 md:text-[28px]">
                {quote ? formatEur(quote.total) : '—'}
              </p>
              <p className="t-sm tnum truncate text-[var(--ink-3)] md:mt-1 md:whitespace-normal">
                {selected ? range(selected.start, selected.end) : 'No free window'}
              </p>
              {/* What the price is for, so the button is not a leap. */}
              {quote && (
                <p className="t-sm tnum hidden text-[var(--ink-3)] md:block">
                  {isWindow(listing)
                    ? durationLabel(quote.hours)
                    : `${quantity} ${meta.unitNoun} · ${durationLabel(quote.hours)} incl. setup`}
                </p>
              )}
            </div>
            <Button
              size="lg"
              disabled={!selected || !quote}
              onClick={() => setConfirming(true)}
              className="md:mt-5 md:w-full"
            >
              Request
            </Button>
            {/* The worry in front of any red button is "am I paying now". Nothing
                is charged here, so the box says so, and says who answers and when. */}
            <p className="t-sm mt-3 hidden text-center text-[var(--ink-4)] md:block">
              Nothing is charged here. {owner.name.split(' ')[0]} confirms first ·{' '}
              {responseTime(owner.responseMins).replace('Replies', 'replies')}
            </p>
          </div>
        )
      }
    >
      {/* ------------------------------------------------------------- title */}
      <header className="-mt-1">
        <h1 className="t-h1 text-balance">{listing.title}</h1>
        <p className="t-lede mt-2.5 text-[var(--ink-3)]">{listing.blurb}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[14px] text-[var(--ink-3)]">
          <span className="tnum inline-flex items-center gap-1.5">
            <Icon name="pin" size={15} className="text-[var(--ink-4)]" />
            {listing.district} · {distance(km)}
          </span>
          <span className="tnum">{formatEur(listing.ratePerHour)} / hour</span>
          {/* The stars are the summary; the reviews are the evidence. One tap apart. */}
          <a href="#reviews" className="underline decoration-[var(--line-strong)] underline-offset-4 hover:decoration-[var(--ink)]">
            <Stars value={stars} count={owner.jobsDone} />
          </a>
        </div>
      </header>

      {mine && (
        <div className="mt-6">
          <Banner
            tone="warn"
            title="This is your listing"
            body="You are seeing it the way a buyer would. Manage availability from the Earn tab."
            action={
              <Button size="sm" variant="secondary" onClick={() => nav('/earn')}>
                Go to Earn
              </Button>
            }
          />
        </div>
      )}

      {/* ---------------------------------------------------------- the host */}
      <Card className="mt-7 p-5">
        <div className="flex items-center gap-4">
          <Avatar initials={owner.initials} size={48} business={owner.kind === 'business'} />
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-[16px] font-semibold">
              <span className="truncate">{owner.name}</span>
              {owner.verified && (
                <Icon name="shield" size={15} className="shrink-0 text-[var(--success)]" />
              )}
            </p>
            <p className="t-sm text-[var(--ink-3)]">
              {trackRecord(owner)} · since {owner.joinedYear}
            </p>
          </div>
        </div>
        <p className="t-sm mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
          <Icon name="clock" size={14} className="text-[var(--ink-4)]" />
          {responseTime(owner.responseMins)}
        </p>
      </Card>

      {/* ------------------------------------------------------- capacity */}
      <SectionHead title="Idle time this week" className="mt-7" />
      <Card className="p-5">
        <CapacityBar slots={slots} booked={selected} intent="buy" showLegend />
      </Card>

      {/* --------------------------------------------------------- amount */}
      <SectionHead
        title={isWindow(listing) ? 'How long do you need it?' : `How many ${meta.unitNoun}?`}
        className="mt-7"
      />
      <div className="flex flex-wrap gap-2">
        {isWindow(listing)
          ? (meta.quickHours ?? [1, 2, 4])
              .filter((h) => h >= listing.minHours && h <= listing.maxHours)
              .map((h) => (
                <Chip
                  key={h}
                  selected={hours === h}
                  onClick={() => {
                    setHours(h)
                    setPicked(null)
                  }}
                >
                  {durationLabel(h)}
                </Chip>
              ))
          : QUANTITY_STEPS.map((q) => (
              <Chip
                key={q}
                selected={quantity === q}
                onClick={() => {
                  setQuantity(q)
                  setPicked(null)
                }}
              >
                {q}
              </Chip>
            ))}
      </div>
      {!isWindow(listing) && needed !== null && (
        <p className="t-sm mt-3 text-[var(--ink-4)]">
          {quantity} {meta.unitNoun} is about {durationLabel(needed)} on this machine, including{' '}
          {durationLabel(listing.setupHours)} of setup.
        </p>
      )}

      {/* ----------------------------------------------------- start time */}
      <SectionHead title="Pick a start" className="mt-7" />
      {offers.length === 0 ? (
        <Card className="p-1">
          <EmptyState
            icon="calendar"
            title="Nothing free that long"
            body={
              isWindow(listing)
                ? `${owner.name.split(' ')[0]} has no ${durationLabel(hours)} gap in the next four weeks. A shorter booking may fit.`
                : `${quantity} ${meta.unitNoun} needs ${needed ? durationLabel(needed) : 'more time'} and no gap that long is open. Try a smaller batch.`
            }
            action={
              <Button
                variant="secondary"
                onClick={() =>
                  isWindow(listing)
                    ? setHours(listing.minHours)
                    : setQuantity(Math.max(10, Math.round(quantity / 4)))
                }
              >
                {isWindow(listing)
                  ? `Try ${durationLabel(listing.minHours)}`
                  : `Try ${Math.max(10, Math.round(quantity / 4))} ${meta.unitNoun}`}
              </Button>
            }
          />
        </Card>
      ) : (
        (() => {
          // Day first, then time. Every half-hour of every free day as its own
          // button was thirty-odd choices before anyone could press Request. A
          // day is one tap and already lands on its earliest start, so the
          // common case (soonest, whatever day suits) is a single decision.
          const days = Object.entries(byDay).slice(0, 7)
          const active =
            dayPick ?? (selected ? day(selected.start) : days[0]?.[0]) ?? days[0]?.[0]
          const times = byDay[active] ?? []
          return (
            <div>
              <div className="rail pb-1 md:m-0 md:flex-wrap md:p-0">
                {days.map(([label, group]) => (
                  <Chip
                    key={label}
                    selected={label === active}
                    onClick={() => {
                      setDayPick(label)
                      setPicked(group[0])
                    }}
                  >
                    <span className="capitalize">{label}</span>
                  </Chip>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {times.slice(0, 12).map((o) => (
                  <Chip
                    key={o.start}
                    selected={selected?.start === o.start}
                    onClick={() => setPicked(o)}
                    ariaLabel={`Start ${range(o.start, o.end)}`}
                  >
                    <span className="tnum">{time(o.start)}</span>
                  </Chip>
                ))}
              </div>
            </div>
          )
        })()
      )}

      {/* ---------------------------------------------------------- price */}
      {quote && selected && (
        <>
          <SectionHead title="Price" className="mt-7" />
          <Card className="p-5">
            <Row
              label={`${formatEur(listing.ratePerHour)}/h × ${durationLabel(quote.hours)}`}
              value={formatEurExact(quote.base)}
            />
            {quote.extra > 0 && <Row label={quote.extraLabel} value={formatEurExact(quote.extra)} />}
            <div className="my-2 border-t border-[var(--line)]" />
            <Row label="Total" value={formatEurExact(quote.total)} strong />
            <p className="t-sm mt-3 border-t border-[var(--line)] pt-3 text-[var(--ink-4)]">
              Includes the {PLATFORM_FEE_BPS / 100}% Cappy fee of{' '}
              {formatEurExact(quote.platformFee)}. {owner.name.split(' ')[0]} receives{' '}
              {formatEurExact(quote.ownerNet)}. You settle directly. Cappy does not take card
              details yet.
            </p>
          </Card>
        </>
      )}

      {/* ---------------------------------------------------- house rules */}
      {/* ---------------------------------------------------------- reviews */}
      <section id="reviews">
        <SectionHead title="What people say" className="mt-7" />
        <Reviews reviews={reviewsFor(listing.id)} ownerFirstName={owner.name.split(' ')[0]} />
      </section>

      <SectionHead title="House rules" className="mt-7" />
      <Card className="p-5">
        <ul className="space-y-3">
          {listing.rules.map((r) => (
            <li key={r} className="flex gap-3 text-[15px] text-[var(--ink-2)]">
              <Icon
                name="check"
                size={16}
                className="mt-[4px] shrink-0 text-[var(--success)]"
                strokeWidth={2.4}
              />
              {r}
            </li>
          ))}
        </ul>
      </Card>

      <Sheet
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Confirm request"
        footer={
          <div className="space-y-2">
            <Button block size="lg" onClick={book}>
              Send request to {owner.name.split(' ')[0]}
            </Button>
            <Button block variant="quiet" onClick={() => setConfirming(false)}>
              Not yet
            </Button>
          </div>
        }
      >
        {selected && quote && (
          <div className="space-y-4 pb-2">
            <div className="flex items-center gap-3.5">
              <Plate
                slots={slots}
                categoryId={listing.category}
                aspect={1}
                detail="thumb"
                className="w-[52px] shrink-0 rounded-[14px]"
              />
              <div className="min-w-0">
                <p className="truncate text-[15.5px] font-semibold">{listing.title}</p>
                <p className="t-sm truncate text-[var(--ink-3)]">{owner.name}</p>
              </div>
            </div>

            <Card className="bg-[var(--sunken)] p-5 shadow-none">
              <Row label="When" value={range(selected.start, selected.end)} />
              <Row
                label={isWindow(listing) ? 'Duration' : 'Batch'}
                value={
                  isWindow(listing)
                    ? durationLabel(quote.hours)
                    : `${quantity} ${meta.unitNoun}`
                }
              />
              <Row label="Where" value={`${listing.district} · ${distance(km)}`} />
              <div className="my-2 border-t border-[var(--line)]" />
              <Row label="You pay" value={formatEurExact(quote.total)} strong />
              <Row
                label={`${owner.name.split(' ')[0]} receives`}
                value={formatEurExact(quote.ownerNet)}
                tone="accent"
              />
            </Card>

            <Banner
              tone="warn"
              title="Nothing is charged yet"
              body={`${owner.name.split(' ')[0]} has to accept first, usually within ${owner.responseMins} minutes. You settle payment directly with them.`}
            />
          </div>
        )}
      </Sheet>
    </Screen>
  )
}
