import { lazy, Suspense, useMemo, useRef, useState, useEffect, type ReactNode } from 'react'
import { useNav } from '../nav.ts'
import { useParams, useSearchParams } from 'react-router-dom'
import { NotFound } from './NotFound.tsx'
import { useQueryClient } from '@tanstack/react-query'
import type { Offer, Requirement, Review } from '../../domain/types.ts'
import { isWindow, rating } from '../../domain/types.ts'
import { category, durationLabel } from '../../domain/categories.ts'
import { distanceKm, trackRecord } from '../../domain/match.ts'
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
  useGlobalFlag,
  usePaymentsConfig,
  useQuote,
  useReviews,
  type BookingCreated,
  type ListingDetail,
} from '../../data/repo.ts'
import { messageOf, useCappy, useMe, useToast } from '../store.tsx'
import { Screen, SectionHead, useLargeText } from '../components/AppShell.tsx'
import { CapacityBar } from '../components/CapacityBar.tsx'
import { WhenBadge } from '../components/Cover.tsx'
import { Photo, SaveButton, WhenChip } from '../components/Photo.tsx'
import { Odometer } from '../components/Odometer.tsx'
import { Reviews } from '../components/Reviews.tsx'
import { BlockButton, ReportButton } from '../components/Report.tsx'
import { TraderNote } from '../components/BusinessFields.tsx'
import { PriceSummary, type PriceLines } from '../components/PriceSummary.tsx'
import { Gallery } from '../components/Gallery.tsx'
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
  DetailSkeleton,
} from '../components/ui.tsx'
import { cancelRate, day, formatDistance, policyInForce, policyLine, policyName, policyText, range, relative, responseRate, responseTime, time } from '../format.ts'
import { useOnline } from '../components/Offline.tsx'
import { locale, t } from '../../i18n.ts'

/** Stripe's card form, fetched only when a payment starts (S-15, V3-1). */
const PayStep = lazy(() => import('../components/PayStep.tsx').then((m) => ({ default: m.PayStep })))

const QUANTITY_STEPS = [10, 25, 50, 100, 250, 500, 1000]

/** The listing page. With `preview`, a read-only staff view of a listing the
 *  public cannot see (held, hidden, taken down): no booking, a banner on top. */
