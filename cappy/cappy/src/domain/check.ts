// Domain self-check. Pure functions, no framework, no fixtures.
//   npm run check
import assert from 'node:assert/strict'
import type { BatchRequest, Owner, WindowRequest, World } from './types.ts'
import { applyOutcome, isBatch, isWindow } from './types.ts'
import { findMatches, sortMatches, trackRecord, trustOf } from './match.ts'
import { offersFor } from './availability.ts'
import { cities, idleEurope, idleNearby, nearestDistrict } from './browse.ts'
import { hoursFor, quoteFor, PLATFORM_FEE_BPS } from './pricing.ts'
import { assessFeasibility } from './feasibility.ts'
import { category } from './categories.ts'
import { formatEur } from './money.ts'
import { districts, listings, owners, reviews, slots } from '../data/seed.ts'
import { REVIEW_TAGS, summarise } from './reviews.ts'

const world: World = { owners, listings, slots, districts, reviews }
const now = new Date().toISOString()
const plus = (h: number) => new Date(Date.parse(now) + h * 3_600_000).toISOString()

const listing = (id: string) => {
  const l = listings.find((x) => x.id === id)
  assert.ok(l, `missing listing ${id}`)
  return l
}
const owner = (id: string) => {
  const o = owners.find((x) => x.id === id)
  assert.ok(o, `missing owner ${id}`)
  return o
}

const saw: WindowRequest = {
  mode: 'window',
  category: 'workshop',
  hours: 2,
  earliest: now,
  latest: plus(24 * 7),
  district: 'Kreuzberg',
  maxDistanceKm: 10,
}

const brackets: BatchRequest = {
  mode: 'batch',
  category: 'fabrication',
  quantity: 500,
  material: 'Aluminium 6061',
  dims: { x: 120, y: 80, z: 25 },
  toleranceMm: 0.05,
  deadline: plus(24 * 21),
  district: 'Kreuzberg',
  maxDistanceKm: 90,
}

// 1. seed integrity. Every listing resolves an owner, a real category, and the
//     category's booking mode matches the listing's shape.
{
  const ownerIds = new Set(owners.map((o) => o.id))
  const listingIds = new Set(listings.map((l) => l.id))
  for (const l of listings) {
    assert.ok(ownerIds.has(l.ownerId), `${l.id} has no owner`)
    assert.ok(districts[l.district], `${l.id} sits in an unknown district`)
    assert.equal(category(l.category).mode, l.mode, `${l.id} mode disagrees with its category`)
  }
  for (const s of slots) {
    assert.ok(listingIds.has(s.listingId), `slot ${s.id} points at nothing`)
    assert.ok(Date.parse(s.end) > Date.parse(s.start), `slot ${s.id} ends before it starts`)
    assert.ok(
      s.hoursUsable <= (Date.parse(s.end) - Date.parse(s.start)) / 3_600_000 + 1e-9,
      `slot ${s.id} claims more usable hours than it lasts`,
    )
  }
  for (const o of owners) {
    assert.ok(o.onTimeJobs <= o.jobsDone, `${o.id} was on time more often than it worked`)
  }
}

// 2. a window request matches only window listings in that category.
{
  const m = findMatches(saw, world, now)
  assert.ok(m.length > 0, 'no saw capacity found')
  for (const x of m) {
    const l = listing(x.listingId)
    assert.ok(isWindow(l), 'a batch listing answered a window request')
    assert.equal(l.category, 'workshop')
  }
}

// 3. a batch request matches only batch listings, and respects tolerance.
{
  const m = findMatches(brackets, world, now)
  assert.ok(m.length > 0, 'no milling capacity found')
  for (const x of m) {
    const l = listing(x.listingId)
    assert.ok(
      isBatch(l) && l.toleranceMm !== undefined && l.toleranceMm <= 0.05,
      'a machine that cannot hold tolerance matched',
    )
  }
  assert.equal(findMatches({ ...brackets, toleranceMm: 0.001 }, world, now).length, 0)
}

// 4. time actually constrains. A deadline in the past, and a job larger than any
//     idle window, both find nothing.
{
  assert.equal(findMatches({ ...brackets, deadline: now }, world, now).length, 0, 'past deadline matched')
  assert.equal(
    findMatches({ ...brackets, quantity: 500_000 }, world, now).length,
    0,
    'a job bigger than every gap still matched',
  )
  assert.equal(
    findMatches({ ...saw, hours: 400 }, world, now).length,
    0,
    'a 400-hour booking matched a saw',
  )
}

