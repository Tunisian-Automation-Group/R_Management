import type { Cents, District, Iso, Listing, Owner, World } from './types.ts'
import { isWindow } from './types.ts'
import { earliestOffer, type Offer } from './availability.ts'
import { distanceKm, trustOf } from './match.ts'

export type Spotlight = {
  listing: Listing
  owner: Owner
  offer: Offer
  distanceKm: number
  /** Cheapest real booking you could make, the minimum, not an average. */
  fromPrice: Cents
  /** The idle window is already open, so this is available this second. Offers
   *  round up to the next half hour, which would otherwise report "in 4 min"
   *  for something sitting free since this morning. */
  freeNow: boolean
  /** When the underlying window opened or opens, the honest answer to "when?". */
  windowStart: Iso
}

/** The smallest booking this listing will accept, priced. */
export function fromPrice(listing: Listing): Cents {
  if (isWindow(listing)) {
    return Math.round(listing.minHours * listing.ratePerHour) + listing.extraFee
  }
  return listing.setupFee + Math.round((listing.setupHours + 1) * listing.ratePerHour)
}

/** The shortest booking worth offering, used to answer "is this free soon?". */
const probeHours = (listing: Listing): number =>
  isWindow(listing) ? listing.minHours : listing.setupHours + 1

/**
 * What is genuinely free near you in the next `withinHours`, soonest first.
 *
 * Pure: `now` is passed in, nothing reads the clock.
 */
export function availableSoon(
  world: World,
  district: string,
  maxKm: number,
  now: Iso,
  withinHours = 24,
  limit = 12,
): Spotlight[] {
  const from = world.districts[district]
  if (!from) return []
  const until = new Date(Date.parse(now) + withinHours * 3_600_000).toISOString()
  const owners = new Map(world.owners.map((o) => [o.id, o]))
  const out: Spotlight[] = []

  for (const listing of world.listings) {
    if (!listing.active) continue
    const owner = owners.get(listing.ownerId)
    const to = world.districts[listing.district]
    if (!owner || !to) continue

    const km = distanceKm(from, to)
    if (km > maxKm) continue

    const slots = world.slots.filter((s) => s.listingId === listing.id)
    const offer = earliestOffer(slots, probeHours(listing), now, until)
    if (!offer) continue

    const slot = slots.find((s) => s.id === offer.slotId)!
    out.push({
      listing,
      owner,
      offer,
      distanceKm: km,
      fromPrice: fromPrice(listing),
      freeNow: Date.parse(slot.start) <= Date.parse(now),
      windowStart: slot.start,
    })
  }

  // Soonest first, and a better-trusted owner wins an exact tie.
  return out
    .sort(
      (a, b) =>
        Number(b.freeNow) - Number(a.freeNow) ||
        Date.parse(a.offer.start) - Date.parse(b.offer.start) ||
        trustOf(b.owner) - trustOf(a.owner),
    )
    .slice(0, limit)
}

/** Free-text filter over the things a person would actually type. */
export function searchListings(listings: Listing[], query: string): Listing[] {
  const q = query.trim().toLowerCase()
  if (!q) return listings
  return listings.filter((l) =>
    [l.title, l.blurb, l.district, l.category].join(' ').toLowerCase().includes(q),
  )
}

export type IdleSummary = {
  /** Idle hours across every active listing in range, over the horizon. */
  hours: number
  /** What those hours would be worth at the owners' own asking rates. */
  value: Cents
  listings: number
  owners: number
  /** Available this second, not merely later today. */
  freeNowCount: number
}

/**
 * The size of the waste, nearby, right now.
 *
 * This is the number the whole product exists to shrink: hours of capacity sitting
 * within walking or driving distance that nobody is collecting money for. Priced at
 * each owner's own rate, so it is their claim, not our estimate.
 */
