// Display formatting. Locale-aware, app layer only, the domain never formats.

const TODAY = () => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

const dayIndex = (iso: string) =>
  Math.round((new Date(iso).setHours(0, 0, 0, 0) - TODAY().getTime()) / 86_400_000)

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

/** "today", "tomorrow", then a weekday, nobody reads a date they can name. */
export function day(iso: string): string {
  const i = dayIndex(iso)
  if (i === 0) return 'today'
  if (i === 1) return 'tomorrow'
  if (i > 1 && i < 7) return new Date(iso).toLocaleDateString('en-GB', { weekday: 'long' })
  return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export const dayShort = (iso: string) => {
  const i = dayIndex(iso)
  if (i === 0) return 'Today'
  if (i === 1) return 'Tomorrow'
  return new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
}

/** "today 18:00" / "Thursday 06:00" */
export const when = (iso: string) => `${day(iso)} ${time(iso)}`

/** "today, 18:00 – 20:00", one date when the window does not cross midnight. */
export function range(startIso: string, endIso: string): string {
  const sameDay = dayIndex(startIso) === dayIndex(endIso)
  return sameDay
    ? `${day(startIso)}, ${time(startIso)} – ${time(endIso)}`
    : `${when(startIso)} → ${when(endIso)}`
}

export function relative(iso: string): string {
  const mins = Math.round((Date.parse(iso) - Date.now()) / 60_000)
  if (mins < 0) return 'now'
  if (mins < 60) return `in ${mins} min`
  const h = Math.round(mins / 60)
  if (h < 24) return `in ${h} h`
  const d = Math.round(h / 24)
  return `in ${d} day${d === 1 ? '' : 's'}`
}

/** Past tense. `relative` collapses everything in the past to "now", which reads
 *  as "asked now ago" once you put it in a sentence. */
export function ago(iso: string): string {
  const mins = Math.round((Date.now() - Date.parse(iso)) / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  if (h < 24) return `${h} h ago`
  const d = Math.round(h / 24)
  if (d < 14) return `${d} day${d === 1 ? '' : 's'} ago`
  // "47 days ago" is a number to work out; a review date is read at a glance.
  if (d < 60) return `${Math.round(d / 7)} weeks ago`
  const m = Math.round(d / 30)
  return `${m} month${m === 1 ? '' : 's'} ago`
}

export const responseTime = (mins: number) =>
  mins < 60 ? `Replies in ~${mins} min` : `Replies in ~${Math.round(mins / 60)} h`

/** Same-district listings geocode to one point, so "0 m" meant "near you" and read
 *  as broken. Under 300 m is walking distance, and that is what it says. */
export const distance = (km: number) =>
  km < 0.3 ? 'Nearby' : km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`
