import { lazy, Suspense, useMemo, useState, useEffect } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { NotFound } from './NotFound.tsx'
import { useQueryClient } from '@tanstack/react-query'
import type { Offer, Requirement } from '../../domain/types.ts'
import { isWindow, rating } from '../../domain/types.ts'
import { category, durationLabel } from '../../domain/categories.ts'
import { distanceKm, trackRecord } from '../../domain/match.ts'
import { PLATFORM_FEE_BPS } from '../../domain/pricing.ts'
import { formatMoney } from '../../domain/money.ts'
import {
  useAttemptKey,
  ApiError,
  getIdentity,
  requestBooking,
  startIdentity,
  useDistricts,
  useListing,
  useOffers,
  useFlag,
  usePaymentsConfig,
  useQuote,
  useReviews,
  type BookingCreated,
} from '../../data/repo.ts'
import { messageOf, useCappy, useMe, useToast } from '../store.tsx'
import { Screen, SectionHead } from '../components/AppShell.tsx'
import { CapacityBar } from '../components/CapacityBar.tsx'
import { WhenBadge } from '../components/Cover.tsx'
import { Photo, SaveButton } from '../components/Photo.tsx'
import { Reviews } from '../components/Reviews.tsx'
import { BlockButton, ReportButton } from '../components/Report.tsx'
import { TraderNote } from '../components/BusinessFields.tsx'
import { askForPush } from '../components/PushPrime.tsx'
import { Icon } from '../components/Icon.tsx'
import {
  Avatar,
  Banner,
  Button,
  Card,
  Check,
  Chip,
  EmptyState,
  Row,
  Sheet,
  oneDecimal,
  Stars,
} from '../components/ui.tsx'
import { cancelRate, day, formatDistance, policyInForce, policyName, policyText, range, relative, responseTime, time } from '../format.ts'
import { useOnline } from '../components/Offline.tsx'
import { locale, t } from '../../i18n.ts'

/** Stripe's card form, fetched only when a payment starts (S-15, V3-1). */
const PayStep = lazy(() => import('../components/PayStep.tsx').then((m) => ({ default: m.PayStep })))

const QUANTITY_STEPS = [10, 25, 50, 100, 250, 500, 1000]

