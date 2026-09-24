// The only module that knows where data lives.
//
// Every function is async even though it currently reads local arrays. That is
// deliberate: swapping in a real backend changes this file and no call sites.
//
// It stores a DELTA, never the whole world. Seed content, listings, windows,
// owner records, is rebuilt from code on every load and only what the person
// actually did is layered on top. Persisting the whole world meant that editing
// seed.ts changed nothing for anyone whose browser already held a copy: a silent
// and genuinely confusing class of bug, and no amount of key-bumping fixes it.
import type { Booking, Listing, Owner, Slot, World } from '../domain/types.ts'
import { districts, listings, owners, reviews, seedBookings, slots } from './seed.ts'

const KEY = 'cappy.delta.v1'

type OwnerRecord = Pick<Owner, 'ratingSum' | 'jobsDone' | 'onTimeJobs'>

type Delta = {
  bookings: Booking[]
  /** Listings the person created. These have no seed counterpart. */
  ownListings: Listing[]
  ownSlots: Slot[]
  /** Listings they paused, seeded or their own. */
  paused: string[]
  /** Seeded listings they removed. */
  removed: string[]
  /** Owner records moved by ratings they gave. */
  records: Record<string, OwnerRecord>
  /** Listings they saved. */
  saved: string[]
  /** Set once anything has been saved, so the seeded inbox request is offered
   *  on a cold start and never re-injected after it has been answered. */
  started: boolean
}

const empty: Delta = {
  bookings: [],
  ownListings: [],
  ownSlots: [],
  paused: [],
  removed: [],
  records: {},
  saved: [],
  started: false,
}

const seedListingIds = new Set(listings.map((l) => l.id))
const seedSlotIds = new Set(slots.map((s) => s.id))
const seedRecords = new Map(owners.map((o) => [o.id, o]))

function read(): Delta {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return empty
    // Merge key by key: a half-written or older delta must never brick the app.
    return { ...empty, ...(JSON.parse(raw) as Partial<Delta>) }
  } catch {
    return empty
  }
}

function write(d: Delta): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(d))
  } catch {
    // Private mode or a full quota. Persistence is a convenience, not correctness.
  }
}

export async function getWorld(): Promise<World> {
  const d = read()
  const removed = new Set(d.removed)
  const paused = new Set(d.paused)

  const merged: Listing[] = [...d.ownListings, ...listings]
    .filter((l) => !removed.has(l.id))
    .map((l) => (paused.has(l.id) ? { ...l, active: false } : l))

  const live = new Set(merged.map((l) => l.id))

  return {
    owners: owners.map((o) => (d.records[o.id] ? { ...o, ...d.records[o.id] } : o)),
    listings: merged,
    slots: [...slots, ...d.ownSlots].filter((s) => live.has(s.listingId)),
    districts,
    // Reviews this person wrote are not stored separately: they are the outcome
    // on a booking they already saved, and the store folds them in from there.
    reviews: reviews.filter((r) => live.has(r.listingId)),
  }
}

export async function getBookings(): Promise<Booking[]> {
  const d = read()
  // A saved booking can outlive the listing it was made against when seed.ts
  // changes underneath it: the old washing machine went, and a request for it
  // sat in the Earn inbox as "wants your listing". Keep bookings for anything
  // that still exists in code or that this person listed themselves; a listing
  // they removed on purpose is different, and its history stays.
  const known = new Set([...seedListingIds, ...d.ownListings.map((l) => l.id)])
  const saved = d.bookings.filter((b) => known.has(b.match.listingId))
  if (!d.started) return [...seedBookings(), ...saved]
  // If the seeded inbox request was one of the casualties, bring the current one
  // back rather than leaving the owner side empty for no reason they can see.
  const have = new Set(saved.map((b) => b.id))
  return [...seedBookings().filter((b) => !have.has(b.id)), ...saved]
}

export async function getSaved(): Promise<string[]> {
  // A saved listing that has since gone from the catalogue is just dropped.
  const d = read()
  const known = new Set([...seedListingIds, ...d.ownListings.map((l) => l.id)])
  return d.saved.filter((id) => known.has(id))
}

export async function persist(world: World, bookings: Booking[], saved: string[]): Promise<void> {
  const present = new Set(world.listings.map((l) => l.id))

  const records: Record<string, OwnerRecord> = {}
  for (const o of world.owners) {
    const seeded = seedRecords.get(o.id)
    if (
      seeded &&
      (seeded.ratingSum !== o.ratingSum ||
        seeded.jobsDone !== o.jobsDone ||
        seeded.onTimeJobs !== o.onTimeJobs)
    ) {
      records[o.id] = { ratingSum: o.ratingSum, jobsDone: o.jobsDone, onTimeJobs: o.onTimeJobs }
    }
  }

  write({
    bookings,
    ownListings: world.listings.filter((l) => !seedListingIds.has(l.id)),
    ownSlots: world.slots.filter((s) => !seedSlotIds.has(s.id)),
    paused: world.listings.filter((l) => !l.active).map((l) => l.id),
    removed: [...seedListingIds].filter((id) => !present.has(id)),
    records,
    saved,
    started: true,
  })
}

export async function reset(): Promise<void> {
  try {
    localStorage.removeItem(KEY)
    // Older builds stored the whole world under these; clear them too so a
    // stale copy cannot linger behind the new delta.
    for (const old of ['cappy.v1', 'cappy.v2', 'cappy.v3-eu']) localStorage.removeItem(old)
  } catch {
    // Nothing stored, nothing to clear.
  }
}
