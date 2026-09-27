// Display formatting. Locale-aware, app layer only, the domain never formats.
import { locale, plural, t } from '../i18n.ts'

const TODAY = () => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

const dayIndex = (iso: string) =>
  Math.round((new Date(iso).setHours(0, 0, 0, 0) - TODAY().getTime()) / 86_400_000)

/** "17:00", "5:00 PM": the locale's own clock. `2-digit` hours gave en-US a
 *  leading zero ("05:00 PM") it never writes (V4-19); 24-hour locales keep it. */
const clock = (d: Date) =>
  d.toLocaleTimeString(locale(), {
    hour: new Intl.DateTimeFormat(locale(), { hour: 'numeric' }).resolvedOptions().hour12 ? 'numeric' : '2-digit',
    minute: '2-digit',
  })
export const time = (iso: string) => clock(new Date(iso))

/** A wall-clock "HH:MM" (a weekly rule, a pattern) in the reader's format. */
export const clockTime = (hhmm: string) => {
  if (hhmm === '24:00') return clock(new Date(2000, 0, 1, 0, 0)).replace(/^0?0/, '24') // midnight at the end of the day
  const [h, m] = hhmm.split(':').map(Number)
  return clock(new Date(2000, 0, 1, h, m))
}

/** "today", "tomorrow", then a weekday, nobody reads a date they can name. */
export function day(iso: string): string {
  const i = dayIndex(iso)
  if (i === 0) return t('today')
  if (i === 1) return t('tomorrow')
  // A weekday alone leaves the reader to work out which one (V3-19): "Wed 30 Sep".
  // Also after the first week: "Oct 3" beside "Tue, Sep 29" read as a different kind of date (V5-32).
  return new Date(iso).toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
}

export const dayShort = (iso: string) => {
  const i = dayIndex(iso)
  if (i === 0) return t('Today')
  if (i === 1) return t('Tomorrow')
  if (i === -1) return t('Yesterday')
  return new Date(iso).toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
}

/** "today 18:00" / "Thursday 06:00" */
export const when = (iso: string) => `${day(iso)}, ${time(iso)}`

/** "today, 18:00 – 20:00", one date when the window does not cross midnight. */
export function range(startIso: string, endIso: string): string {
  const sameDay = dayIndex(startIso) === dayIndex(endIso)
  return sameDay
    ? `${day(startIso)}, ${time(startIso)} – ${time(endIso)}`
    : `${when(startIso)} → ${when(endIso)}`
}

export function relative(iso: string): string {
  const mins = Math.round((Date.parse(iso) - Date.now()) / 60_000)
  if (mins < 0) return t('now')
  // Never "in 0 min" in the last minute (V7-21); it fits every sentence it is put in.
  if (mins < 1) return t('in under a minute')
  if (mins < 60) return t('in {n} min', { n: mins })
  const h = Math.round(mins / 60)
  if (h < 24) return t('in {n} h', { n: h })
  const d = Math.round(h / 24)
  return plural(d, 'in {n} day', 'in {n} days')
}

/** Past tense. `relative` collapses everything in the past to "now", which reads
 *  as "asked now ago" once you put it in a sentence. */
export function ago(iso: string): string {
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60_000)
  if (mins < 1) return t('just now')
  if (mins < 60) return t('{n} min ago', { n: mins })
  const h = Math.round(mins / 60)
  if (h < 24) return t('{n} h ago', { n: h })
  const d = Math.round(h / 24)
  if (d < 14) return plural(d, '{n} day ago', '{n} days ago')
  // "47 days ago" is a number to work out; a review date is read at a glance.
  if (d < 60) return t('{n} weeks ago', { n: Math.round(d / 7) })
  const m = Math.round(d / 30)
  return plural(m, '{n} month ago', '{n} months ago')
}

/** "…, and it lapses." after a sentence that may already end in "Min." (V3-15). */
export const sentence = (s: string) => (/[.!?]$/.test(s) ? `${s} ` : `${s}. `)

/** "Replies in ~20 min", measured (H-1); null until the owner has answered
 *  enough requests to say, and then the app says nothing about it. */
export const responseTime = (mins: number | null | undefined): string | null =>
  mins == null
    ? null
    : mins < 60
      ? t('Replies in ~{n} min', { n: Math.max(1, Math.round(mins)) })
      : t('Replies in ~{n} h', { n: Math.round(mins / 60) })

/** A share in the reader's format: "95%" (en), "95 %" (de, fr) (V5-17). */
export const percent = (share: number, loc: string = locale()) =>
  new Intl.NumberFormat(loc, { style: 'percent', maximumFractionDigits: 0 }).format(share)

/** "Answers 95% of requests", with the time when both are known. */
export const responseRate = (rate: number | null | undefined): string | null =>
  rate == null ? null : t('Answers {pct} of requests', { pct: percent(rate) })