// 5. booking limits are enforced in both directions.
{
  const pa = listing('l12') // minimum 8 h
  assert.equal(
    assessFeasibility({ ...saw, category: 'events', hours: 2 }, pa).feasible,
    false,
    'booked under the minimum',
  )
  assert.equal(
    assessFeasibility({ ...saw, category: 'events', hours: 200 }, pa).feasible,
    false,
    'booked over the maximum',
  )
  assert.equal(assessFeasibility({ ...saw, category: 'events', hours: 24 }, pa).feasible, true)
}

// 6. offers sit inside their window, never overlap its end, and are ordered.
{
  const drillSlots = slots.filter((s) => s.listingId === 'l8')
  const offers = offersFor(drillSlots, 2, now, plus(24 * 5))
  assert.ok(offers.length > 3, 'expected several drill slots this week')
  for (const o of offers) {
    const slot = drillSlots.find((s) => s.id === o.slotId)!
    assert.ok(Date.parse(o.start) >= Date.parse(slot.start), 'offer starts before its window')
    assert.ok(Date.parse(o.end) <= Date.parse(slot.end), 'offer runs past its window')
    assert.ok(Date.parse(o.start) >= Date.parse(now), 'offer starts in the past')
  }
  const starts = offers.map((o) => Date.parse(o.start))
  assert.deepEqual(starts, [...starts].sort((a, b) => a - b), 'offers came back out of order')
}

// 7. pricing. The fee is inside the total, and the split always reconciles.
{
  for (const req of [saw, brackets]) {
    for (const l of listings) {
      const q = quoteFor(req, l)
      if (!q) continue
      assert.equal(q.base + q.extra, q.total, 'quote does not add up')
      assert.equal(q.platformFee + q.ownerNet, q.total, 'split does not reconcile')
      assert.equal(q.platformFee, Math.round((q.total * PLATFORM_FEE_BPS) / 10_000))
      assert.ok(Number.isInteger(q.total), 'money must stay in whole cents')
    }
  }
  const drill = quoteFor(saw, listing('l8'))!
  assert.equal(drill.hours, 2)
  assert.equal(drill.total, 2 * 250)
}

// 8. batch hours come from throughput, not from the buyer.
{
  const mill = listing('l20')
  assert.ok(isBatch(mill))
  const h = hoursFor(brackets, mill)!
  assert.equal(h, mill.setupHours + 500 / mill.unitsPerHour)
}

// 9. sorting does what it says.
{
  const m = findMatches(brackets, world, now)
  const byPrice = sortMatches(m, 'price')
  assert.deepEqual(
    byPrice.map((x) => x.quote.total),
    [...byPrice.map((x) => x.quote.total)].sort((a, b) => a - b),
  )
  const bySoon = sortMatches(m, 'soonest')
  assert.deepEqual(
    bySoon.map((x) => Date.parse(x.start)),
    [...bySoon.map((x) => Date.parse(x.start))].sort((a, b) => a - b),
  )
}

// 10. THE LOOP. A completed, on-time, five-star booking must lift the owner above
//      an otherwise identical one with no record. If this breaks, the whole
//      "outcomes compound" argument breaks with it.
{
  const twin = (id: string, rated: boolean): Owner => ({
    ...owner('b2'),
    id,
    name: id,
    ratingSum: rated ? 25 : 0,
    jobsDone: rated ? 5 : 0,
    onTimeJobs: rated ? 5 : 0,
  })
  const base = listing('l20')
  assert.ok(isBatch(base))
  const w: World = {
    owners: [twin('rated', true), twin('unrated', false)],
    listings: [
      { ...base, id: 'lA', ownerId: 'rated' },
      { ...base, id: 'lB', ownerId: 'unrated' },
    ],
    slots: [
      { id: 'sA', listingId: 'lA', start: plus(24), end: plus(24 * 6), hoursUsable: 90 },
      { id: 'sB', listingId: 'lB', start: plus(24), end: plus(24 * 6), hoursUsable: 90 },
    ],
    districts,
    reviews: [],
  }
  const m = findMatches(brackets, w, now)
  assert.equal(m.length, 2, 'expected both twins to match')
  assert.equal(m[0].ownerId, 'rated', 'a clean record did not lift the ranking')
}

