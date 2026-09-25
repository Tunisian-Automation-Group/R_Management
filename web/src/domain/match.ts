// Display helpers for matches. The ranking itself runs on the server.
import type { Owner } from './types.ts'

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
  if (o.jobsDone === 0) return 'New on Cappy'
  const pct = Math.round((o.onTimeJobs / o.jobsDone) * 100)
  return `${o.jobsDone} booking${o.jobsDone === 1 ? '' : 's'} · ${pct}% on time`
}

/** How the server can order results. */
export type SortKey = 'best' | 'price' | 'soonest' | 'nearest'
