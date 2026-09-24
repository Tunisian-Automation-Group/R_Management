// Exports the frontend's seed (cappy/src/data/seed.ts) as JSON fixtures for the
// catalog service, so the backend ships exactly the same demo world.
//
// Slot and review times are stored as hour offsets from local midnight on the
// export day ("startHour": 42 = tomorrow 18:00, "atHour": -480 = twenty days
// ago), and the catalog seeder rebuilds real timestamps from *its* midnight.
// That keeps the demo world fresh forever, which is the same trick the frontend
// plays with `at(day, hour)`.
//
//   node scripts/export-seed.mjs ../cappy/cappy > libs/cappy_common/cappy_common/fixtures/seed.json
//
// Needs Node 22.18+ (type stripping), which is what the frontend needs anyway.
import { pathToFileURL } from 'node:url'
import { resolve } from 'node:path'

const root = process.argv[2] ?? '../cappy/cappy'
const seed = await import(pathToFileURL(resolve(root, 'src/data/seed.ts')).href)

const base = new Date()
base.setHours(0, 0, 0, 0)
const hoursFromBase = (iso) => (Date.parse(iso) - base.getTime()) / 3_600_000

const out = {
  me: seed.ME,
  homeDistrict: seed.HOME_DISTRICT,
  districts: Object.values(seed.districts),
  owners: seed.owners,
  listings: seed.listings,
  slots: seed.slots.map((s) => ({
    id: s.id,
    listingId: s.listingId,
    startHour: hoursFromBase(s.start),
    endHour: hoursFromBase(s.end),
    hoursUsable: s.hoursUsable,
  })),
  reviews: seed.reviews.map(({ at, ...r }) => ({ ...r, atHour: hoursFromBase(at) })),
}
process.stdout.write(JSON.stringify(out, null, 2) + '\n')
