// Display formatting. Locale-aware, app layer only, the domain never formats.
import { locale, plural, t } from '../i18n.ts'

const TODAY = () => {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

const dayIndex = (iso: string) =>
  Math.round((new Date(iso).setHours(0, 0, 0, 0) - TODAY().getTime()) / 86_400_000)

export const time = (iso: string) =>
  new Date(iso).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })

/** "today", "tomorrow", then a weekday, nobody reads a date they can name. */
export function day(iso: string): string {
  const i = dayIndex(iso)
  if (i === 0) return t('today')
  if (i === 1) return t('tomorrow')
  if (i > 1 && i < 7) return new Date(iso).toLocaleDateString(locale(), { weekday: 'long' })
  return new Date(iso).toLocaleDateString(locale(), { day: 'numeric', month: 'short' })
}

export const dayShort = (iso: string) => {
  const i = dayIndex(iso)
  if (i === 0) return t('Today')
  if (i === 1) return t('Tomorrow')
  return new Date(iso).toLocaleDateString(locale(), { weekday: 'short', day: 'numeric', month: 'short' })
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
  if (mins < 0) return t('now')
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

export const responseTime = (mins: number) =>
  mins < 60 ? t('Replies in ~{n} min', { n: mins }) : t('Replies in ~{n} h', { n: Math.round(mins / 60) })

/** Same-district listings geocode to one point, so "0 m" meant "near you" and read
 *  as broken. Under 300 m is walking distance, and that is what it says. */
export const distance = (km: number) =>
  km < 0.3
    ? t('Nearby')
    : km < 1
      ? `${Math.round(km * 1000)} m`
      : `${km.toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })} km`