// 11. the same loop on the real seed, in both booking modes. A five-star, on-time
//      booking can never make an owner worse off: their trust score must not fall
//      and their position must not slip. (Whether it overtakes a specific rival
//      depends on the gap, check 10 is the clean statement of the mechanism.)
for (const [label, req] of [
  ['everyday', saw],
  ['industry', brackets],
] as const) {
  const before = findMatches(req, world, now)
  assert.ok(before.length >= 2, `${label}: need two options to compare order`)
  const target = before[1].ownerId
  const wasAt = before.findIndex((m) => m.ownerId === target)

  const rated: World = {
    ...world,
    owners: world.owners.map((o) =>
      o.id === target ? applyOutcome(o, { onTime: true, quality: 5 }) : o,
    ),
  }
  const after = findMatches(req, rated, now)
  const nowAt = after.findIndex((m) => m.ownerId === target)

  assert.ok(
    trustOf(owner(target)) <= trustOf(rated.owners.find((o) => o.id === target)!),
    `${label}: a clean booking lowered the owner's trust score`,
  )
  assert.ok(nowAt >= 0 && nowAt <= wasAt, `${label}: a clean booking pushed the owner down`)
}

// 12. copy that gets rendered must be grammatical at the boundaries.
{
  assert.match(trackRecord({ ...owner('o1'), jobsDone: 1, onTimeJobs: 1 }), /^1 booking · /)
  assert.match(trackRecord({ ...owner('o1'), jobsDone: 2, onTimeJobs: 1 }), /^2 bookings · 50% /)
  assert.equal(trackRecord({ ...owner('o1'), jobsDone: 0, onTimeJobs: 0 }), 'New on Cappy')
}

// 13. the headline number. It must never exceed what the windows physically hold,
//      must grow with radius, and must price at the owners' own rates.
{
  const near = idleNearby(world, 'Kreuzberg', 5, now, 24)
  const wide = idleNearby(world, 'Kreuzberg', 90, now, 24)
  assert.ok(near.hours > 0, 'no idle capacity found nearby')
  assert.ok(wide.hours >= near.hours, 'a wider radius found less capacity')
  assert.ok(wide.listings >= near.listings)
  assert.ok(near.freeNowCount <= near.listings, 'more live than listed')
  assert.ok(near.owners <= near.listings, 'more owners than listings')
  // A 24-hour horizon cannot surface more than 24 hours per listing.
  assert.ok(near.hours <= near.listings * 24 + 1e-6, 'headline exceeds what a day holds')
  assert.ok(Number.isInteger(near.value), 'headline value must be whole cents')
  const future = idleNearby(world, 'Kreuzberg', 5, plus(24 * 365), 24)
  assert.equal(future.hours, 0, 'found idle capacity a year after the seed window')
}

// 14. every listing must be bookable at its own minimum. A window listing whose
//      longest idle block is shorter than its own minimum booking can never be
//      booked by anyone, it is dead inventory that still shows in the catalogue.
{
  for (const l of listings) {
    if (!l.active) continue
    const mine = slots.filter((s) => s.listingId === l.id)
    assert.ok(mine.length > 0, `${l.id} (${l.title}) has no idle windows at all`)

    const need = l.mode === 'window' ? l.minHours : l.setupHours + 1
    const longest = Math.max(...mine.map((s) => s.hoursUsable))
    assert.ok(
      longest >= need,
      `${l.id} (${l.title}) needs ${need}h minimum but its longest window is ${longest}h`,
    )
  }
}

// 15. Europe. Every seeded city must carry real capacity, every district must
//      name a city and a country, and the continent total must be the sum of
//      its cities rather than a separate calculation that can drift.
{
  for (const d of Object.values(districts)) {
    assert.ok(d.city, `district ${d.name} has no city`)
    assert.match(d.country, /^[A-Z]{2}$/, `district ${d.name} has no ISO country`)
  }

  const list = cities(world, now)
  assert.ok(list.length >= 5, `expected at least five cities, got ${list.length}`)
  for (const c of list) {
    assert.ok(c.listings > 0, `${c.city} appears with no listings`)
    assert.ok(Number.isFinite(c.lat) && Number.isFinite(c.lng), `${c.city} has no centre`)
  }
  // Busiest first.
  const hours = list.map((c) => c.idle.hours)
  assert.deepEqual(hours, [...hours].sort((a, b) => b - a), 'cities came back unsorted')

  const europe = idleEurope(world, now)
  assert.ok(
    Math.abs(europe.hours - hours.reduce((a, b) => a + b, 0)) < 1e-6,
    'the Europe total does not match the sum of its cities',
  )
  assert.ok(europe.hours > idleNearby(world, 'Kreuzberg', 5, now, 24).hours, 'Europe is smaller than Kreuzberg')
  // Every market must show real capacity over a week, or it reads as broken.
  for (const c of list) {
    assert.ok(c.idle.hours > 0, `${c.city} has listings but no capacity this week`)
  }
}