export function Listing({ preview }: { preview?: { detail: ListingDetail; banner: ReactNode; address?: string; reviews?: Review[]; bookable: boolean } } = {}) {
  const { id } = useParams()
  const [params] = useSearchParams()
  const nav = useNav()
  const big = useLargeText()
  const qc = useQueryClient()
  const { state } = useCappy()
  const toast = useToast()
  const ME = useMe()
  const fetched = useListing(preview ? undefined : id)
  const detail = preview ? { data: preview.detail, isPending: false } : fetched
  const districts = useDistricts()
  // A staff preview asks staff's own endpoints (held listings included) and gets
  // the reviews with the listing (V6-2).
  const memberReviews = useReviews(preview ? undefined : id)
  const reviews = preview ? { data: { items: preview.reviews ?? [] } } : memberReviews
  const payments = usePaymentsConfig()
  const paidPolicies = useGlobalFlag('paidCancellationPolicies')

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

  // The largest batch the longest free window can hold (V4-14). A suggestion
  // of a quarter of the batch ("Try 13 pallets") was often still too big.
  // ponytail: from window lengths, not bookings inside them; the offers the
  // server returns for the new quantity are the final word.
  const maxFit = useMemo(() => {
    if (!listing || isWindow(listing)) return null
    const room = Math.max(0, ...slots.map((s) => s.hoursUsable)) - listing.setupHours
    return room > 0 ? Math.floor(room * listing.unitsPerHour) : 0
  }, [listing, slots])
  // Open on a batch that fits, when the search asked for more than any window holds.
  const fitted = useRef(false)
  useEffect(() => {
    if (fitted.current || maxFit === null || !detail.data) return
    fitted.current = true
    if (maxFit > 0 && quantity > maxFit && !params.get('quantity')) setQuantity(maxFit)
    // Never above what the owner takes per booking (V5-22).
    const most = detail.data.listing.mode === 'batch' ? detail.data.listing.maxQuantity : undefined
    if (most && quantity > most) setQuantity(most)
  }, [maxFit, detail.data, quantity, params])

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
  const quoted = useQuote(preview && !preview.bookable ? undefined : listing?.id, requirement, Boolean(preview))
  const quote = quoted.data?.quote ?? null
  // One set of lines for the price card and the confirm sheet (UX-23).
  const priceLines: PriceLines | null = quote && detail.data
    ? {
        base: {
          label: `${formatMoney(detail.data.listing.ratePerHour, quote.currency ?? detail.data.listing.currency)}/h × ${durationLabel(quote.hours)}`,
          amount: quote.base,
        },
        // The server's label (freight: "Loading"), in the reader's language (V5-18, V5-22).
        extra: quote.extra > 0 ? { label: t(quote.extraLabel), amount: quote.extra } : undefined,
        discount: (quote.discount ?? 0) > 0 ? { label: quote.discountLabel ?? t('Discount'), amount: quote.discount ?? 0 } : undefined,
        fee: quote.platformFee,
        total: quote.total,
      }
    : null
  const needed = quote?.hours ?? null
  const offersQ = useOffers(preview && !preview.bookable ? undefined : listing?.id, needed, Boolean(preview))
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

  const heroStart = selected?.start ?? slots.find((sl) => Date.parse(sl.start) > Date.now())?.start

  if (detail.isPending) return <Screen back="/"><DetailSkeleton /></Screen>
  if (!detail.data || !listing || !owner) return <NotFound what="listing" />
  const info = detail.data
  // The owner's policy only binds once Cappy switches paid policies on (V3-4).
  const policy = policyInForce(listing.cancellationPolicy, paidPolicies)

  const meta = category(listing.category)
  const from = districts.data?.[origin]
  const km = from ? distanceKm(from, info.district) : null
  const stars = rating(owner)
  // Staff previewing get the owner's read-only view: nothing to book (V5-4).
  const mine = owner.id === ME || Boolean(preview)
  // A business goes by its whole name: "Eindhoven Additive BV", not "Eindhoven" (V7-26).
  const first = owner.kind === 'business' ? owner.name : owner.name.split(' ')[0]
  // Instant book has no "owner accepts" moment: the address comes with the confirmation (V5-21).
  const addressNote = listing.instantBook
    ? t('Approximate area. The exact address is shared once the booking is confirmed.')
    : t('Approximate area. The exact address is shared once the owner accepts.')
  // Batch sizes this listing can take (V5-22): never more than the longest free
  // window holds, and always the size already picked.
  const cap = !isWindow(listing) ? listing.maxQuantity : undefined
  const room = Math.min(maxFit ?? Infinity, cap ?? Infinity)
  const quantities = [...new Set([1, ...QUANTITY_STEPS.filter((q) => q <= room), ...(Number.isFinite(room) && room > 0 ? [room] : []), Math.min(quantity, room)])]
    .filter((q) => q > 0)
    .sort((a, b) => a - b)
  const freight = listing.category === 'freight'

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
    // The ticket on the booking says it now (VD-15), not a toast.
    askForPush('request')
    void qc.invalidateQueries({ queryKey: ['bookings'] })
    setConfirming(false)
    startOver()
    nav(`/bookings/${bookingId}`, { replace: true, state: { fresh: true } })
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
      toast(messageOf(err), 'error')
      // Taken by someone else a moment ago: show what is still free.
      if (err instanceof ApiError && err.status === 409) void offersQ.refetch()
      attempt.settle(err)
    } finally {
      setSending(false)
    }
  }

  // Whoever runs the check (F-1, `identityProvider`): Stripe's own modal, a
  // hosted page the session names (`url`), or nothing to do (the fake provider
  // verifies at once). Either way, the same booking attempt (and key) is retried.
  const verify = async () => {
    setVerifying('busy')
    try {
      let id = await startIdentity()
      let started = false
      if (id.status !== 'verified' && id.url) {
        window.open(id.url, '_blank', 'noopener')
        started = true
      } else if (id.status !== 'verified' && id.clientSecret && payments.data?.publishableKey && (payments.data.identityProvider ?? 'stripe') === 'stripe') {
        const { loadStripe } = await import('@stripe/stripe-js/pure')
        const stripe = await loadStripe(payments.data.publishableKey)
        const res = await stripe?.verifyIdentity(id.clientSecret)
        if (res?.error) throw new Error(res.error.message)
        started = true
      }
      // The result arrives by webhook: wait for it, for up to a minute (two for a hosted page).
      for (let i = 0; started && i < (id.url ? 60 : 30) && id.status !== 'verified' && id.status !== 'failed'; i++) {
        await new Promise((ok) => setTimeout(ok, 2000))
        id = await getIdentity()
      }
      if (id.status === 'failed') throw new Error(t('The ID check did not go through. Try again with a valid ID document.'))
      if (id.status !== 'verified') throw new Error(t('Your ID check is still being processed. Try booking again in a few minutes.'))
      setVerifying(null)
      await book()
    } catch (err) {
      toast(messageOf(err), 'error')
      setVerifying('ask')
    }
  }

  return (
    <Screen
      back={preview ? '/admin' : '/'}
      docTitle={listing.title}
      wash={detail.data.photoMeta?.[0]?.color ?? undefined}
      hero={
        <Gallery
          photos={listing.photos ?? []}
          meta={detail.data.photoMeta}
          title={listing.title}
          slots={slots}
          categoryId={listing.category}
          style={{ viewTransitionName: 'hero' }}
          overlay={
          <>
          <span
            // One row that never wraps into the photo counter (J-12): the chip's
            // own text wraps inside it instead.
            className="absolute left-20 right-4 flex items-start justify-end gap-2"
            style={{ top: 'calc(var(--safe-top) + 12px)' }}
          >
            <span className="glass-media-text min-w-0 rounded-[var(--radius-l)] px-3 py-1.5 text-center text-label font-semibold">
              {meta.label}
            </span>
            <WhenBadge
              freeNow={Boolean(selected && Date.parse(selected.start) <= Date.now())}
              text={selected ? t('Free {when}', { when: relative(selected.start) }) : t('No window')}
            />
            {!mine && <SaveButton id={listing.id} title={listing.title} className="" />}
          </span>
          {/* The hour tag the card showed, in the same corner (VD-16): the card's
              tag travels here. The slot stands in until the offers arrive. */}
          {heroStart && <WhenChip start={heroStart} className="[view-transition-name:hour]" />}
          </>
          }
        />
      }
      // One row in the phone's bottom bar, a stacked buy box in the page's side
      // panel. Same content, and the panel has the room to label it.
      footer={
        mine ? undefined : (
          // At large text sizes (U-27) the button wraps under the price instead of covering it.
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:block">
            <div className={`flex-1 ${big ? 'basis-full' : 'min-w-[min(10rem,100%)]'}`}>
              <p className="t-label hidden md:block">{t('Your booking')}</p>
              {/* On a desktop the box itself carries the choice (UX-20): Day,
                  Start, Duration as native selects, the same state as the chips. */}
              {isWindow(listing) && Object.keys(byDay).length > 0 && (
                <div className="mt-3 hidden gap-2 md:grid md:grid-cols-2">
                  <label className="t-label col-span-2 block">
                    {t('Day')}
                    <select
                      className="mt-1 min-h-[44px] w-full rounded-[var(--radius-control)] border border-[var(--line)] bg-transparent px-3 text-body text-[var(--ink)]"
                      value={selected ? day(selected.start) : ''}
                      onChange={(e) => {
                        setDayPick(e.target.value)
                        setPicked(byDay[e.target.value]?.[0] ?? null)
                      }}
                    >
                      {Object.keys(byDay).slice(0, 14).map((d) => (
                        <option key={d} value={d}>
                          {/* A list entry starts with a capital, as the chips do (V9-18). */}
                          {d.charAt(0).toLocaleUpperCase(locale()) + d.slice(1)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="t-label block">
                    {t('Starts')}
                    <select
                      className="mt-1 tnum min-h-[44px] w-full rounded-[var(--radius-control)] border border-[var(--line)] bg-transparent px-3 text-body text-[var(--ink)]"
                      value={selected?.start ?? ''}
                      onChange={(e) => setPicked(offers.find((o) => o.start === e.target.value) ?? null)}
                    >
                      {(selected ? byDay[day(selected.start)] ?? [] : []).map((o) => (
                        <option key={o.start} value={o.start}>
                          {time(o.start)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="t-label block">
                    {t('Duration')}
                    <select
                      className="mt-1 min-h-[44px] w-full rounded-[var(--radius-control)] border border-[var(--line)] bg-transparent px-3 text-body text-[var(--ink)]"
                      value={hours}
                      onChange={(e) => {
                        setHours(Number(e.target.value))
                        setPicked(null)
                      }}
                    >
                      {Array.from({ length: Math.min(listing.maxHours, 24) - listing.minHours + 1 }, (_, i) => listing.minHours + i).map((h) => (
                        <option key={h} value={h}>
                          {durationLabel(h)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              )}
              <p className="tnum text-title-s font-bold leading-tight md:mt-2 md:text-title-l">
                {quote ? <Odometer value={formatMoney(quote.total, cur)} /> : '—'}
              </p>
              {/* U-20: the total is the whole price; the fee is inside it, never added at the end. */}
              {quote && (
                <p className="tnum [overflow-wrap:anywhere] text-label text-[var(--ink-3)]">
                  {t('Total, incl. {fee} service fee', { fee: formatMoney(quote.platformFee, cur) })}
                </p>
              )}
              {/* Wraps rather than truncates: the end time is half the answer (V4-11). */}
              <p className="t-sm tnum text-[var(--ink-3)] md:mt-1">
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
              // At large text the bar stacks: the price above, the button across (J-8).
              className={`md:mt-5 md:w-full ${big ? 'w-full' : ''}`}
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
                  {t('Your card is only held. Nothing is charged until {name} accepts', { name: first })}
                  {responseTime(owner.responseMins) && ` · ${responseTime(owner.responseMins)!.replace(/^./, (c) => c.toLowerCase())}`}
                </>
              )}
            </p>
          </div>
        )
      }
    >
      {/* ------------------------------------------------------------- title */}
      <header className="-mt-1">
        <h1 className="t-title-user text-balance">{listing.title}</h1>
        <p className="t-lede mt-2.5 text-[var(--ink-3)]">{listing.blurb}</p>
        {/* The price as the one hero figure on the screen (VD-9). */}
        <p className="mt-5 flex flex-wrap items-baseline gap-x-2">
          <span className="t-figure-hero">{formatMoney(listing.ratePerHour, cur)}</span>
          <span className="text-body text-[var(--ink-3)]">/ {t('hour')}</span>
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-body text-[var(--ink-3)]">
          {/* Approximate for everyone but the owner (M-6): the exact place comes with the booking. */}
          <span className="tnum inline-flex items-center gap-1.5" title={mine ? undefined : addressNote}>
            <Icon name="pin" size={15} className="text-[var(--ink-4)]" />
            {listing.district}{km !== null ? ` · ${formatDistance(km)}` : ''}
            {!mine && <span className="sr-only">{addressNote}</span>}
          </span>
          {/* This listing's reviews; the owner's overall record is on their card below. */}
          <a
            href="#reviews"
            aria-label={
              info.reviews.average != null
                ? t('This listing: {avg} from {n} reviews', { avg: oneDecimal(info.reviews.average), n: info.reviews.count })
                : t('No reviews of this listing yet')
            }
            className="inline-flex min-h-[44px] min-w-[44px] items-center underline decoration-[var(--line-strong)] underline-offset-4 hover:decoration-[var(--ink)]"
          >
            <Stars value={info.reviews.average} count={info.reviews.count} />
          </a>
          {listing.instantBook && (
            <span className="inline-flex items-center gap-1 rounded-full bg-[var(--sunken)] px-2.5 py-0.5 text-label font-semibold text-[var(--ink-2)]">
              <Icon name="bolt" size={13} />
              {t('Instant book')}
            </span>
          )}
        </div>
      </header>

      {preview && <div className="mt-6">{preview.banner}</div>}
      {mine && !preview && (
        <div className="mt-6">
          <Banner
            tone="neutral"
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
            <p className="flex items-center gap-1.5 text-body-l font-semibold">
              {/* Wraps: a name is not cut to "Nadia Bra…" when the rating beside it is long (V4-11). */}
              <span className="min-w-0 break-words">{owner.name}</span>
              {owner.verified && (
                <Icon name="shield" size={15} className="shrink-0 text-[var(--success)]" />
              )}
            </p>
            <p className="t-sm text-[var(--ink-3)]">
              {trackRecord(owner)} · {t('since {year}', { year: owner.joinedYear })}
            </p>
            {/* The owner across all their listings, under the name so a long
                company name keeps the full width (judge c). */}
            {stars != null && (
              <p className="mt-1 flex flex-wrap items-center gap-x-1.5">
                <Stars value={stars} count={owner.jobsDone} />
                <span className="t-sm text-[var(--ink-4)]">{t('all their jobs')}</span>
              </p>
            )}
            {cancelRate(owner.cancellationRate) && (
              <p className="t-sm text-[var(--warn)]">{cancelRate(owner.cancellationRate)}</p>
            )}
          </div>
        </div>
        {/* Measured, never assumed (H-1): nothing is said before 3 requests. */}
        {(responseTime(owner.responseMins) || responseRate(owner.responseRate)) && (
          <p className="t-sm mt-4 flex items-center gap-1.5 border-t border-[var(--line)] pt-4 text-[var(--ink-3)]">
            <Icon name="clock" size={14} className="text-[var(--ink-4)]" />
            {[responseTime(owner.responseMins), responseRate(owner.responseRate)].filter(Boolean).join(' · ')}
          </p>
        )}
        {/* EU consumer law: say whether you are dealing with a business. */}
        <p className="t-sm mt-2 flex items-start gap-1.5 text-[var(--ink-3)]">
          <Icon name="info" size={14} className="mt-[3px] shrink-0 text-[var(--ink-4)]" />
          {owner.kind === 'business'
            ? preview
              ? t('Business. EU consumer rights apply to bookings with it.')
              : t('Business. EU consumer rights apply to your booking.')
            : t('Private person, not a business. EU consumer rights toward businesses do not apply; Cappy’s terms and payment protection do.')}
        </p>
        {owner.business && (
          <div className="mt-3">
            <TraderNote business={owner.business} />
          </div>
        )}
        {!preview && (
          <div className="mt-3 flex flex-wrap gap-1 border-t border-[var(--line)] pt-3">
            <ReportButton targetType="owner" targetId={owner.id} />
            {ME && ME !== owner.id && <BlockButton sub={owner.id} name={first} />}
          </div>
        )}
      </Card>

      {/* ------------------------------------------------------- capacity */}
      <SectionHead title={t('Idle time this week')} className="mt-7" />
      <Card className="p-5">
        {/* Staff see the listing as its owner does: free and sold, not "your booking" (V7-26). */}
        <CapacityBar slots={slots} booked={selected} intent={preview ? 'earn' : 'buy'} showLegend />
      </Card>

      {preview?.address && (
        <>
          <SectionHead title={t('Hand-over address')} className="mt-7" />
          <Card className="p-5">
            <p className="text-body text-[var(--ink-2)]">{preview.address}</p>
          </Card>
        </>
      )}
      {/* A listing nobody can book (hidden, paused, taken down) shows no availability to staff either (V6-2). */}
      {(!preview || preview.bookable) && (
        <>
        {/* --------------------------------------------------------- amount */}
        <SectionHead
          title={preview ? t('Durations it takes') : isWindow(listing) ? t('How long do you need it?') : t('How many {unit}?', { unit: meta.unitNoun ?? '' })}
          className="mt-7"
        />
        <div className="flex flex-wrap gap-2">
          {isWindow(listing)
            ? // The duration being priced is always one of the chips, and selected (V6-3).
              [...new Set([listing.minHours, ...(meta.quickHours ?? [1, 2, 4]), ...(hours ? [hours] : [])])]
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
            : quantities.map((q) => (
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
            {freight
              ? t('{n} {unit} take about {duration}, including {setup} to load.', { n: quantity, unit: meta.unitNoun ?? '', duration: durationLabel(needed), setup: durationLabel(listing.setupHours) })
              : t('{n} {unit} is about {duration} on this machine, including {setup} of setup.', { n: quantity, unit: meta.unitNoun ?? '', duration: durationLabel(needed), setup: durationLabel(listing.setupHours) })}
          </p>
        )}

        {/* ----------------------------------------------------- start time */}
        {/* Staff are not booking: the view names what is there (V8-13). */}
        <SectionHead title={preview ? t('Start times') : t('Pick a start')} className="mt-7" />
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
                isWindow(listing) ? (
                  <Button variant="secondary" onClick={() => setHours(listing.minHours)}>
                    {t('Try {what}', { what: durationLabel(listing.minHours) })}
                  </Button>
                ) : maxFit && maxFit < quantity ? (
                  <Button variant="secondary" onClick={() => setQuantity(maxFit)}>
                    {t('Try {what}', { what: `${maxFit} ${meta.unitNoun}` })}
                  </Button>
                ) : undefined
              }
            />
          </Card>
        ) : (
          (() => {
            // Day first, then time. Every half-hour of every free day as its own
            // button was thirty-odd choices before anyone could press Request. A
            // day is one tap and already lands on its earliest start, so the
            // common case (soonest, whatever day suits) is a single decision.
            // Two weeks of days in the rail, so next weekend can be picked (V6-23).
          const days = Object.entries(byDay).slice(0, 14)
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
                      {/* First letter only: `capitalize` made every word a capital, "Mar. 29 Sept." (V4-21). */}
                      <span className="inline-block first-letter:uppercase">{label}</span>
                    </Chip>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {/* Every start, not the first twelve: 18:00 must be bookable too (V5-9). */}
                  {times.map((o) => (
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
        </>
      )}

      {/* ---------------------------------------------------------- price */}
      {quote && selected && (
        <>
          <SectionHead title={t('Price')} className="mt-7" />
          <Card className="p-5">
            <PriceSummary lines={priceLines!} currency={cur} perspective="renter" policy={policyLine(policy, selected.start)} />
            <p className="t-sm mt-3 text-[var(--ink-4)]">
              {listing.instantBook
                ? t('Instant book: paid by card when you book, confirmed at once.')
                : t('Paid by card when {name} accepts; if they decline, the hold is released.', { name: first })}
            </p>
          </Card>
        </>
      )}

      <SectionHead title={t('Cancellation')} className="mt-7" />
      <Card className="p-5">
        <p className="text-body font-semibold">{policyName(policy)}</p>
        <p className="t-sm mt-1 text-[var(--ink-3)]">
          {policyText(policy)} {preview ? t('If the owner cancels, the renter gets everything back.') : t('If the owner cancels, you get everything back.')}
        </p>
      </Card>

      {/* ---------------------------------------------------- house rules */}
      {/* ---------------------------------------------------------- reviews */}
      <section id="reviews">
        <SectionHead title={t('What people say')} className="mt-7" />
        <Reviews reviews={reviews.data?.items ?? []} summary={info.reviews} ownerFirstName={first} ownerJobs={owner.jobsDone} staff={Boolean(preview)} />
      </section>

      <SectionHead title={t('House rules')} className="mt-7" />
      <Card className="p-5">
        <ul className="space-y-3">
          {listing.rules.map((r) => (
            <li key={r} className="flex gap-3 text-body text-[var(--ink-2)]">
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

      {!preview && (
        <div className="mt-4 flex justify-end">
          <ReportButton targetType="listing" targetId={listing.id} />
        </div>
      )}

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
                {/* The amount on the button (UX-23), the legal wording kept verbatim. */}
                {/* It says what happens (UX-50): a request holds the amount, a
                    booking pays it. German keeps the legal "zahlungspflichtig". */}
                {sending
                  ? t('Sending…')
                  : !quote
                    ? t('Book and pay')
                    : listing.instantBook
                      ? `${t('Book and pay')} · ${formatMoney(quote.total, cur)}`
                      : t('Request · {amount} held', { amount: formatMoney(quote.total, cur) })}
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
                thumb
                className="w-[52px] shrink-0 rounded-[var(--radius-m)]"
              />
              <div className="min-w-0">
                <p className="[overflow-wrap:anywhere] text-body font-semibold">{listing.title}</p>
                <p className="t-sm [overflow-wrap:anywhere] text-[var(--ink-3)]">{owner.name}</p>
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
              <p className="t-sm text-[var(--ink-4)]">{addressNote}</p>
              <div className="my-2 border-t border-[var(--line)]" />
              {/* What the renter pays, never what the owner nets (UX-23). */}
              <PriceSummary lines={priceLines!} currency={cur} perspective="renter" policy={policyLine(policy, selected.start)} />
            </Card>

            {listing.instantBook ? (
              <Banner
                tone="neutral"
                title={t('Instant book')}
                body={t('Confirmed as soon as your card is held; {name} does not need to accept first.', { name: first })}
              />
            ) : (
              <Banner
                tone="neutral"
                title={t('Nothing is charged yet')}
                body={t('Your card is held for the total. {name} has to accept first; if they decline or do not answer, the hold is released.', { name: first })}
              />
            )}
            {/* How it is paid, said before the button (UX-50); the cancellation
                terms are the price summary's dated line, said once. */}
            <Row label={t('Payment')} value={t('Card, on the next step')} />
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
        <p className="pb-2 text-body text-[var(--ink-2)]">
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
