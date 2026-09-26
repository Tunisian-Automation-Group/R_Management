// Display helpers for matches. The ranking itself runs on the server.
import type { Owner } from './types.ts'
import { locale, plural, t } from '../i18n.ts'

const EARTH_KM = 6371
const toRad = (d: number) => (d * Math.PI) / 180

/** Great-circle distance, for "3.2 km away" where the server did not say. */
export function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_KM * Math.asin(Math.sqrt(h))
}

export function trackRecord(o: Owner): string {
  if (o.jobsDone === 0) return t('New on Cappy')
  const pct = new Intl.NumberFormat(locale(), { style: 'percent', maximumFractionDigits: 0 }).format(o.onTimeJobs / o.jobsDone)
  return `${plural(o.jobsDone, '{n} booking', '{n} bookings')} · ${t('{pct} on time', { pct })}`
}

/** How the server can order results. */
export type SortKey = 'best' | 'price' | 'soonest' | 'nearest'