// 16. turning a real GPS fix into a market. A coordinate sitting on a district
//      must resolve to that district, a coordinate in another of our cities must
//      resolve there rather than to the biggest market, and somewhere we do not
//      serve must come back with a distance large enough for the UI to notice.
{
  const at = (name: string) => {
    const d = districts[name]
    return nearestDistrict(world, d.lat, d.lng)
  }
  assert.equal(at('Kreuzberg')?.district.name, 'Kreuzberg')
  assert.ok((at('Kreuzberg')?.km ?? 99) < 0.001, 'a district did not resolve to itself')
  assert.equal(at('Navigli')?.district.metro, 'Milan')
  assert.equal(at('Marvila')?.district.metro, 'Lisbon')

  // Someone in central Paris gets Paris, not Berlin.
  assert.equal(nearestDistrict(world, 48.8566, 2.3522)?.district.metro, 'Paris')
  // Someone in Hamburg gets the closest market, but far enough to warn about.
  const hamburg = nearestDistrict(world, 53.5511, 9.9937)!
  assert.ok(hamburg.km > 200, `Hamburg resolved only ${hamburg.km.toFixed(0)} km away`)
  // Never null while any district exists.
  assert.ok(nearestDistrict(world, 0, 0) !== null)
}

// --- readout, so seed tuning is done against real numbers ------------------
for (const [label, req] of [
  ['WINDOW  2 h of a saw near Kreuzberg', saw],
  ['BATCH   500 alu brackets ±0.05', brackets],
] as const) {
  console.log(`\n${label}`)
  const m = findMatches(req, world, now)
  if (!m.length) console.log('  no capacity')
  for (const x of m) {
    const l = listing(x.listingId)
    const o = owner(x.ownerId)
    console.log(
      `  ${x.score.toFixed(3)}  ${o.name.padEnd(24)} ${l.title.slice(0, 26).padEnd(27)}` +
        `${formatEur(x.quote.total).padStart(9)}  ${x.start.slice(5, 16).replace('T', ' ')}  ` +
        `${x.distanceKm.toFixed(1)}km`,
    )
  }
}

const head = idleNearby(world, 'Kreuzberg', 5, now, 24)
console.log(
  `\nheadline: ${Math.round(head.hours)} idle hours · ${formatEur(head.value)} unclaimed ` +
    `· ${head.listings} listings · ${head.freeNowCount} free right now (5 km, 24 h)`,
)
const eu = idleEurope(world, now)
console.log(
  `europe:   ${Math.round(eu.hours)} idle hours · ${formatEur(eu.value)} unclaimed across ` +
    `${cities(world, now, 24).length} cities`,
)
for (const c of cities(world, now)) {
  console.log(
    `  ${c.city.padEnd(10)} ${c.country}  ${String(c.listings).padStart(2)} listing${c.listings === 1 ? ' ' : 's'}  ` +
      `${String(Math.round(c.idle.hours)).padStart(4)} h  ${formatEur(c.idle.value).padStart(11)}`,
  )
}
console.log(`${listings.length} listings · ${owners.length} owners · ${slots.length} idle windows`)
// 13. reviews tell the same story as the record they were written from.
{
  const vocab = new Set<string>(REVIEW_TAGS)
  for (const o of owners) {
    const mine = reviews.filter((r) => r.ownerId === o.id)
    if (o.jobsDone === 0) {
      assert.equal(mine.length, 0, `${o.id} has no jobs but has reviews`)
      continue
    }
    const s = summarise(mine)
    const avg = o.ratingSum / o.jobsDone
    assert.ok(s.average !== null && Math.abs(s.average - avg) <= 1, `${o.id} reviews disagree with its rating`)
    for (const lid of new Set(mine.map((r) => r.listingId))) {
      const texts = mine.filter((r) => r.listingId === lid).map((r) => r.text)
      assert.equal(new Set(texts).size, texts.length, `${lid} repeats a review`)
    }
    for (const r of mine) {
      assert.ok(r.rating >= 1 && r.rating <= 5, 'rating out of range')
      for (const t of r.tags) assert.ok(vocab.has(t), `unknown tag ${t}`)
    }
  }
  assert.deepEqual(summarise([]), { count: 0, average: null, onTimeShare: null, topTags: [] })
}

console.log('all checks passed')
