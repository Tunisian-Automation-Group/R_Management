import type { Iso, Listing, Match, Owner, Requirement, World } from './types.ts'
import { rating, reliability } from './types.ts'
import { assessFeasibility } from './feasibility.ts'
import { earliestOffer } from './availability.ts'
import { hoursFor, quoteFor } from './pricing.ts'
import { durationLabel } from './categories.ts'

const EARTH_KM = 6371
const toRad = (d: number) => (d * Math.PI) / 180

export function distanceKm(
  a: { lat: number; lng: number },
  b: { lat: number; lng: number },
): number {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_KM * Math.asin(Math.sqrt(h))
}

/** Min-max to 0..1. All-equal collapses to 0.5 rather than dividing by zero. */
function normalise(values: number[]): number[] {
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  if (hi === lo) return values.map(() => 0.5)
  return values.map((v) => (v - lo) / (hi - lo))
}

// Hand-tuned weights. A learned ranker only makes sense once there is real outcome
// data to learn from, which is what the rating loop is accumulating.
const W = { price: 0.3, soon: 0.2, trust: 0.3, near: 0.2 }

/** Reliability dominates; stars break ties; an unrated owner sits mid-scale. */
export function trustOf(o: Owner): number {
  const stars = rating(o)
  return 0.6 * reliability(o) + 0.4 * (stars === null ? 0.5 : stars / 5)
}

export function trackRecord(o: Owner): string {
  if (o.jobsDone === 0) return 'New on Cappy'
  const pct = Math.round((o.onTimeJobs / o.jobsDone) * 100)
  return `${o.jobsDone} booking${o.jobsDone === 1 ? '' : 's'} · ${pct}% on time`
}

const windowEnd = (req: Requirement): Iso =>
  req.mode === 'window' ? req.latest : req.deadline

/**
 * Pure. Every input arrives as an argument, including `now`, so the same inputs
 * always produce the same ranking, which is what makes it testable and portable.
 */
export function findMatches(req: Requirement, world: World, now: Iso): Match[] {
  const from = world.districts[req.district]
  if (!from) return []

  const owners = new Map(world.owners.map((o) => [o.id, o]))
  const until = windowEnd(req)
  if (Date.parse(until) <= Date.parse(now)) return []

  type Candidate = { listing: Listing; owner: Owner; match: Omit<Match, 'score'> }
  const candidates: Candidate[] = []

  for (const listing of world.listings) {
    const owner = owners.get(listing.ownerId)
    if (!owner) continue

    const fit = assessFeasibility(req, listing)
    if (!fit.feasible) continue

    const to = world.districts[listing.district]
    if (!to) continue
    const km = distanceKm(from, to)
    if (km > req.maxDistanceKm) continue

    const hours = hoursFor(req, listing)
    const quote = quoteFor(req, listing)
    if (hours === null || quote === null) continue

    const slots = world.slots.filter((s) => s.listingId === listing.id)
    const offer = earliestOffer(slots, hours, now, until)
    if (!offer) continue

    candidates.push({
      listing,
      owner,
      match: {
        listingId: listing.id,
        ownerId: owner.id,
        slotId: offer.slotId,
        start: offer.start,
        end: offer.end,
        confidence: fit.confidence,
        reasons: [
          ...fit.reasons,
          `${durationLabel(hours)} of idle time`,
          `${km.toFixed(1)} km away`,
          trackRecord(owner),
        ],
        quote,
        distanceKm: km,
      },
    })
  }

  if (candidates.length === 0) return []

  const cheap = normalise(candidates.map((c) => -c.match.quote.total))
  const soon = normalise(candidates.map((c) => -Date.parse(c.match.start)))
  const near = normalise(candidates.map((c) => -c.match.distanceKm))
  const trust = normalise(candidates.map((c) => trustOf(c.owner)))

  return candidates
    .map((c, i) => ({
      ...c.match,
      score: W.price * cheap[i] + W.soon * soon[i] + W.near * near[i] + W.trust * trust[i],
    }))
    .sort((a, b) => b.score - a.score)
}

export type SortKey = 'best' | 'price' | 'soonest' | 'nearest'

export function sortMatches(matches: Match[], key: SortKey): Match[] {
  const copy = [...matches]
  switch (key) {
    case 'price':
      return copy.sort((a, b) => a.quote.total - b.quote.total)
    case 'soonest':
      return copy.sort((a, b) => Date.parse(a.start) - Date.parse(b.start))
    case 'nearest':
      return copy.sort((a, b) => a.distanceKm - b.distanceKm)
    default:
      return copy.sort((a, b) => b.score - a.score)
  }
}

/**
 * Build the match for a window the buyer picked themselves, rather than the
 * soonest one we suggested. Same shape, same reasons, so everything downstream
 * (quote, booking, receipt) is identical whichever route they took.
 */
export function matchForOffer(
  req: Requirement,
  listing: Listing,
  owner: Owner,
  offer: { slotId: string; start: Iso; end: Iso },
  km: number,
): Match | null {
  const fit = assessFeasibility(req, listing)
  if (!fit.feasible) return null
  const hours = hoursFor(req, listing)
  const quote = quoteFor(req, listing)
  if (hours === null || quote === null) return null

  return {
    listingId: listing.id,
    ownerId: owner.id,
    slotId: offer.slotId,
    start: offer.start,
    end: offer.end,
    score: 1,
    confidence: fit.confidence,
    reasons: [
      ...fit.reasons,
      `${durationLabel(hours)} of idle time`,
      `${km.toFixed(1)} km away`,
      trackRecord(owner),
    ],
    quote,
    distanceKm: km,
  }
}