export function Listing() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const nav = useNavigate()
  const qc = useQueryClient()
  const { state } = useCappy()
  const toast = useToast()
  const ME = useMe()
  const detail = useListing(id)
  const districts = useDistricts()
  const reviews = useReviews(id)
  const payments = usePaymentsConfig()
  const paidPolicies = useFlag('paidCancellationPolicies')

  const listing = detail.data?.listing
  const cur = listing?.currency
  const owner = detail.data?.owner

  const [hours, setHours] = useState(0)
  const [quantity, setQuantity] = useState(Number(params.get('quantity')) || state.search.quantity)
  // The listing arrives after the first render. Adopt a sensible duration once it
  // is there: the one they had picked before signing in, else their search's.
  const wanted = Number(params.get('hours')) || state.search.hours
  useEffect(() => {
    if (listing && isWindow(listing) && hours === 0) {
      setHours(Math.min(listing.maxHours, Math.max(listing.minHours, wanted)))
    }
  }, [listing, hours, wanted])
  const [picked, setPicked] = useState<Offer | null>(null)
  const [dayPick, setDayPick] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const online = useOnline()
  const [sending, setSending] = useState(false)
  // One key per attempt (FL-1): a retry after a 5xx or a lost connection is the
  // same booking; another slot, a success or a definite no makes a new one.
  const attempt = useAttemptKey()
  const [paying, setPaying] = useState<BookingCreated | null>(null)
  // A 'verification_required' booking: the one-time ID check, then the booking again.
  const [verifying, setVerifying] = useState<'ask' | 'busy' | null>(null)
  // P-18: the ID check is biometric data; it starts only after an explicit yes.
  const [idConsent, setIdConsent] = useState(false)

  // To the minute, so the quote's query key does not change every render.
  const now = useMemo(() => new Date(Math.floor(Date.now() / 60_000) * 60_000), [])
  const slots = detail.data?.slots ?? []

  // Distances are measured from wherever this person searches from.
  const origin = state.search.district
  const requirement: Requirement | null = useMemo(() => {
    if (!listing || (isWindow(listing) && hours === 0)) return null
    const until = new Date(now.getTime() + 28 * 86_400_000).toISOString()
    return isWindow(listing)
      ? {
          mode: 'window',
          category: listing.category,
          hours,
          earliest: now.toISOString(),
          latest: until,
          district: origin,
          maxDistanceKm: 500,
        }
      : {
          mode: 'batch',
          category: listing.category,
          quantity,
          deadline: until,
          district: origin,
          maxDistanceKm: 500,
        }
  }, [listing, hours, quantity, now, origin])

  // The server prices it and says how many hours it takes; offers are the starts
  // that fit that many hours around what is already booked.
  const quoted = useQuote(listing?.id, requirement)
  const quote = quoted.data?.quote ?? null
  const needed = quote?.hours ?? null
  const offersQ = useOffers(listing?.id, needed)
  const offers = needed === null ? [] : (offersQ.data ?? [])

  // Pre-select whatever brought them here: the slot from the results list, else
  // the soonest. Nobody should land on this screen with nothing chosen.
  const selected = useMemo(() => {
    if (picked && offers.some((o) => o.start === picked.start)) return picked
    const start = params.get('start')
    const fromResults = params.get('slot')
    return (
      offers.find((o) => o.start === start) ?? offers.find((o) => o.slotId === fromResults) ?? offers[0] ?? null
    )
  }, [picked, offers, params])

  // A new window is a new attempt: never carry the last one's payment or key over.
  const startOver = () => {
    setPaying(null)
    attempt.settle()
  }
  const selectedStart = selected?.start
  useEffect(startOver, [selectedStart])

  if (detail.isPending) return <Screen back="/">{null}</Screen>
  if (!detail.data || !listing || !owner) return <NotFound what="listing" />
  const info = detail.data
  // The owner's policy only binds once Cappy switches paid policies on (V3-4).
  const policy = policyInForce(listing.cancellationPolicy, paidPolicies)

  const meta = category(listing.category)
  const from = districts.data?.[origin]
  const km = from ? distanceKm(from, info.district) : null
  const stars = rating(owner)
  const mine = owner.id === ME
  const first = owner.name.split(' ')[0]

  const byDay = offers.reduce<Record<string, Offer[]>>((acc, o) => {
    const k = day(o.start)
    ;(acc[k] ??= []).push(o)
    return acc
  }, {})

  // Asking for a window needs a person on the other end of it.
  const request = () => {
    if (!ME) {
      // Back to this exact choice after signing in, not to the defaults.
      const back = `${location.pathname}?hours=${hours}&quantity=${quantity}${selected ? `&start=${encodeURIComponent(selected.start)}` : ''}`
      nav(`/login?next=${encodeURIComponent(back)}`)
      return
    }
    setConfirming(true)
  }

  const sent = (bookingId: string) => {
    toast(listing?.instantBook ? t('Booked') : t('Request sent to {name}', { name: first }))
    askForPush('request')
    void qc.invalidateQueries({ queryKey: ['bookings'] })
    setConfirming(false)
    startOver()
    nav(`/bookings/${bookingId}`, { replace: true })
  }

  const book = async () => {
    if (!requirement || !selected) return
    setSending(true)
    const body = { requirement, listingId: listing.id, slotId: selected.slotId, start: selected.start, end: selected.end }
    try {
      const made = await requestBooking(body, attempt.keyFor(body))
      attempt.settle()
      // With Stripe, the card is authorised here before the owner is asked.
      if (made.payment && payments.data?.provider === 'stripe') setPaying(made)
      else sent(made.booking.id)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'verification_required') {
        // The same attempt (and key) is retried after the ID check.
        setVerifying('ask')
        return
      }
      toast(messageOf(err))
      // Taken by someone else a moment ago: show what is still free.
      if (err instanceof ApiError && err.status === 409) void offersQ.refetch()
      attempt.settle(err)
    } finally {
      setSending(false)
    }
  }

  // Stripe Identity's own modal when the provider is Stripe; the fake provider
  // verifies at once. Either way, the same booking attempt (and key) is retried.
  const verify = async () => {
    setVerifying('busy')
    try {
      let id = await startIdentity()
      if (id.status !== 'verified' && id.clientSecret && payments.data?.publishableKey) {
        const { loadStripe } = await import('@stripe/stripe-js/pure')
        const stripe = await loadStripe(payments.data.publishableKey)
        const res = await stripe?.verifyIdentity(id.clientSecret)
        if (res?.error) throw new Error(res.error.message)
        // The result arrives by webhook: wait for it, for up to a minute.
        for (let i = 0; i < 30 && id.status !== 'verified'; i++) {
          await new Promise((ok) => setTimeout(ok, 2000))
          id = await getIdentity()
        }
      }
      if (id.status !== 'verified') throw new Error(t('Your ID check is still being processed. Try booking again in a few minutes.'))
      setVerifying(null)
      await book()
    } catch (err) {
      toast(messageOf(err))
      setVerifying('ask')
    }
  }

  return (
    <Screen
      back="/"
      docTitle={listing.title}
      hero={
        <Photo
          src={listing.photos?.[0]}
          alt={listing.title}
          slots={slots}
          categoryId={listing.category}
          aspect={16 / 10}
          priority
          className="w-full md:rounded-[var(--radius-sheet)]"
          style={{ viewTransitionName: 'hero' }}
        >
          <span
            className="absolute left-20 right-5 flex items-center justify-end gap-2"
            style={{ top: 'calc(var(--safe-top) + 14px)' }}
          >
            <span className="glass glass-dark min-w-0 truncate rounded-full px-3 py-1 text-[0.75rem] font-semibold">
              {meta.label}
            </span>
            <WhenBadge
              freeNow={Boolean(selected && Date.parse(selected.start) <= Date.now())}
              text={selected ? t('Free {when}', { when: relative(selected.start) }) : t('No window')}
            />
            {!mine && <SaveButton id={listing.id} title={listing.title} className="" />}
          </span>
        </Photo>
      }
      // One row in the phone's bottom bar, a stacked buy box in the page's side
      // panel. Same content, and the panel has the room to label it.
      footer={
        mine ? undefined : (
          // At large text sizes (U-27) the button wraps under the price instead of covering it.
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:block">
            <div className="min-w-[10rem] flex-1">
              <p className="t-label hidden md:block">{t('Your booking')}</p>
              <p className="tnum text-[1.1875rem] font-bold leading-tight md:mt-2 md:text-[1.75rem]">
                {quote ? formatMoney(quote.total, cur) : '—'}
              </p>
              {/* U-20: the total is the whole price; the fee is inside it, never added at the end. */}
              {quote && (
                <p className="tnum truncate text-[0.7812rem] text-[var(--ink-3)]">
                  {t('Total, incl. {fee} service fee', { fee: formatMoney(quote.platformFee, cur) })}
                </p>
              )}
              <p className="t-sm tnum truncate text-[var(--ink-3)] md:mt-1 md:whitespace-normal">
                {selected ? range(selected.start, selected.end) : t('No free window')}
              </p>
              {/* What the price is for, so the button is not a leap. */}
              {quote && (
                <p className="t-sm tnum hidden text-[var(--ink-3)] md:block">
                  {isWindow(listing)
                    ? durationLabel(quote.hours)
                    : `${quantity} ${meta.unitNoun} · ${t('{duration} incl. setup', { duration: durationLabel(quote.hours) })}`}
                </p>
              )}
            </div>
            <Button
              size="lg"
              disabled={!selected || !quote || !online}
              icon={listing.instantBook ? 'bolt' : undefined}
              onClick={request}
              className="md:mt-5 md:w-full"
            >
              {listing.instantBook ? t('Book') : t('Request')}
            </Button>
            {/* The worry in front of any red button is "am I paying now". Nothing
                is charged here, so the box says so, and says who answers and when. */}
            <p className="t-sm mt-3 hidden text-center text-[var(--ink-4)] md:block">
              {listing.instantBook ? (
                t('Instant book: confirmed as soon as your card is held.')
              ) : (
                <>
                  {t('Your card is only held. Nothing is charged until {name} accepts', { name: first })} ·{' '}
                  {responseTime(owner.responseMins).replace(/^./, (c) => c.toLowerCase())}
                </>
              )}
            </p>
          </div>
        )
      }
    >
      {/* ------------------------------------------------------------- title */}
      <header className="-mt-1">
        <h1 className="t-h1 text-balance">{listing.title}</h1>
        <p className="t-lede mt-2.5 text-[var(--ink-3)]">{listing.blurb}</p>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.875rem] text-[var(--ink-3)]">
          <span className="tnum inline-flex items-center gap-1.5">
            <Icon name="pin" size={15} className="text-[var(--ink-4)]" />
            {listing.district}{km !== null ? ` · ${formatDistance(km)}` : ''}
          </span>
          <span className="tnum">{formatMoney(listing.ratePerHour, cur)} / {t('hour')}</span>
          {/* This listing's reviews; the owner's overall record is on their card below. */}
          <a
            href="#reviews"
            aria-label={
              info.reviews.average != null
                ? t('This listing: {avg} from {n} reviews', { avg: oneDecimal(info.reviews.average), n: info.reviews.count })
                : t('No reviews of this listing yet')
            }
            className="underline decoration-[var(--line-strong)] underline-offset-4 hover:decoration-[var(--ink)]"
          >
            <Stars value={info.reviews.average} count={info.reviews.count} />
          </a>
          {listing.instantBook && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--sunken)] px-2.5 py-0.5 text-[0.8125rem] font-semibold text-[var(--ink-2)]">
              <Icon name="bolt" size={13} />
              {t('Instant book')}
            </span>
          )}
        </div>
      </header>

      {mine && (
        <div className="mt-6">
          <Banner
            tone="warn"
            title={t('This is your listing')}
            body={t('You are seeing it the way a buyer would. Manage availability from the Earn tab.')}
            action={
              <Button size="sm" variant="secondary" to={'/earn'}>
                {t('Go to Earn')}
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
            <p className="flex items-center gap-1.5 text-[1rem] font-semibold">
              <span className="truncate">{owner.name}</span>
              {owner.verified && (
                <Icon name="shield" size={15} className="shrink-0 text-[var(--success)]" />
              )}
            </p>
            <p className="t-sm text-[var(--ink-3)]">
              {trackRecord(owner)} · {t('since {year}', { year: owner.joinedYear })}
            </p>
            {cancelRate(owner.cancellationRate) && (
              <p className="t-sm text-[var(--warn)]">{cancelRate(owner.cancellationRate)}</p>
            )}
          </div>
          {/* The owner across all their listings, labelled so it is not read as this listing's. */}
          <span className="shrink-0 text-right">
            <Stars value={stars} count={owner.jobsDone} />
            <span className="t-sm block text-[var(--ink-4)]">{t('all their jobs')}</span>
          </span>
        </div>
        <p className="t-sm mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
          <Icon name="clock" size={14} className="text-[var(--ink-4)]" />
          {responseTime(owner.responseMins)}
        </p>
        {/* EU consumer law: say whether you are dealing with a business. */}
        <p className="t-sm mt-2 flex items-start gap-1.5 text-[var(--ink-3)]">
          <Icon name="info" size={14} className="mt-[3px] shrink-0 text-[var(--ink-4)]" />
          {owner.kind === 'business'
            ? t('Business. EU consumer rights apply to your booking.')
            : t('Private person, not a business. EU consumer rights toward businesses do not apply; Cappy’s terms and payment protection do.')}
        </p>
        {owner.business && (
          <div className="mt-3">
            <TraderNote business={owner.business} />
          </div>
        )}
        <div className="mt-3 flex flex-wrap gap-1 border-t border-[var(--line)] pt-3">
          <ReportButton targetType="owner" targetId={owner.id} />
          {ME && ME !== owner.id && <BlockButton sub={owner.id} name={first} />}
        </div>
      </Card>

      {/* ------------------------------------------------------- capacity */}
      <SectionHead title={t('Idle time this week')} className="mt-7" />
      <Card className="p-5">
        <CapacityBar slots={slots} booked={selected} intent="buy" showLegend />
      </Card>

      {/* --------------------------------------------------------- amount */}
      <SectionHead
        title={isWindow(listing) ? t('How long do you need it?') : t('How many {unit}?', { unit: meta.unitNoun ?? '' })}
        className="mt-7"
      />
      <div className="flex flex-wrap gap-2">
        {isWindow(listing)
          ? [...new Set([listing.minHours, ...(meta.quickHours ?? [1, 2, 4])])]
              .filter((h) => h >= listing.minHours && h <= listing.maxHours)
              .sort((a, b) => a - b)
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
          {t('{n} {unit} is about {duration} on this machine, including {setup} of setup.', { n: quantity, unit: meta.unitNoun ?? '', duration: durationLabel(needed), setup: durationLabel(listing.setupHours) })}
        </p>
      )}

      {/* ----------------------------------------------------- start time */}
      <SectionHead title={t('Pick a start')} className="mt-7" />
      {offers.length === 0 ? (
        <Card className="p-1">
          <EmptyState
            icon="calendar"
            title={t('Nothing free that long')}
            body={
              isWindow(listing)
                ? t('{name} has no {duration} gap in the next four weeks. A shorter booking may fit.', { name: first, duration: durationLabel(hours) })
                : t('{n} {unit} needs {duration} and no gap that long is open. Try a smaller batch.', { n: quantity, unit: meta.unitNoun ?? '', duration: needed ? durationLabel(needed) : t('more time') })
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
                  ? t('Try {what}', { what: durationLabel(listing.minHours) })
                  : t('Try {what}', { what: `${Math.max(10, Math.round(quantity / 4))} ${meta.unitNoun}` })}
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
                    ariaLabel={t('Start {when}', { when: range(o.start, o.end) })}
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
          <SectionHead title={t('Price')} className="mt-7" />
          <Card className="p-5">
            <Row
              label={`${formatMoney(listing.ratePerHour, cur)}/h × ${durationLabel(quote.hours)}`}
              value={formatMoney(quote.base, cur)}
            />
            {quote.extra > 0 && <Row label={quote.extraLabel} value={formatMoney(quote.extra, cur)} />}
            <div className="my-2 border-t border-[var(--line)]" />
            {(quote.discount ?? 0) > 0 && (
              <Row
                label={quote.discountLabel ?? t('Discount')}
                value={`−${formatMoney(quote.discount ?? 0, cur)}`}
                tone="accent"
              />
            )}
            <Row label={t('Total')} value={formatMoney(quote.total, cur)} strong />
            <p className="t-sm mt-3 border-t border-[var(--line)] pt-3 text-[var(--ink-4)]">
              {t(
                listing.instantBook
                  ? 'Includes the {pct} % Cappy fee of {fee}. {name} receives {net}. Instant book: paid by card when you book, confirmed at once.'
                  : 'Includes the {pct} % Cappy fee of {fee}. {name} receives {net}. Paid by card when {name} accepts; if they decline, the hold is released.',
                {
                  pct: (PLATFORM_FEE_BPS / 100).toLocaleString(locale()),
                  fee: formatMoney(quote.platformFee, cur),
                  net: formatMoney(quote.ownerNet, cur),
                  name: first,
                },
              )}
            </p>
          </Card>
        </>
      )}

      <SectionHead title={t('Cancellation')} className="mt-7" />
      <Card className="p-5">
        <p className="text-[0.9375rem] font-semibold">{policyName(policy)}</p>
        <p className="t-sm mt-1 text-[var(--ink-3)]">
          {policyText(policy)} {t('If the owner cancels, you get everything back.')}
        </p>
      </Card>

      {/* ---------------------------------------------------- house rules */}
      {/* ---------------------------------------------------------- reviews */}
      <section id="reviews">
        <SectionHead title={t('What people say')} className="mt-7" />
        <Reviews reviews={reviews.data?.items ?? []} summary={info.reviews} ownerFirstName={first} ownerJobs={owner.jobsDone} />
      </section>

      <SectionHead title={t('House rules')} className="mt-7" />
      <Card className="p-5">
        <ul className="space-y-3">
          {listing.rules.map((r) => (
            <li key={r} className="flex gap-3 text-[0.9375rem] text-[var(--ink-2)]">
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

      <div className="mt-4 flex justify-end">
        <ReportButton targetType="listing" targetId={listing.id} />
      </div>

      <Sheet
        open={confirming}
        onClose={() => {
          setConfirming(false)
          // The booking made so far can still be paid from its own page.
          startOver()
        }}
        title={
          listing.instantBook
            ? paying
              ? t('Pay to book')
              : t('Confirm booking')
            : paying
              ? t('Pay to send your request')
              : t('Confirm request')
        }
        footer={
          paying ? undefined : (
            <div className="space-y-2">
              <Button block size="lg" disabled={sending || !online} onClick={() => void book()}>
                {/* The final button must say it commits to paying (§312j BGB). */}
                {sending ? t('Sending…') : t('Book and pay')}
              </Button>
              <Button block variant="quiet" onClick={() => setConfirming(false)}>
                {t('Not yet')}
              </Button>
            </div>
          )
        }
      >
        {paying?.payment && payments.data?.publishableKey ? (
          <Suspense fallback={null}>
            <PayStep
              publishableKey={payments.data.publishableKey}
              clientSecret={paying.payment.clientSecret}
              bookingId={paying.booking.id}
              onPaid={() => sent(paying.booking.id)}
            />
          </Suspense>
        ) : selected && quote && (
          <div className="space-y-4 pb-2">
            <div className="flex items-center gap-3.5">
              <Photo
                src={listing.photos?.[0]}
                alt=""
                categoryId={listing.category}
                aspect={1}
                className="w-[52px] shrink-0 rounded-[14px]"
              />
              <div className="min-w-0">
                <p className="truncate text-[0.9688rem] font-semibold">{listing.title}</p>
                <p className="t-sm truncate text-[var(--ink-3)]">{owner.name}</p>
              </div>
            </div>

            <Card className="bg-[var(--sunken)] p-5 shadow-none">
              <Row label={t('When')} value={range(selected.start, selected.end)} />
              <Row
                label={isWindow(listing) ? t('Duration') : t('Batch')}
                value={
                  isWindow(listing)
                    ? durationLabel(quote.hours)
                    : `${quantity} ${meta.unitNoun}`
                }
              />
              <Row label={t('Where')} value={`${listing.district}${km !== null ? ` · ${formatDistance(km)}` : ''}`} />
              <div className="my-2 border-t border-[var(--line)]" />
              <Row label={t('You pay')} value={formatMoney(quote.total, cur)} strong />
              <Row
                label={t('{name} receives', { name: first })}
                value={formatMoney(quote.ownerNet, cur)}
                tone="accent"
              />
            </Card>

            {listing.instantBook ? (
              <Banner
                tone="warn"
                title={t('Instant book')}
                body={t('Confirmed as soon as your card is held; {name} does not need to accept first.', { name: first })}
              />
            ) : (
              <Banner
                tone="warn"
                title={t('Nothing is charged yet')}
                body={t('Your card is held for the total. {name} has to accept first, usually within {n} minutes; if they decline or do not answer, the hold is released.', { name: first, n: owner.responseMins })}
              />
            )}
            <p className="t-sm text-[var(--ink-3)]">
              {t('Cancellation')}: {policyText(policy)}
            </p>
            <TraderNote business={owner.business} />
          </div>
        )}
      </Sheet>

      <Sheet
        open={verifying !== null}
        onClose={() => setVerifying(null)}
        title={t('Check your ID once')}
        footer={
          <div className="space-y-2">
            <Button block size="lg" disabled={verifying === 'busy' || !idConsent} onClick={() => void verify()}>
              {verifying === 'busy' ? t('Checking…') : t('Check my ID')}
            </Button>
            <Button block variant="quiet" onClick={() => setVerifying(null)}>
              {t('Not yet')}
            </Button>
          </div>
        }
      >
        <p className="pb-2 text-[0.9375rem] text-[var(--ink-2)]">
          {t('This booking needs a one-time ID check. You photograph an ID document and your face; it takes about two minutes and is never needed again. Your booking is sent as soon as it is done.')}
        </p>
        <div className="pb-3">
          <Check
            checked={idConsent}
            onChange={setIdConsent}
            label={t('I agree to the ID check')}
            hint={
              <>
                {t('Stripe, our payment provider, checks a photo of your ID document against a selfie on Cappy’s behalf. You can refuse; then this booking cannot go ahead.')}{' '}
                <a className="underline" href="/legal/privacy">
                  {t('Privacy Policy')}
                </a>
              </>
            }
          />
        </div>
      </Sheet>
    </Screen>
  )
}