export function idleNearby(
  world: World,
  district: string,
  maxKm: number,
  now: Iso,
  horizonHours = 24,
): IdleSummary {
  const from = world.districts[district]
  if (!from) return { hours: 0, value: 0, listings: 0, owners: 0, freeNowCount: 0 }

  const nowMs = Date.parse(now)
  const untilMs = nowMs + horizonHours * 3_600_000
  const owners = new Set<string>()
  let hours = 0
  let value = 0
  let listings = 0
  let freeNowCount = 0

  for (const listing of world.listings) {
    if (!listing.active) continue
    const to = world.districts[listing.district]
    if (!to || distanceKm(from, to) > maxKm) continue

    let listingHours = 0
    let live = false

    for (const slot of world.slots) {
      if (slot.listingId !== listing.id) continue
      const start = Date.parse(slot.start)
      const end = Date.parse(slot.end)
      // Only the part of the window that is still ahead of us and inside the horizon.
      const lo = Math.max(start, nowMs)
      const hi = Math.min(end, untilMs)
      if (hi <= lo) continue

      const wall = (end - start) / 3_600_000
      const overlap = (hi - lo) / 3_600_000
      // Scale declared usable hours by how much of the window is left.
      listingHours += wall > 0 ? slot.hoursUsable * (overlap / wall) : 0
      if (start <= nowMs) live = true
    }

    if (listingHours <= 0) continue
    hours += listingHours
    value += Math.round(listingHours * listing.ratePerHour)
    listings += 1
    owners.add(listing.ownerId)
    if (live) freeNowCount += 1
  }

  return { hours, value, listings, owners: owners.size, freeNowCount }
}

export type CityStat = {
  /** The market's name, Berlin, Eindhoven, Brescia. */
  city: string
  country: string
  lat: number
  lng: number
  listings: number
  /** Idle hours live in that city over the horizon, priced at owners' rates. */
  idle: IdleSummary
}

/**
 * Every market with capacity on the platform, busiest first.
 *
 * Drives the city switcher and the Europe-level map: a marker per market, sized
 * by what is actually live there rather than by how many rows exist.
 *
 * The horizon is a week, not a day. "Free in the next 24 hours" is the right
 * question for a washing machine tonight and the wrong one for a machine shop's
 * gap next Tuesday, on a daily horizon fabrication capacity reads as empty.
 */
export function cities(world: World, now: Iso, horizonHours = 168): CityStat[] {
  const byCity = new Map<string, { country: string; lat: number; lng: number; n: number }>()

  for (const d of Object.values(world.districts)) {
    const seen = byCity.get(d.metro)
    if (seen) {
      // Running mean of the districts, so the marker sits over the city centre.
      seen.lat += (d.lat - seen.lat) / (seen.n + 1)
      seen.lng += (d.lng - seen.lng) / (seen.n + 1)
      seen.n += 1
    } else {
      byCity.set(d.metro, { country: d.country, lat: d.lat, lng: d.lng, n: 1 })
    }
  }

  const counts = new Map<string, number>()
  for (const l of world.listings) {
    if (!l.active) continue
    const d = world.districts[l.district]
    if (d) counts.set(d.metro, (counts.get(d.metro) ?? 0) + 1)
  }

  return [...byCity.entries()]
    .map(([city, c]) => ({
      city,
      country: c.country,
      lat: c.lat,
      lng: c.lng,
      listings: counts.get(city) ?? 0,
      // A city-wide radius: big enough to cover the metro area and its industry.
      idle: idleNearby(world, anyDistrictIn(world, city) ?? '', 60, now, horizonHours),
    }))
    .filter((c) => c.listings > 0)
    .sort((a, b) => b.idle.hours - a.idle.hours || a.city.localeCompare(b.city))
}

const anyDistrictIn = (world: World, metro: string): string | undefined =>
  Object.values(world.districts).find((d) => d.metro === metro)?.name

/** Europe-wide total, the number an investor asks for. A week, like `cities`. */
export function idleEurope(world: World, now: Iso, horizonHours = 168): IdleSummary {
  return cities(world, now, horizonHours).reduce<IdleSummary>(
    (acc, c) => ({
      hours: acc.hours + c.idle.hours,
      value: acc.value + c.idle.value,
      listings: acc.listings + c.idle.listings,
      owners: acc.owners + c.idle.owners,
      freeNowCount: acc.freeNowCount + c.idle.freeNowCount,
    }),
    { hours: 0, value: 0, listings: 0, owners: 0, freeNowCount: 0 },
  )
}

/**
 * The seeded district closest to a real coordinate, and how far away it is.
 *
 * Used to turn a browser geolocation fix into somewhere the app actually has
 * capacity. Returns the distance too, so the caller can decide what to do when
 * the person is nowhere near a market we serve, silently dropping someone in
 * Berlin because that is the biggest city would be worse than telling them.
 */
export function nearestDistrict(
  world: World,
  lat: number,
  lng: number,
): { district: District; km: number } | null {
  const all = Object.values(world.districts)
  if (all.length === 0) return null

  let best = all[0]
  let bestKm = distanceKm({ lat, lng }, best)
  for (const d of all.slice(1)) {
    const km = distanceKm({ lat, lng }, d)
    if (km < bestKm) {
      best = d
      bestKm = km
    }
  }
  return { district: best, km: bestKm }
}