/** Where distance is read in miles: the US and the UK (GOAL 16). Everyone else, km. */
const MILES = new Set(['US', 'GB', 'LR', 'MM'])
const unitFor = (loc: string) => (MILES.has((loc.split('-')[1] ?? '').toUpperCase()) ? 'mile' : 'kilometer')

/** "2.3 km", "1.4 mi". Same-district listings geocode to one point, so "0 m"
 *  meant "near you" and read as broken: under 300 m says "Nearby". */
export function formatDistance(km: number, loc: string = locale()): string {
  if (km < 0.3) return t('Nearby')
  const unit = unitFor(loc)
  const n = unit === 'mile' ? km / 1.609344 : km
  if (unit === 'kilometer' && km < 1) {
    return new Intl.NumberFormat(loc, { style: 'unit', unit: 'meter', maximumFractionDigits: 0 }).format(Math.round(km * 1000))
  }
  return new Intl.NumberFormat(loc, { style: 'unit', unit, maximumFractionDigits: n < 10 ? 1 : 0 }).format(n)
}

/** A search radius, rounded the way a person says it: "20 km", "12 mi". */
export const formatRadius = (km: number, loc: string = locale()): string =>
  unitFor(loc) === 'mile'
    ? // A 1 km radius is 0.6 mi, not "1 mi" (V7-17).
      new Intl.NumberFormat(loc, { style: 'unit', unit: 'mile', maximumFractionDigits: km < 16 ? 1 : 0 }).format(km / 1.609344)
    : new Intl.NumberFormat(loc, { style: 'unit', unit: 'kilometer', maximumFractionDigits: 0 }).format(km)

/** The cancellation policies, as booking/cancellation.py applies them. */
export const POLICIES = ['flexible', 'moderate', 'strict'] as const
export function policyName(p: string | undefined): string {
  return p === 'moderate' ? t('Moderate') : p === 'strict' ? t('Strict') : t('Flexible')
}
/** The policy a booking actually gets: moderate and strict wait for Cappy's
 *  switch (booking's paid_cancellation_policies, mirrored in app-config's
 *  `paidCancellationPolicies` flag); until then everyone gets flexible. */
export const policyInForce = (p: string | undefined, paidOn: boolean) => (paidOn ? p : 'flexible')

export function policyText(p: string | undefined): string {
  if (p === 'moderate') return t('Full refund until 24 hours before, then half.')
  if (p === 'strict') return t('Full refund until 7 days before, half until 24 hours before, then nothing.')
  return t('Full refund until the booked time starts.')
}

/** The policy as one dated line for a chosen time (UX-23): "Free cancellation
 *  until Sat 3 Oct, 10:00", or plainly non-refundable once that has passed. */
export function policyLine(p: string | undefined, startIso: string, now = Date.now()): string {
  const before = p === 'strict' ? 7 * 24 : p === 'moderate' ? 24 : 0
  const until = Date.parse(startIso) - before * 3_600_000
  if (until <= now) return p === 'flexible' || !p ? t('Free cancellation until it starts') : t('No free cancellation for this time')
  return t('Free cancellation until {when}', { when: when(new Date(until).toISOString()) })
}

/** Why a listing waits, when it is not a price check (V5-1). */
export const holdText = (reason: 'market_not_live' | 'district_not_in_country'): string =>
  reason === 'market_not_live'
    ? t('Not live: Cappy is not open in that country yet. Move it to a place in an open market to publish it.')
    : t('Not live: the place is not in your country. Move it to a district in your own country to publish it.')

/** A renter's record from owners' ratings: "4.8 from 5 bookings" or "New renter". */
export function renterRecord(sum: number | undefined, jobs: number | undefined): string {
  if (!jobs) return t('New renter')
  // One decimal in the reader's format ("4,0" in German), and the plural their language uses (V5-17).
  const stars = ((sum ?? 0) / jobs).toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })
  const one = new Intl.PluralRules(locale()).select(jobs) === 'one'
  return t(one ? 'Renter {stars} from {n} booking' : 'Renter {stars} from {n} bookings', { stars, n: jobs })
}

/** S-18: shown only when the owner has cancelled or missed some (the server
 *  leaves the rate out under 5 accepted bookings). */
export function cancelRate(rate: number | undefined): string | null {
  if (!rate) return null
  return t('Cancelled {pct} of confirmed bookings in the last year', { pct: percent(Math.max(0.01, rate)) })
}

/** "Sa", "So", "Di", "Do": one letter could not tell Saturday from Sunday (V3-16). */
export const weekday2 = (d: Date) => d.toLocaleDateString(locale(), { weekday: 'short' }).replace('.', '').slice(0, 2)
