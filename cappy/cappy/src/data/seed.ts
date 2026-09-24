import type {
  BatchListing,
  Booking,
  CategoryId,
  Cents,
  District,
  Listing,
  Owner,
  Slot,
  WindowListing,
  WindowRequest,
} from '../domain/types.ts'
import { matchForOffer } from '../domain/match.ts'
import { earliestOffer } from '../domain/availability.ts'
import { category } from '../domain/categories.ts'
import type { CategoryGroup, Review } from '../domain/types.ts'

// Windows are generated relative to today, so the app never shows stale dates.
const base = new Date()
base.setHours(0, 0, 0, 0)

const at = (day: number, hour: number): string =>
  new Date(base.getTime() + day * 86_400_000 + hour * 3_600_000).toISOString()

let slotSeq = 0

/** One idle window. `usable` defaults to wall-clock hours, which is right for
 *  anything a person books directly; factory gaps override it. */
function win(listingId: string, day: number, fromH: number, toH: number, usable?: number): Slot {
  return {
    id: `w${++slotSeq}`,
    listingId,
    start: at(day, fromH),
    end: at(day, toH),
    hoursUsable: usable ?? toH - fromH,
  }
}

/** The same window on several days, how most idle time actually behaves. */
const recur = (listingId: string, days: number[], fromH: number, toH: number, usable?: number) =>
  days.map((d) => win(listingId, d, fromH, toH, usable))

const WEEK = [0, 1, 2, 3, 4, 5, 6]

const place = (
  name: string,
  city: string,
  metro: string,
  country: string,
  lat: number,
  lng: number,
): District => ({ name, city, metro, country, lat, lng })

/** Eurozone only, so every price on the platform is in euros and nothing needs
 *  converting. Berlin is the densest market; the rest are real neighbourhoods and
 *  real manufacturing clusters. */
export const districts: Record<string, District> = Object.fromEntries(
  [
    // --- Berlin, and the Brandenburg industry around it
    place('Kreuzberg', 'Berlin', 'Berlin', 'DE', 52.4987, 13.418),
    place('Neukölln', 'Berlin', 'Berlin', 'DE', 52.4811, 13.4353),
    place('Mitte', 'Berlin', 'Berlin', 'DE', 52.5219, 13.4038),
    place('Wedding', 'Berlin', 'Berlin', 'DE', 52.5503, 13.34),
    place('Friedrichshain', 'Berlin', 'Berlin', 'DE', 52.5155, 13.454),
    place('Moabit', 'Berlin', 'Berlin', 'DE', 52.53, 13.34),
    place('Prenzlauer Berg', 'Berlin', 'Berlin', 'DE', 52.54, 13.424),
    place('Tempelhof', 'Berlin', 'Berlin', 'DE', 52.4675, 13.3903),
    place('Treptow', 'Berlin', 'Berlin', 'DE', 52.4937, 13.4569),
    place('Pankow', 'Berlin', 'Berlin', 'DE', 52.5692, 13.4017),
    place('Spandau', 'Berlin', 'Berlin', 'DE', 52.535, 13.2),
    place('Potsdam', 'Potsdam', 'Berlin', 'DE', 52.3906, 13.0645),
    place('Ludwigsfelde', 'Ludwigsfelde', 'Berlin', 'DE', 52.302, 13.254),
    place('Oranienburg', 'Oranienburg', 'Berlin', 'DE', 52.755, 13.236),
    place('Königs Wusterhausen', 'Königs Wusterhausen', 'Berlin', 'DE', 52.297, 13.633),
    place('Brandenburg a.d.H.', 'Brandenburg a.d.H.', 'Berlin', 'DE', 52.4125, 12.5316),
    place('Teltow', 'Teltow', 'Berlin', 'DE', 52.4026, 13.2637),
    place('Schönefeld', 'Schönefeld', 'Berlin', 'DE', 52.3878, 13.5033),

    // --- Amsterdam, and the Eindhoven high-tech cluster as its own market
    place('Jordaan', 'Amsterdam', 'Amsterdam', 'NL', 52.374, 4.879),
    place('De Pijp', 'Amsterdam', 'Amsterdam', 'NL', 52.3545, 4.8925),
    place('Oud-West', 'Amsterdam', 'Amsterdam', 'NL', 52.367, 4.868),
    place('Amsterdam-Noord', 'Amsterdam', 'Amsterdam', 'NL', 52.398, 4.91),
    place('Strijp', 'Eindhoven', 'Eindhoven', 'NL', 51.448, 5.452),

    // --- Paris, and the Lyon industrial belt as its own market
    place('Le Marais', 'Paris', 'Paris', 'FR', 48.859, 2.362),
    place('Belleville', 'Paris', 'Paris', 'FR', 48.872, 2.383),
    place('Batignolles', 'Paris', 'Paris', 'FR', 48.887, 2.32),
    place('Montreuil', 'Paris', 'Paris', 'FR', 48.863, 2.443),
    place('Vaulx-en-Velin', 'Vaulx-en-Velin', 'Lyon', 'FR', 45.777, 4.92),

    // --- Milan, and the Brescia machining valley as its own market
    place('Navigli', 'Milan', 'Milan', 'IT', 45.451, 9.174),
    place('Isola', 'Milan', 'Milan', 'IT', 45.488, 9.189),
    place('Lambrate', 'Milan', 'Milan', 'IT', 45.485, 9.238),
    place('Bovisa', 'Milan', 'Milan', 'IT', 45.503, 9.158),
    place('Lumezzane', 'Lumezzane', 'Brescia', 'IT', 45.647, 10.264),

    // --- Lisbon
    place('Arroios', 'Lisbon', 'Lisbon', 'PT', 38.73, -9.136),
    place('Marvila', 'Lisbon', 'Lisbon', 'PT', 38.74, -9.103),
    place('Alcântara', 'Lisbon', 'Lisbon', 'PT', 38.705, -9.177),
    place('Benfica', 'Lisbon', 'Lisbon', 'PT', 38.75, -9.2),
  ].map((d) => [d.name, d]),
)


const person = (
  id: string,
  name: string,
  initials: string,
  district: string,
  ratingSum: number,
  jobsDone: number,
  onTimeJobs: number,
  joinedYear: number,
  responseMins: number,
  verified = true,
): Owner => ({
  id,
  name,
  initials,
  kind: 'person',
  district,
  verified,
  ratingSum,
  jobsDone,
  onTimeJobs,
  joinedYear,
  responseMins,
})

const firm = (
  id: string,
  name: string,
  initials: string,
  district: string,
  ratingSum: number,
  jobsDone: number,
  onTimeJobs: number,
  joinedYear: number,
  responseMins: number,
): Owner => ({
  id,
  name,
  initials,
  kind: 'business',
  district,
  verified: true,
  ratingSum,
  jobsDone,
  onTimeJobs,
  joinedYear,
  responseMins,
})

/** o1 is you, the account the Earn side speaks for. */
export const ME = 'o1'

/** The batch side varies in which questions apply (a truck has no tolerance, a
 *  printer has no material list we model), so this takes named fields rather
 *  than a positional argument list nobody can read. */
const bl = (l: Omit<BatchListing, 'mode' | 'active'>): BatchListing => ({
  ...l,
  mode: 'batch',
  active: true,
})

/** Window listings are all the same shape, so the rest of Europe is written with
 *  a constructor rather than thirty more object literals. */
const wl = (
  id: string,
  ownerId: string,
  category: CategoryId,
  title: string,
  blurb: string,
  district: string,
  ratePerHour: Cents,
  minHours: number,
  maxHours: number,
  extraFee: Cents,
  extraLabel: string,
  instructions: string,
  rules: string[],
): WindowListing => ({
  id,
  ownerId,
  category,
  mode: 'window',
  title,
  blurb,
  district,
  ratePerHour,
  minHours,
  maxHours,
  extraFee,
  extraLabel,
  instructions,
  rules,
  active: true,
})

const berlinOwners: Owner[] = [
  person('o1', 'Nadia Brandt', 'NB', 'Kreuzberg', 89, 19, 18, 2025, 12),
  person('o5', 'Deniz Kaya', 'DK', 'Wedding', 71, 15, 14, 2025, 18),
  person('o11', 'Rana Yıldız', 'RY', 'Moabit', 29, 6, 6, 2025, 15),
  person('o12', 'Tobias Frei', 'TF', 'Prenzlauer Berg', 14, 3, 3, 2026, 48, false),
  person('o13', 'Jonas Reinhardt', 'JR', 'Kreuzberg', 66, 14, 13, 2024, 20),
  person('o14', 'Lea Okonkwo', 'LO', 'Neukölln', 0, 0, 0, 2026, 33),
  person('o15', 'Ana Kestner', 'AK', 'Friedrichshain', 38, 8, 7, 2025, 27),
  person('o16', 'Ferhat Aydın', 'FA', 'Spandau', 51, 11, 10, 2025, 45),
  person('o17', 'Clara Bissinger', 'CB', 'Neukölln', 33, 7, 7, 2025, 14),

  firm('b1', 'Prächtig Präzision GmbH', 'PP', 'Potsdam', 146, 30, 29, 2024, 90),
  firm('b2', 'Havel Zerspanung GmbH', 'HZ', 'Brandenburg a.d.H.', 0, 0, 0, 2026, 120),
  firm('b3', 'Metallbau Sturm GmbH', 'MS', 'Ludwigsfelde', 103, 22, 20, 2024, 110),
  firm('b4', 'Spandauer Werkstatt GmbH', 'SW', 'Spandau', 76, 17, 15, 2025, 75),
  firm('b5', 'Blechwerk Oranienburg GmbH', 'BO', 'Oranienburg', 55, 12, 11, 2025, 95),
  firm('b6', 'KW Kunststofftechnik GmbH', 'KW', 'Königs Wusterhausen', 44, 10, 9, 2025, 140),

  // Finishing. Every machined part needs one of these before it ships, and the
  // step buyers most often discover they forgot.
  firm('b7', 'Oberflächen Teltow GmbH', 'OT', 'Teltow', 92, 19, 18, 2024, 80),
  firm('b8', 'Härterei Spandau GmbH', 'HS', 'Spandau', 61, 13, 12, 2025, 105),

  // Print and signage.
  person('o18', 'Nils Krüger', 'NK', 'Neukölln', 58, 12, 12, 2025, 26),
  person('o19', 'Sarah Ebert', 'SE', 'Friedrichshain', 31, 7, 7, 2026, 19),
  firm('b9', 'Signal Druck GmbH', 'SD', 'Moabit', 84, 18, 17, 2024, 65),

  // Freight. Half a van already going somewhere is the cheapest capacity on the
  // network, and the reason a mill in Lumezzane is reachable from Kreuzberg.
  person('o20', 'Marek Zieliński', 'MZ', 'Wedding', 45, 10, 10, 2025, 23),
  firm('b10', 'Havelspedition GmbH', 'HV', 'Oranienburg', 108, 23, 22, 2024, 70),
  firm('b11', 'Nord-Süd Logistik GmbH', 'NS', 'Ludwigsfelde', 0, 0, 0, 2026, 115),

  // Warehousing.
  firm('b12', 'Lagerhaus Schönefeld GmbH', 'LS', 'Schönefeld', 73, 16, 15, 2025, 90),
  firm('b13', 'Kühlhaus Treptow GmbH', 'KT', 'Treptow', 39, 8, 8, 2025, 125),

  // One more stage rig, so the category is not a single listing.
  person('o21', 'Jule Havemann', 'JH', 'Kreuzberg', 52, 11, 11, 2025, 16),

  // ---- more supply, Berlin and Brandenburg -------------------------------
  firm('b14', 'Wasserstrahl Adlershof GmbH', 'WA', 'Treptow', 87, 18, 17, 2024, 85),
  firm('b15', 'Erodiertechnik Marzahn GmbH', 'EM', 'Königs Wusterhausen', 64, 14, 13, 2025, 100),
  firm('b16', 'Abkantwerk Velten GmbH', 'AV', 'Oranienburg', 0, 0, 0, 2026, 110),
  firm('b17', 'Rohrbiegerei Nord GmbH', 'RN', 'Spandau', 48, 10, 10, 2025, 92),
  firm('b18', 'Galvanik Lichtenberg GmbH', 'GL', 'Treptow', 79, 17, 16, 2024, 88),
  firm('b19', 'Strahltechnik Teltow GmbH', 'ST', 'Teltow', 41, 9, 8, 2025, 97),
  firm('b20', 'Kaltlager Schönefeld GmbH', 'KS', 'Schönefeld', 58, 12, 12, 2025, 105),
  firm('b21', 'Pickpack Ludwigsfelde GmbH', 'PL', 'Ludwigsfelde', 93, 20, 19, 2024, 60),
  firm('b22', 'Bogendruck Kreuzberg GmbH', 'BK', 'Kreuzberg', 71, 15, 14, 2025, 55),
  person('o22', 'Yannick Pohl', 'YP', 'Wedding', 36, 8, 8, 2025, 29),
  person('o23', 'Amira Haddad', 'AH', 'Neukölln', 61, 13, 13, 2024, 18),
  person('o24', 'Bastian Roth', 'BR', 'Pankow', 0, 0, 0, 2026, 52),
  person('o25', 'Lotte Simon', 'LT', 'Friedrichshain', 44, 9, 9, 2025, 25),
  person('o26', 'Kwame Osei', 'KO', 'Moabit', 55, 12, 11, 2025, 31),
  person('o27', 'Vera Lindner', 'VL', 'Mitte', 28, 6, 6, 2026, 41, false),
  person('o28', 'Tomás Ferreira', 'TA', 'Tempelhof', 67, 14, 14, 2024, 22),
  person('o29', 'Greta Nowak', 'GN', 'Prenzlauer Berg', 39, 8, 8, 2025, 27),
]

const berlinListings: Listing[] = [
  // ---------------------------------------------------------------- everyday
  {
    id: 'l8',
    ownerId: 'o5',
    category: 'workshop',
    mode: 'window',
    title: 'Bosch GBH 2-28 hammer drill',
    blurb: 'SDS-plus with the full bit set and a chisel.',
    district: 'Wedding',
    ratePerHour: 250,
    minHours: 2,
    maxHours: 8,
    extraFee: 0,
    extraLabel: 'No extras',
    instructions: 'Pick up from the yard on Gerichtstraße. Comes in the blue case with bits and a spare chuck.',
    rules: ['Back the same day', 'Blow the dust out of the case before returning'],
    active: true,
  },
  {
    id: 'l9',
    ownerId: 'o1',
    category: 'workshop',
    mode: 'window',
    title: 'Festool TS 55 plunge saw + 1.4 m rail',
    blurb: 'Clean straight cuts in sheet goods. Barely used.',
    district: 'Tempelhof',
    ratePerHour: 400,
    minHours: 2,
    maxHours: 8,
    extraFee: 0,
    extraLabel: 'No extras',
    instructions: 'Systainer is in the hallway cupboard. Rail is long, so bring a car or a cargo bike. It will not fit on the U-Bahn.',
    rules: ['Fresh blade stays on the saw', 'Use it with a vacuum, it makes a mess otherwise'],
    active: true,
  },
  {
    id: 'l12',
    ownerId: 'o11',
    category: 'events',
    mode: 'window',
    title: 'L-Acoustics A10 PA + DMX rig',
    blurb: 'Two tops, two subs, desk and eight lights.',
    district: 'Moabit',
    ratePerHour: 1200,
    minHours: 8,
    maxHours: 72,
    extraFee: 8000,
    extraLabel: 'Load-out, cabling and a spare desk',
    instructions: 'Flightcased and on wheels. Load-out from the rehearsal room on Beusselstraße. You need a van rather than a car.',
    rules: ['Indoor use unless you have cover', 'Return in the same cases', 'Damage deposit agreed before pickup'],
    active: true,
  },
  {
    id: 'l13',
    ownerId: 'o12',
    category: 'creator',
    mode: 'window',
    title: 'Canon C400 + Aputure 600x',
    blurb: 'Body, three primes, light and stands. Between shoots.',
    district: 'Prenzlauer Berg',
    ratePerHour: 1500,
    minHours: 8,
    maxHours: 72,
    extraFee: 0,
    extraLabel: 'No extras',
    instructions: 'Two Pelicases and a light stand bag. Cards are formatted before handover, so copy your rushes before you return it.',
    rules: ['Insurance confirmation before pickup', 'No rain without the cover', 'Batteries returned charged'],
    active: true,
  },
  {
    id: 'l14',
    ownerId: 'o16',
    category: 'workshop',
    mode: 'window',
    title: 'Woodworking bench with vices',
    blurb: 'Heated workshop, dust extraction, decent light.',
    district: 'Spandau',
    ratePerHour: 600,
    minHours: 2,
    maxHours: 10,
    extraFee: 0,
    extraLabel: 'No extras',
    instructions: 'Unit 4 at the back of the yard. Bench is 2.1 m with a tail vice; extraction and clamps are shared, hand tools are not.',
    rules: ['Bring your own blades and bits', 'Sweep down at the end', 'Ear protection provided, please use it'],
    active: true,
  },
  {
    id: 'l15',
    ownerId: 'o17',
    category: 'creator',
    mode: 'window',
    title: 'Treated studio room',
    blurb: '14 m², absorbers, no traffic noise. Vocals or podcasts.',
    district: 'Neukölln',
    ratePerHour: 1400,
    minHours: 2,
    maxHours: 10,
    extraFee: 0,
    extraLabel: 'No extras',
    instructions: 'Rear building, third floor. Interface and two mics stay in the room; bring your own laptop and headphones.',
    rules: ['No food in the live room', 'Last session ends 21:30', 'Leave the patchbay as you found it'],
    active: true,
  },

  // ------------------------------------------------- batch: makers + industry
  {
    id: 'l16',
    ownerId: 'o13',
    category: 'additive',
    mode: 'batch',
    title: 'Prusa MK4S ×3',
    blurb: 'Three machines running unattended overnight.',
    district: 'Kreuzberg',
    machine: 'Prusa MK4S ×3',
    materials: ['PLA', 'PETG', 'ABS', 'ASA', 'TPU'],
    maxDims: { x: 250, y: 210, z: 220 },
    toleranceMm: 0.3,
    unitsPerHour: 0.9,
    setupHours: 0.5,
    ratePerHour: 900,
    setupFee: 1200,
    instructions: 'Send STL or STEP. I slice and confirm orientation with you before the first layer.',
    rules: ['No files under NDA without a signed copy first', 'Supports removed, no post-processing'],
    active: true,
  },
  {
    id: 'l17',
    ownerId: 'o14',
    category: 'additive',
    mode: 'batch',
    title: 'Bambu Lab X1C',
    blurb: 'Fast, enclosed, AMS for multi-material. New here.',
    district: 'Neukölln',
    machine: 'Bambu Lab X1C',
    materials: ['PLA', 'PETG', 'ABS'],
    maxDims: { x: 256, y: 256, z: 256 },
    toleranceMm: 0.25,
    unitsPerHour: 0.75,
    setupHours: 0.25,
    ratePerHour: 750,
    setupFee: 600,
    instructions: 'STL or 3MF. I am pricing low while I build up reviews. Tell me if the deadline is tight and I will run it overnight.',
    rules: ['Pickup only, Weserstraße', 'No food-contact parts'],
    active: true,
  },
  {
    id: 'l18',
    ownerId: 'o15',
    category: 'fabrication',
    mode: 'batch',
    title: 'xTool P2S 55W',
    blurb: 'Acrylic and ply up to 10 mm, 600 × 300 bed.',
    district: 'Friedrichshain',
    machine: 'xTool P2S 55W',
    materials: ['Acrylic', 'Plywood'],
    maxDims: { x: 600, y: 308, z: 10 },
    toleranceMm: 0.2,
    unitsPerHour: 12,
    setupHours: 0.5,
    ratePerHour: 2500,
    setupFee: 2000,
    instructions: 'Vector files as SVG or DXF, outlines only, no strokes. I nest them for you.',
    rules: ['No PVC or anything chlorinated', 'Material can be yours or mine'],
    active: true,
  },
  {
    id: 'l19',
    ownerId: 'b1',
    category: 'fabrication',
    mode: 'batch',
    title: 'DMG Mori DMU 50 (5-axis)',
    blurb: 'Tight-tolerance alloy work. Gap opens most weeks.',
    district: 'Potsdam',
    machine: 'DMG Mori DMU 50 (5-axis)',
    materials: ['Aluminium 6061', 'Aluminium 7075', 'Stainless 304', 'POM'],
    maxDims: { x: 500, y: 450, z: 400 },
    toleranceMm: 0.02,
    unitsPerHour: 12,
    setupHours: 2.5,
    ratePerHour: 11000,
    setupFee: 24000,
    instructions: 'STEP plus a dimensioned PDF. We confirm fixturing and first-article before the run.',
    rules: ['First-article inspection included', 'Material certs on request', 'Minimum order €400'],
    active: true,
  },
  {
    id: 'l20',
    ownerId: 'b2',
    category: 'fabrication',
    mode: 'batch',
    title: 'Haas VF-2SS',
    blurb: '3-axis, fast spindle. Two shifts free this month.',
    district: 'Brandenburg a.d.H.',
    machine: 'Haas VF-2SS',
    materials: ['Aluminium 6061', 'Steel S235', 'POM'],
    maxDims: { x: 762, y: 406, z: 508 },
    toleranceMm: 0.05,
    unitsPerHour: 9,
    setupHours: 2,
    ratePerHour: 7800,
    setupFee: 15000,
    instructions: 'STEP or Parasolid. We are new to Cappy and quoting keenly to get the first jobs through.',
    rules: ['Deburred as standard', 'Anodising subcontracted, adds 5 days'],
    active: true,
  },
  {
    id: 'l21',
    ownerId: 'b3',
    category: 'fabrication',
    mode: 'batch',
    title: 'DMG Mori NLX 2500',
    blurb: 'Bar work to Ø 80. Reliable, well maintained.',
    district: 'Ludwigsfelde',
    machine: 'DMG Mori NLX 2500',
    materials: ['Aluminium 6061', 'Stainless 304', 'Brass'],
    maxDims: { x: 366, y: 366, z: 705 },
    toleranceMm: 0.02,
    unitsPerHour: 15,
    setupHours: 2,
    ratePerHour: 7500,
    setupFee: 18000,
    instructions: 'Drawing with tolerances and surface finish. We quote back within a working day.',
    rules: ['Minimum order €300', 'Thread gauging on request'],
    active: true,
  },
  {
    id: 'l22',
    ownerId: 'b4',
    category: 'fabrication',
    mode: 'batch',
    title: 'Haas ST-20',
    blurb: 'Short runs and prototypes, quick turnaround.',
    district: 'Spandau',
    machine: 'Haas ST-20',
    materials: ['Aluminium 6061', 'Brass', 'Steel S235'],
    maxDims: { x: 356, y: 356, z: 508 },
    toleranceMm: 0.03,
    unitsPerHour: 12,
    setupHours: 1.5,
    ratePerHour: 6800,
    setupFee: 14000,
    instructions: 'Happy with a sketch for one-offs. Production runs need a proper drawing.',
    rules: ['No hardened steel', 'Collect from Spandau or we ship at cost'],
    active: true,
  },
  {
    id: 'l23',
    ownerId: 'b5',
    category: 'fabrication',
    mode: 'batch',
    title: 'Trumpf TruLaser 3030',
    blurb: 'Sheet up to 3 × 1.5 m. Bending in house.',
    district: 'Oranienburg',
    machine: 'Trumpf TruLaser 3030',
    materials: ['Steel S235', 'Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 3000, y: 1500, z: 25 },
    toleranceMm: 0.2,
    unitsPerHour: 45,
    setupHours: 1,
    ratePerHour: 9000,
    setupFee: 12000,
    instructions: 'Flat patterns as DXF. Tell us the bend allowance you assumed or we will use ours.',
    rules: ['Powder coating subcontracted', 'Offcuts kept unless you ask'],
    active: true,
  },
  {
    id: 'l24',
    ownerId: 'b6',
    category: 'fabrication',
    mode: 'batch',
    title: 'Arburg Allrounder 470 H',
    blurb: 'Press time for short runs. You bring the tool.',
    district: 'Königs Wusterhausen',
    machine: 'Arburg Allrounder 470 H',
    materials: ['ABS', 'POM', 'PLA'],
    maxDims: { x: 150, y: 150, z: 150 },
    toleranceMm: 0.1,
    unitsPerHour: 120,
    setupHours: 4,
    ratePerHour: 8500,
    setupFee: 45000,
    instructions: 'Existing tool only. We do not cut tooling. Send the tool drawing and shot weight.',
    rules: ['Tool inspected before first shot', 'Material supplied by us unless agreed'],
    active: true,
  },

  // ------------------------------------------------------------- finishing
  bl({
    id: 'l25',
    ownerId: 'b7',
    category: 'finishing',
    title: 'Powder coating line',
    blurb: 'RAL to order, chromate-free pretreatment. Gaps on Tuesdays and Fridays.',
    district: 'Teltow',
    machine: 'Wagner powder line, 6 m oven',
    materials: ['Aluminium 6061', 'Aluminium 7075', 'Steel S235', 'Stainless 304'],
    maxDims: { x: 2000, y: 1200, z: 800 },
    unitsPerHour: 58,
    setupHours: 1.5,
    ratePerHour: 4800,
    setupFee: 9000,
    instructions: 'Parts degreased and free of oil. Tell us the RAL and the gloss level, and mask anything that must stay bare.',
    rules: ['Masking charged separately', 'No galvanised stock', 'Minimum order €120'],
  }),
  bl({
    id: 'l26',
    ownerId: 'b8',
    category: 'finishing',
    title: 'Vacuum hardening furnace',
    blurb: 'Through-hardening and tempering to spec. Charge runs most nights.',
    district: 'Spandau',
    machine: 'Ipsen TurboTreater',
    materials: ['Steel S235', 'Stainless 304'],
    maxDims: { x: 600, y: 600, z: 900 },
    unitsPerHour: 110,
    setupHours: 3,
    ratePerHour: 5600,
    setupFee: 14000,
    instructions: 'Give us the grade and the target hardness in HRC. Certificate issued per charge, not per part.',
    rules: ['Hardness certificate included', 'Distortion is not warranted on thin sections'],
  }),

  // --------------------------------------------------------- print & signage
  bl({
    id: 'l27',
    ownerId: 'o18',
    category: 'print',
    title: 'Roland VG3-640 large format',
    blurb: '1.6 m eco-solvent with cut. Idle most of the week between club jobs.',
    district: 'Neukölln',
    machine: 'Roland TrueVIS VG3-640',
    maxDims: { x: 1600, y: 20000, z: 1 },
    unitsPerHour: 9,
    setupHours: 0.5,
    ratePerHour: 3200,
    setupFee: 1800,
    instructions: 'PDF with 3 mm bleed and outlined type. I proof one metre before running the rest.',
    rules: ['Pickup only', 'Laminating adds a day', 'Colour matched by eye unless you send a reference'],
  }),
  bl({
    id: 'l28',
    ownerId: 'o19',
    category: 'print',
    title: 'DTF garment press',
    blurb: 'Direct-to-film transfers and a 40×50 press. Good for runs of 20 to 500.',
    district: 'Friedrichshain',
    machine: 'Prestige A3+ DTF + Secabo TC7',
    maxDims: { x: 400, y: 500, z: 1 },
    unitsPerHour: 42,
    setupHours: 0.4,
    ratePerHour: 2400,
    setupFee: 1500,
    instructions: 'PNG at 300 dpi on transparent, actual size. Bring the garments; I do not stock blanks.',
    rules: ['No polyester below 160 g', 'Wash test on request', 'Garments counted on arrival'],
  }),
  bl({
    id: 'l29',
    ownerId: 'b9',
    category: 'print',
    title: 'Zünd cutter + UV flatbed',
    blurb: 'Rigid signage to 3 m: dibond, foamex, acrylic. Second shift usually open.',
    district: 'Moabit',
    machine: 'Zünd G3 + swissQprint Nyala',
    materials: ['Acrylic', 'Plywood'],
    maxDims: { x: 3200, y: 2000, z: 50 },
    unitsPerHour: 16,
    setupHours: 1,
    ratePerHour: 6400,
    setupFee: 7500,
    instructions: 'Artwork and cut path on separate layers, cut path as a spot colour named CutContour.',
    rules: ['Substrate at cost unless you supply it', 'Offcuts kept unless you ask'],
  }),

  // ----------------------------------------------------------------- freight
  bl({
    id: 'l30',
    ownerId: 'o20',
    category: 'freight',
    title: 'Sprinter, Berlin to the Ruhr',
    blurb: 'I run this Thursday anyway. Three pallet spaces go begging every week.',
    district: 'Wedding',
    machine: 'Mercedes Sprinter L3H2, tail lift',
    maxDims: { x: 1200, y: 800, z: 1700 },
    unitsPerHour: 0.75,
    setupHours: 1.2,
    ratePerHour: 3900,
    setupFee: 3500,
    instructions: 'Palletised and wrapped, or it does not go on. I send a photo at pickup and at drop.',
    rules: ['No hazardous goods', 'Tail lift, no forklift at my end', 'Max 600 kg per pallet'],
  }),
  bl({
    id: 'l31',
    ownerId: 'b10',
    category: 'freight',
    title: '7.5 t box truck, Berlin–Hamburg',
    blurb: 'Scheduled run, Monday and Wednesday. Spare space sold by the pallet.',
    district: 'Oranienburg',
    machine: 'MAN TGL 7.5 t, 18 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 2200 },
    unitsPerHour: 1.6,
    setupHours: 1.5,
    ratePerHour: 5200,
    setupFee: 4800,
    instructions: 'Booking closes 16:00 the day before. Delivery note travels with the goods.',
    rules: ['ADR limited quantities only', 'Forklift both ends', 'Max 1,000 kg per pallet'],
  }),
  bl({
    id: 'l32',
    ownerId: 'b11',
    category: 'freight',
    title: 'Groupage trailer, Berlin–Milan',
    blurb: 'Weekly southbound trailer via Munich. Consolidates part loads for the valley.',
    district: 'Ludwigsfelde',
    machine: 'Curtainsider, 33 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 2400 },
    unitsPerHour: 0.9,
    setupHours: 2.5,
    ratePerHour: 6100,
    setupFee: 9500,
    instructions: 'Departs Thursday night, unloads Lumezzane and Milan on Monday. CMR raised at loading.',
    rules: ['Palletised only', 'Customs not applicable inside the EU', 'Insurance at CMR limits unless upgraded'],
  }),

  // ------------------------------------------------------------- warehousing
  wl('l33', 'b12', 'warehousing', 'Dry pallet space, Schönefeld', 'Racked, alarmed, 1,400 spaces. Usually 80 free.', 'Schönefeld', 9, 24, 2160, 1200, 'Inbound handling per pallet', 'Gate 4, goods in until 17:00. Book a slot or you will queue behind the scheduled traffic.', ['Palletised and wrapped', 'No food or hazardous goods', 'Stock report emailed weekly']),
  wl('l34', 'b13', 'warehousing', 'Cold store at −18 °C', 'Blast-frozen or chilled, HACCP audited. Space frees up after the seasonal peak.', 'Treptow', 34, 24, 1440, 2500, 'Blast freezing per pallet', 'Docks 1 and 2 are refrigerated. Bring your own pallets; we do not exchange.', ['Temperature log provided', 'No unwrapped goods', 'Minimum one week']),


  // ---------------------------------------------- more fabrication variants
  bl({
    id: 'l36', ownerId: 'b14', category: 'fabrication',
    title: 'Waterjet, 3 m bed',
    blurb: 'Abrasive waterjet. No heat-affected zone, so it cuts what a laser cannot.',
    district: 'Treptow', machine: 'Flow Mach 500, 3000 × 1500',
    materials: ['Aluminium 6061', 'Stainless 304', 'Steel S235', 'Acrylic', 'Plywood'],
    maxDims: { x: 3000, y: 1500, z: 150 }, toleranceMm: 0.1,
    unitsPerHour: 22, setupHours: 0.8, ratePerHour: 7400, setupFee: 6500,
    instructions: 'DXF with closed contours. Tell us the edge quality you need, Q3 is the default.',
    rules: ['Taper compensation on request', 'Garnet included', 'Minimum order €150'],
  }),
  bl({
    id: 'l37', ownerId: 'b15', category: 'fabrication',
    title: 'Wire EDM, ±0.005 mm',
    blurb: 'Submerged wire erosion for hardened tool steel and tight-tolerance profiles.',
    district: 'Königs Wusterhausen', machine: 'Sodick ALN400G',
    materials: ['Steel S235', 'Stainless 304', 'Brass'],
    maxDims: { x: 400, y: 300, z: 250 }, toleranceMm: 0.005,
    unitsPerHour: 3.5, setupHours: 2.2, ratePerHour: 11500, setupFee: 24000,
    instructions: 'Hardened stock preferred. Start holes drilled by us unless you supply them.',
    rules: ['First article measured', 'Wire included', 'Minimum order €500'],
  }),
  bl({
    id: 'l38', ownerId: 'b16', category: 'fabrication',
    title: 'Press brake, 3 m',
    blurb: 'Folding to 3 m with offline programming. New here, quoting keenly.',
    district: 'Oranienburg', machine: 'Trumpf TruBend 5130',
    materials: ['Steel S235', 'Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 3000, y: 1500, z: 12 }, toleranceMm: 0.3,
    unitsPerHour: 52, setupHours: 1, ratePerHour: 6600, setupFee: 8000,
    instructions: 'Flat pattern plus a 3D step so we can check the bend sequence for collisions.',
    rules: ['Bend radius per our tooling unless agreed', 'Scratch-free on request, adds cost'],
  }),
  bl({
    id: 'l39', ownerId: 'b17', category: 'fabrication',
    title: 'CNC tube bending',
    blurb: 'Mandrel bending to 60 mm OD. Frames, handrails, roll cages.',
    district: 'Spandau', machine: 'BLM E-Turn 40',
    materials: ['Steel S235', 'Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 4000, y: 600, z: 600 }, toleranceMm: 0.5,
    unitsPerHour: 34, setupHours: 1.6, ratePerHour: 5900, setupFee: 11000,
    instructions: 'Send the centreline as a step file. We will tell you which bends need a different die.',
    rules: ['Tube supplied by you or at cost', 'Springback compensated on the first article'],
  }),

  // --------------------------------------------------- more 3D printing kit
  bl({
    id: 'l40', ownerId: 'o22', category: 'additive',
    title: 'Formlabs Form 4L resin',
    blurb: 'Large-format resin for smooth prototypes and castable patterns.',
    district: 'Wedding', machine: 'Formlabs Form 4L',
    materials: ['Resin'], maxDims: { x: 335, y: 200, z: 300 }, toleranceMm: 0.15,
    unitsPerHour: 1.2, setupHours: 0.6, ratePerHour: 1900, setupFee: 2200,
    instructions: 'STL or 3MF. I wash and cure everything before pickup; supports removed unless you ask.',
    rules: ['Pickup only', 'Resin parts are not UV stable outdoors', 'No food contact'],
  }),
  bl({
    id: 'l41', ownerId: 'b21', category: 'additive',
    title: 'HP Multi Jet Fusion, PA12',
    blurb: 'Nylon SLS in production quantities. Full build or shared with other jobs.',
    district: 'Ludwigsfelde', machine: 'HP Jet Fusion 5200',
    materials: ['PLA', 'PETG', 'ABS'], maxDims: { x: 380, y: 284, z: 380 }, toleranceMm: 0.2,
    unitsPerHour: 14, setupHours: 2.5, ratePerHour: 7800, setupFee: 9800,
    instructions: 'Nest-ready STEP or STL. Shared builds ship when the bed fills, usually within three days.',
    rules: ['Grey dyeing included', 'Shared builds are cheaper and slower', 'Minimum order €200'],
  }),
  bl({
    id: 'l42', ownerId: 'o23', category: 'additive',
    title: 'Bambu H2D, two colour',
    blurb: 'Fast FDM with a second extruder. Good for signage letters and jigs.',
    district: 'Neukölln', machine: 'Bambu Lab H2D',
    materials: ['PLA', 'PETG', 'ABS', 'ASA', 'TPU'],
    maxDims: { x: 350, y: 320, z: 325 }, toleranceMm: 0.25,
    unitsPerHour: 0.9, setupHours: 0.4, ratePerHour: 780, setupFee: 900,
    instructions: '3MF with your colours assigned, or tell me and I will assign them.',
    rules: ['Pickup or I post it', 'Colour changes cost filament in purge'],
  }),
  bl({
    id: 'l43', ownerId: 'n9', category: 'additive',
    title: 'DMLS metal printing',
    blurb: 'Laser powder bed in stainless and aluminium. Eindhoven, next to the machine shops.',
    district: 'Strijp', machine: 'EOS M 290',
    materials: ['Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 250, y: 250, z: 325 }, toleranceMm: 0.1,
    unitsPerHour: 0.35, setupHours: 4, ratePerHour: 19500, setupFee: 42000,
    instructions: 'STEP with machining stock left on critical faces. Stress relief and wire removal included.',
    rules: ['Support removal marks are unavoidable', 'Density report on request', 'Minimum order €900'],
  }),

  // ------------------------------------------------------ more finishing
  bl({
    id: 'l44', ownerId: 'b18', category: 'finishing',
    title: 'Electroplating, zinc and nickel',
    blurb: 'Barrel and rack plating with passivation. Small batches welcome.',
    district: 'Treptow', machine: 'Barrel and rack line',
    materials: ['Steel S235', 'Brass'], maxDims: { x: 800, y: 500, z: 400 },
    unitsPerHour: 140, setupHours: 1.4, ratePerHour: 4200, setupFee: 7000,
    instructions: 'Deburred and degreased. Tell us the coating thickness and whether you need RoHS paperwork.',
    rules: ['Hydrogen embrittlement relief on request', 'No assemblies with trapped cavities'],
  }),
  bl({
    id: 'l45', ownerId: 'b19', category: 'finishing',
    title: 'Shot blasting and vibratory finishing',
    blurb: 'Deburring, descaling and a uniform matt key before paint.',
    district: 'Teltow', machine: 'Rösler tumble blast + vibratory bowl',
    materials: ['Steel S235', 'Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 900, y: 600, z: 500 },
    unitsPerHour: 180, setupHours: 0.7, ratePerHour: 3400, setupFee: 4500,
    instructions: 'Tell us if any face must stay masked. Thin sheet can distort, we will flag it first.',
    rules: ['Media choice is ours unless specified', 'Not suitable below 0.8 mm sheet'],
  }),
  bl({
    id: 'l46', ownerId: 'f9', category: 'finishing',
    title: 'Wet paint booth, 2K',
    blurb: 'Two-pack spraying with a heated booth. Lyon, quick turnaround on small runs.',
    district: 'Vaulx-en-Velin', machine: 'Heated downdraught booth, 7 m',
    materials: ['Steel S235', 'Aluminium 6061', 'Plywood'],
    maxDims: { x: 6000, y: 2200, z: 2200 },
    unitsPerHour: 26, setupHours: 2, ratePerHour: 5400, setupFee: 12000,
    instructions: 'Send the RAL or a Pantone and the finish. Primer included unless the substrate says otherwise.',
    rules: ['Masking charged separately', 'Overnight cure before handling'],
  }),

  // ------------------------------------------------------ more print work
  bl({
    id: 'l47', ownerId: 'b22', category: 'print',
    title: 'Offset press, B2 five colour',
    blurb: 'Litho for books, catalogues and posters. Makeready shared across jobs.',
    district: 'Kreuzberg', machine: 'Heidelberg Speedmaster XL 75',
    maxDims: { x: 530, y: 750, z: 1 },
    unitsPerHour: 2800, setupHours: 2.5, ratePerHour: 9800, setupFee: 22000,
    instructions: 'PDF/X-4, 3 mm bleed, images at 300 dpi. We send a contract proof before the run.',
    rules: ['Paper at cost unless you supply it', 'Overs and unders of 5% are normal'],
  }),
  bl({
    id: 'l48', ownerId: 'f8', category: 'print',
    title: 'Screen printing, six station',
    blurb: 'Manual carousel for posters and garments. Paris, good for runs of 50 to 400.',
    district: 'Montreuil', machine: 'Six-colour carousel + flash',
    maxDims: { x: 500, y: 700, z: 1 },
    unitsPerHour: 58, setupHours: 1.3, ratePerHour: 3600, setupFee: 5500,
    instructions: 'Vector separations, one layer per colour, at final size. Screens charged per colour.',
    rules: ['Screens reusable for a repeat within six months', 'Maximum four colours on dark stock'],
  }),
  bl({
    id: 'l49', ownerId: 'i9', category: 'print',
    title: 'Label press, roll to roll',
    blurb: 'Digital labels with die cutting and laminate. Milan, small runs at short notice.',
    district: 'Isola', machine: 'Epson SurePress + Grafisk die cutter',
    maxDims: { x: 320, y: 5000, z: 1 },
    unitsPerHour: 1600, setupHours: 0.9, ratePerHour: 4600, setupFee: 6200,
    instructions: 'PDF with the die line on its own layer. Tell us roll direction and core size.',
    rules: ['Die tooling at cost for a new shape', 'White ink available on clear stock'],
  }),
  bl({
    id: 'l50', ownerId: 'o24', category: 'print',
    title: 'Laser engraver, 100 W',
    blurb: 'Engraving and light cutting in wood, acrylic and anodised aluminium.',
    district: 'Pankow', machine: 'Trotec Speedy 400',
    materials: ['Acrylic', 'Plywood', 'Aluminium 6061'],
    maxDims: { x: 1000, y: 610, z: 40 },
    unitsPerHour: 26, setupHours: 0.4, ratePerHour: 2900, setupFee: 1600,
    instructions: 'Vector for cuts, raster for engraving, on separate layers. No PVC, it destroys the optics.',
    rules: ['No PVC or vinyl', 'Material at cost unless you bring it', 'Pickup only'],
  }),

  // --------------------------------------------------------- more freight
  bl({
    id: 'l51', ownerId: 'n8', category: 'freight',
    title: 'Refrigerated van, Randstad',
    blurb: 'Temperature controlled 2 to 8 °C, daily Amsterdam–Rotterdam–Utrecht loop.',
    district: 'Jordaan', machine: 'Refrigerated Sprinter, 6 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 1600 },
    unitsPerHour: 0.9, setupHours: 1, ratePerHour: 5400, setupFee: 4200,
    instructions: 'Pre-chilled goods only, we do not pull temperature down. Logger travels with the load.',
    rules: ['Temperature log provided', 'No frozen goods', 'Max 500 kg per pallet'],
  }),
  bl({
    id: 'l52', ownerId: 'i10', category: 'freight',
    title: 'Flatbed, oversize from the valley',
    blurb: 'Machine moves and long stock out of Brescia. Permits arranged for oversize.',
    district: 'Lumezzane', machine: 'Flatbed semi with crane, 13.6 m',
    maxDims: { x: 13600, y: 2480, z: 2700 },
    unitsPerHour: 0.5, setupHours: 3.5, ratePerHour: 8600, setupFee: 18000,
    instructions: 'Send weights and lift points. Escort and permits quoted separately for anything over 3 m wide.',
    rules: ['Lashing included', 'Crane reach 8 m', 'Permits billed at cost'],
  }),
  bl({
    id: 'l53', ownerId: 'o25', category: 'freight',
    title: 'Courier van, same-day Berlin',
    blurb: 'Direct runs inside the Ring and out to Brandenburg. Usually free by early afternoon.',
    district: 'Friedrichshain', machine: 'VW Crafter, 4 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 1500 },
    unitsPerHour: 1.8, setupHours: 0.5, ratePerHour: 3400, setupFee: 1900,
    instructions: 'Message me the two addresses and a contact at each end. Photo proof at drop.',
    rules: ['No hazardous goods', 'Two-person lifts need warning', 'Max 400 kg per pallet'],
  }),
  bl({
    id: 'l54', ownerId: 'p6', category: 'freight',
    title: 'Iberia groupage, Lisbon–Madrid',
    blurb: 'Twice weekly eastbound. Consolidates part loads for the peninsula.',
    district: 'Marvila', machine: 'Curtainsider, 33 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 2400 },
    unitsPerHour: 1.2, setupHours: 2.2, ratePerHour: 4900, setupFee: 7800,
    instructions: 'Departs Tuesday and Friday. CMR at loading, POD scanned the next working day.',
    rules: ['Palletised only', 'Max 900 kg per pallet', 'Insurance at CMR limits'],
  }),

  // ------------------------------------------------------ more warehousing
  wl('l55', 'b20', 'warehousing', 'Ambient and hazmat bays', 'Racked ambient space plus a bunded hazmat bay to ADR class 3.', 'Schönefeld', 14, 24, 2160, 1800, 'Inbound handling per pallet', 'Hazmat goods in through gate 2 only. Safety data sheet required before arrival.', ['Safety data sheet before arrival', 'No class 1 or class 7', 'Stock report weekly']),
  wl('l56', 'b21', 'warehousing', 'Pick and pack fulfilment', 'Storage plus same-day picking, packing and carrier handover.', 'Ludwigsfelde', 21, 168, 2160, 4000, 'Onboarding and SKU setup', 'Send a packing spec and your carrier account. We photograph the first order of every SKU.', ['One SKU per location', 'Cut-off 15:00 for same day', 'Packaging at cost']),
  wl('l57', 'p6', 'warehousing', 'Tejo riverside storage', 'Dry racked space five minutes from the container terminal.', 'Marvila', 8, 24, 2160, 1100, 'Inbound handling per pallet', 'Goods in 08:00 to 17:00. Book a dock slot the day before.', ['Palletised and wrapped', 'No food or hazardous goods', 'Stock report on request']),

  // ------------------------------------------------- more workshop & tools
  wl('l58', 'o26', 'workshop', 'MIG and TIG welding bay', 'Fronius sets, extraction, a 2 m steel bench and a chop saw.', 'Moabit', 850, 2, 10, 0, 'No extras', 'Ground-floor unit behind the yard. Gas is included; bring your own filler and PPE beyond the mask.', ['Certificate or a test piece before you start', 'Extraction on at all times', 'Sweep the bay']),
  wl('l59', 'o27', 'workshop', 'Ceramics studio and kiln', 'Two wheels, a slab roller and a 100 l electric kiln.', 'Mitte', 700, 3, 12, 1800, 'Firing and glaze', 'Basement studio on Linienstraße. Firings run Thursdays, so throw by Wednesday.', ['Clay at cost', 'Firings batched weekly', 'Clean your wheel and bats']),
  wl('l60', 'o28', 'workshop', 'Industrial sewing room', 'Juki straight stitch, overlocker, coverstitch and a steam press.', 'Tempelhof', 600, 2, 10, 0, 'No extras', 'Third floor, lift at the back. Needles and thread are stocked; heavy canvas needs a needle change, ask me.', ['No leather on the overlocker', 'Replace a needle you break', 'Tidy the table']),
  wl('l61', 'o29', 'workshop', 'Bike workshop and wheel jig', 'Park Tool stand, truing jig, headset press and a full torque set.', 'Prenzlauer Berg', 400, 2, 8, 0, 'No extras', 'Courtyard shed, code sent on booking. Degreaser and rags are there; bring consumables.', ['Bring your own consumables', 'Torque wrench stays on the bench']),
  wl('l62', 'n7', 'workshop', 'Makerspace bench, De Pijp', 'Bench with vice, soldering station, oscilloscope and a small mill.', 'De Pijp', 550, 2, 8, 0, 'No extras', 'Ring at the side door. Bench 4 is the booked one; the scope calibration sheet is in the drawer.', ['Antistatic mat stays on the bench', 'Log any tool you find broken']),

  // -------------------------------------------------------- more event & AV
  wl('l63', 'o21', 'events', 'LED wall, 4 × 3 m', 'P3.9 indoor panels, processor, rigging bars and spares.', 'Kreuzberg', 2600, 8, 72, 18000, 'Delivery, rig and de-rig', 'Twelve cases and a flight case of spares. You need a van with a tail lift and four hands.', ['Indoor use only', 'Rigging by a competent person', 'Deposit agreed before pickup']),
  wl('l64', 'o26', 'events', 'Staging and truss', '24 m² of deck, legs to 800 mm, and 12 m of box truss with bases.', 'Moabit', 1300, 24, 168, 12000, 'Delivery inside the Ring', 'Stored in the yard. Everything is on wheeled dollies but the trailer is your problem.', ['Load rating 750 kg per m²', 'Returned clean', 'Two-person minimum']),
  wl('l65', 'o25', 'events', 'Marquee, 6 × 12 m', 'Clear-span frame tent with sidewalls, weights and a floor option.', 'Friedrichshain', 900, 24, 168, 15000, 'Delivery and crew', 'Stored flat in Friedrichshain. Four people and three hours to put up, honestly.', ['Not for winds above 40 km/h', 'Ground anchors or weights, not both', 'Returned dry']),

  // --------------------------------------------------------- more creator kit
  wl('l66', 'o23', 'creator', 'Podcast room, four mics', 'Treated room with four SM7Bs, a Rodecaster and boom arms.', 'Neukölln', 1400, 2, 8, 0, 'No extras', 'Second courtyard, studio B. Cards are formatted before each session; bring your own if you prefer.', ['No food in the booth', 'Levels checked before you record', 'Last session ends 22:00']),
  wl('l67', 'o22', 'creator', 'FPV and mapping drone', 'Mavic 3 Enterprise with RTK, plus spare batteries and a case.', 'Wedding', 1600, 4, 24, 0, 'No extras', 'Pickup in Wedding. You fly it, not me: A2 certificate and insurance checked at handover.', ['A2 certificate and insurance required', 'No flights over crowds', 'Batteries returned charged']),
  wl('l68', 'p3', 'creator', 'Grip and lighting truck', 'Two 300 W COBs, an Aputure 600x, flags, stands and a dolly.', 'Alcântara', 1800, 8, 72, 4000, 'Delivery in Lisbon', 'Old factory block, unit 7. Everything is cased and labelled; the inventory sheet is in the lid.', ['Insurance confirmation before pickup', 'Gels replaced if burnt', 'Returned in the same cases']),
  wl('l69', 'f7', 'creator', 'Daylight studio, Le Marais', '70 m² with north windows, a cyc corner and a small kitchen.', 'Le Marais', 2200, 3, 12, 0, 'No extras', 'Courtyard building, code sent on booking. The lift takes a cart but not a ladder.', ['No shoes on the cyc', 'Repaint charged if you mark it', 'Quiet after 20:00']),
  wl('l70', 'i8', 'creator', 'Sony FX6 kit, Milan', 'Body, 24-70 GM, 70-200 GM, cage, monitor and four batteries.', 'Navigli', 1900, 8, 72, 0, 'No extras', 'Pickup at the studio on the Naviglio Grande. Two Peli cases, heavier than they look.', ['Insurance confirmation before pickup', 'Cards returned formatted', 'No rain without the cover']),

  // --------------------------------------------------------------- event & AV
  wl('l35', 'o21', 'events', 'Pioneer booth + eight movers', 'CDJ-3000 pair, DJM-A9, eight LED movers and a small desk.', 'Kreuzberg', 1100, 8, 48, 6000, 'Delivery inside the Ring', 'Flightcased in the basement on Ohlauer. Two people to carry, the cases are not light.', ['Indoor use only', 'Returned in the same cases', 'Deposit agreed before pickup']),
]

const berlinSlots: Slot[] = [
  // Hammer drill
  ...recur('l8', WEEK, 8, 20),
  // Plunge saw, evenings and weekends
  ...recur('l9', [1, 3, 4], 17, 21),
  ...recur('l9', [5, 6], 9, 19),
  // PA rig, between gigs, long blocks
  win('l12', 3, 8, 22),
  win('l12', 4, 8, 22),
  win('l12', 5, 8, 22),
  // Camera kit, free for the next few days
  win('l13', 2, 8, 20),
  win('l13', 3, 8, 20),
  win('l13', 4, 8, 20),
  // Woodworking bench
  ...recur('l14', [0, 1, 2, 3, 4], 8, 19),
  ...recur('l14', [5], 10, 16),
  // Studio room
  ...recur('l15', WEEK, 10, 21),

  // Printers run unattended: the block spans the night and the day after
  win('l16', 0, 17, 32, 15),
  win('l16', 1, 18, 56, 38),
  win('l16', 4, 18, 56, 38),
  win('l17', 0, 19, 33, 14),
  win('l17', 1, 9, 44, 30),
  win('l17', 4, 9, 44, 30),
  // Laser
  win('l18', 0, 16, 22, 6),
  win('l18', 2, 10, 20, 10),
  win('l18', 5, 10, 20, 10),

  // Factory gaps: multi-day windows, but usable machine-hours are far fewer
  win('l19', 1, 6, 94, 52),
  win('l19', 9, 6, 110, 64),
  win('l20', 1, 6, 118, 74),
  win('l20', 10, 6, 126, 80),
  win('l21', 3, 6, 94, 48),
  win('l21', 12, 6, 94, 48),
  win('l22', 1, 6, 84, 40),
  win('l22', 8, 6, 84, 40),
  win('l23', 2, 6, 66, 30),
  win('l23', 11, 6, 66, 30),
  win('l24', 5, 6, 126, 90),

  // Finishing lines: a charge or a batch through the oven, not a machine-hour
  win('l25', 1, 6, 20, 12),
  win('l25', 4, 6, 20, 12),
  win('l25', 8, 6, 20, 12),
  win('l26', 0, 18, 32, 12),
  win('l26', 2, 18, 32, 12),
  win('l26', 6, 18, 32, 12),

  // Print, mostly evenings and the quiet middle of the week
  ...recur('l27', [1, 2, 3], 10, 20),
  ...recur('l28', [0, 1, 2, 4], 9, 18),
  win('l29', 1, 14, 24, 10),
  win('l29', 3, 14, 24, 10),
  win('l29', 7, 14, 24, 10),

  // Freight departs when it departs. The window is the run, and the usable
  // hours are the driving time, not the days it sits at either end.
  win('l30', 3, 6, 20, 11),
  win('l30', 10, 6, 20, 11),
  win('l31', 0, 5, 17, 9),
  win('l31', 2, 5, 17, 9),
  win('l31', 7, 5, 17, 9),
  win('l32', 3, 18, 90, 22),
  win('l32', 10, 18, 90, 22),

  // Space is continuous, so it is one long block rather than daily windows
  win('l33', 0, 0, 24 * 60, 24 * 60),
  win('l34', 0, 0, 24 * 45, 24 * 45),


  // Fabrication: gaps between contracts, measured in machine-hours not calendar
  win('l36', 1, 6, 20, 11), win('l36', 4, 6, 20, 11), win('l36', 8, 6, 20, 11),
  win('l37', 2, 6, 78, 34), win('l37', 9, 6, 78, 34),
  win('l38', 0, 6, 20, 12), win('l38', 3, 6, 20, 12), win('l38', 7, 6, 20, 12),
  win('l39', 1, 6, 44, 20), win('l39', 8, 6, 44, 20),

  // Printing runs unattended, so the block spans the night and the day after
  win('l40', 0, 18, 34, 14), win('l40', 2, 18, 56, 32), win('l40', 5, 18, 56, 32),
  win('l41', 1, 6, 102, 56), win('l41', 8, 6, 102, 56),
  win('l42', 0, 17, 33, 15), win('l42', 3, 9, 44, 30), win('l42', 6, 9, 44, 30),
  win('l43', 2, 6, 126, 72), win('l43', 11, 6, 126, 72),

  // Finishing lines run a charge, not a machine-hour
  win('l44', 0, 6, 20, 12), win('l44', 3, 6, 20, 12), win('l44', 7, 6, 20, 12),
  win('l45', 1, 6, 18, 11), win('l45', 4, 6, 18, 11), win('l45', 9, 6, 18, 11),
  win('l46', 2, 6, 20, 13), win('l46', 6, 6, 20, 13), win('l46', 10, 6, 20, 13),

  // Print: makeready is the cost, so blocks are long and few
  win('l47', 1, 6, 22, 14), win('l47', 5, 6, 22, 14),
  ...recur('l48', [1, 3, 4], 10, 19),
  win('l49', 0, 8, 20, 11), win('l49', 3, 8, 20, 11), win('l49', 8, 8, 20, 11),
  ...recur('l50', [0, 2, 4, 5], 10, 19),

  // Freight leaves when it leaves; usable hours are driving time
  ...recur('l51', [0, 1, 2, 3, 4], 6, 16, 8),
  win('l52', 4, 5, 29, 15), win('l52', 11, 5, 29, 15),
  ...recur('l53', WEEK, 8, 18, 8),
  win('l54', 1, 6, 26, 13), win('l54', 4, 6, 26, 13), win('l54', 8, 6, 26, 13),

  // Space is continuous: one long block, not daily windows
  win('l55', 0, 0, 24 * 60, 24 * 60),
  win('l56', 0, 0, 24 * 60, 24 * 60),
  win('l57', 0, 0, 24 * 60, 24 * 60),

  // Workshops: evenings and weekends, mostly
  ...recur('l58', [1, 2, 4, 5], 9, 19),
  ...recur('l59', [0, 2, 3], 10, 20),
  ...recur('l60', [0, 1, 3, 4], 9, 18),
  ...recur('l61', WEEK, 9, 20),
  ...recur('l62', [1, 2, 3, 5, 6], 10, 20),

  // Stage kit, between weekend bookings
  win('l63', 2, 8, 22), win('l63', 3, 8, 22), win('l63', 9, 8, 22),
  win('l64', 1, 8, 104), win('l64', 8, 8, 104),
  win('l65', 3, 8, 128), win('l65', 11, 8, 104),

  // Creator kit
  ...recur('l66', [0, 1, 2, 3, 4], 10, 21),
  win('l67', 1, 9, 19), win('l67', 4, 9, 19), win('l67', 8, 9, 19),
  win('l68', 2, 8, 20), win('l68', 5, 8, 20), win('l68', 9, 8, 20),
  ...recur('l69', [0, 1, 2, 3, 4, 5], 9, 20),
  win('l70', 1, 8, 20), win('l70', 2, 8, 20), win('l70', 6, 8, 20),

  // Stage rig, between weekend bookings
  win('l35', 1, 8, 22),
  win('l35', 2, 8, 22),
  win('l35', 8, 8, 22),
]

const euOwners: Owner[] = [
  // Amsterdam
  person('n3', 'Joris Willems', 'JW', 'Oud-West', 34, 7, 7, 2026, 38),
  person('n4', 'Nienke Visser', 'NV', 'Amsterdam-Noord', 68, 14, 13, 2024, 20),
  firm('n6', 'Haven Opslag BV', 'HO', 'Amsterdam-Noord', 55, 12, 11, 2025, 95),
  firm('n5', 'Brainport Precisie BV', 'BP', 'Strijp', 118, 24, 23, 2024, 85),

  // Paris
  person('f1', 'Camille Rousseau', 'CR', 'Belleville', 77, 16, 15, 2025, 17),
  person('f4', 'Thomas Girard', 'TG', 'Montreuil', 0, 0, 0, 2026, 50),
  firm('f5', 'Rhône Tournage SAS', 'RT', 'Vaulx-en-Velin', 89, 19, 17, 2025, 100),
  firm('f6', 'Transports Rhône-Sud SAS', 'TR', 'Vaulx-en-Velin', 67, 14, 14, 2025, 75),

  // Milan
  person('i3', 'Chiara Rizzo', 'CZ', 'Lambrate', 27, 6, 6, 2026, 42),
  person('i4', 'Davide Conti', 'DC', 'Bovisa', 64, 14, 13, 2024, 24),
  firm('i5', 'Valtrompia Meccanica Srl', 'VM', 'Lumezzane', 131, 27, 26, 2024, 95),
  firm('i6', 'Acciaio Lumezzane Srl', 'AL', 'Lumezzane', 0, 0, 0, 2026, 130),
  firm('i7', 'Galvanica Valtrompia Srl', 'GV', 'Lumezzane', 96, 20, 19, 2024, 88),

  // Lisbon
  person('p2', 'Tiago Sousa', 'TS', 'Marvila', 36, 8, 7, 2025, 34),
  person('p3', 'Mariana Lopes', 'ML', 'Alcântara', 72, 15, 14, 2024, 21),
  person('p4', 'Rui Antunes', 'RA', 'Benfica', 22, 5, 5, 2026, 46, false),

  // ---- more supply across the rest of Europe -----------------------------
  person('n7', 'Sanne de Boer', 'SB', 'De Pijp', 49, 10, 10, 2025, 24),
  firm('n8', 'Randstad Koeltransport BV', 'RK', 'Jordaan', 82, 17, 17, 2024, 78),
  firm('n9', 'Eindhoven Additive BV', 'EA', 'Strijp', 0, 0, 0, 2026, 105),
  person('f7', 'Élodie Mercier', 'EL', 'Le Marais', 58, 12, 12, 2025, 20),
  firm('f8', 'Atelier Sérigraphie Nord', 'AS', 'Montreuil', 44, 9, 9, 2025, 48),
  firm('f9', 'Traitement Rhône SAS', 'TH', 'Vaulx-en-Velin', 76, 16, 15, 2024, 92),
  person('i8', 'Luca Ferrari', 'LF', 'Navigli', 53, 11, 11, 2025, 26),
  firm('i9', 'Stampa Isola Srl', 'SI', 'Isola', 68, 14, 14, 2024, 50),
  firm('i10', 'Logistica Brescia Srl', 'LB', 'Lumezzane', 0, 0, 0, 2026, 118),
  person('p5', 'Inês Carvalho', 'IC', 'Arroios', 47, 10, 10, 2025, 23),
  firm('p6', 'Tejo Fulfilment Lda', 'TF', 'Marvila', 62, 13, 13, 2025, 68),
]

const euListings: Listing[] = [
  // ---------------------------------------------------------------- Amsterdam
  wl('n-l3', 'n3', 'workshop', 'Festool ETS 150 sander + extractor', 'Random orbital with a proper dust extractor.', 'Oud-West', 450, 2, 8, 0, 'No extras', 'Systainer in the hall cupboard. Abrasives are yours. The shop on the corner has them.', ['Empty the extractor bag', 'Indoor use only']),
  wl('n-l5', 'n4', 'creator', 'Sony FX3 + three primes', 'Body, 24/35/85 GM, cage and two batteries.', 'Amsterdam-Noord', 1700, 8, 72, 0, 'No extras', 'Ferry from Centraal, five minutes the other side. Two Peli cases, heavier than they look.', ['Insurance confirmation before pickup', 'Cards returned formatted', 'No rain without the cover']),
  {
    id: 'n-l6',
    ownerId: 'n5',
    category: 'fabrication',
    mode: 'batch',
    title: 'Hurco VMX42 Ti',
    blurb: 'Titanium and alloy work. Gaps most weeks between Brainport contracts.',
    district: 'Strijp',
    machine: 'Hurco VMX42 Ti',
    materials: ['Aluminium 6061', 'Aluminium 7075', 'Stainless 304', 'POM'],
    maxDims: { x: 1067, y: 610, z: 610 },
    toleranceMm: 0.02,
    unitsPerHour: 11,
    setupHours: 2.5,
    ratePerHour: 10500,
    setupFee: 22000,
    instructions: 'STEP plus a dimensioned PDF. First article measured and reported before the run continues.',
    rules: ['First-article inspection included', 'Material certificates on request', 'Minimum order €400'],
    active: true,
  },

  // -------------------------------------------------------------------- Paris
  wl('f-l4', 'f4', 'workshop', 'Shared wood atelier', 'Bench, extraction, bandsaw. Heated, good light.', 'Montreuil', 700, 2, 10, 0, 'No extras', 'Back of the courtyard, unit 3. Bench is 2.4 m; clamps shared, hand tools are not.', ['Bring your own blades', 'Sweep at the end', 'Ear protection provided']),
  wl('f-l5', 'f1', 'events', 'Nexo PA + lighting desk', 'Two tops, one sub, twelve LED pars and a desk.', 'Belleville', 1400, 8, 72, 9000, 'Load-out and cabling', 'Flightcased, rehearsal room on rue Ramponeau. You need a van, not a car.', ['Indoor use unless covered', 'Returned in the same cases', 'Deposit agreed before pickup']),
  {
    id: 'f-l6',
    ownerId: 'f5',
    category: 'fabrication',
    mode: 'batch',
    title: 'Mazak QT-200',
    blurb: 'Bar work to Ø 65. Second shift often free.',
    district: 'Vaulx-en-Velin',
    machine: 'Mazak QT-200',
    materials: ['Aluminium 6061', 'Stainless 304', 'Brass', 'Steel S235'],
    maxDims: { x: 300, y: 300, z: 520 },
    toleranceMm: 0.025,
    unitsPerHour: 14,
    setupHours: 1.8,
    ratePerHour: 7200,
    setupFee: 16000,
    instructions: 'Drawing with tolerances and surface finish. We quote back inside a working day.',
    rules: ['Minimum order €300', 'Thread gauging on request'],
    active: true,
  },

  // -------------------------------------------------------------------- Milan
  wl('i-l3', 'i3', 'workshop', 'Makita mitre saw + stand', '305 mm sliding compound, folding stand.', 'Lambrate', 300, 2, 8, 0, 'No extras', 'Ground-floor storeroom, ask at the bar next door if I am out.', ['Back the same day', 'Blade stays on the saw']),
  wl('i-l4', 'i4', 'creator', 'Design studio desk + A1 plotter', 'Quiet desk, plotter, good north light.', 'Bovisa', 800, 2, 10, 0, 'No extras', 'Second floor above the old workshop. Plotter paper is stocked; bring your own files.', ['No food at the plotter', 'Last entry 20:00']),
  {
    id: 'i-l5',
    ownerId: 'i5',
    category: 'fabrication',
    mode: 'batch',
    title: 'Mazak VCN-530C',
    blurb: 'Vertical machining centre in the Brescia valley. Reliable, well kept.',
    district: 'Lumezzane',
    machine: 'Mazak VCN-530C',
    materials: ['Aluminium 6061', 'Stainless 304', 'Steel S235', 'Brass'],
    maxDims: { x: 1050, y: 530, z: 510 },
    toleranceMm: 0.03,
    unitsPerHour: 13,
    setupHours: 2,
    ratePerHour: 6900,
    setupFee: 14000,
    instructions: 'STEP or Parasolid. We will tell you if a feature is going to be expensive before we run it.',
    rules: ['Deburred as standard', 'Anodising subcontracted, adds 5 days'],
    active: true,
  },
  {
    id: 'i-l6',
    ownerId: 'i6',
    category: 'fabrication',
    mode: 'batch',
    title: 'Salvagnini P2Lean panel bender',
    blurb: 'Bending and punching up to 2.5 m. New to Cappy, quoting keenly.',
    district: 'Lumezzane',
    machine: 'Salvagnini P2Lean',
    materials: ['Steel S235', 'Stainless 304', 'Aluminium 6061'],
    maxDims: { x: 2500, y: 1250, z: 20 },
    toleranceMm: 0.2,
    unitsPerHour: 40,
    setupHours: 1.2,
    ratePerHour: 8200,
    setupFee: 11000,
    instructions: 'Flat patterns as DXF. Tell us your bend allowance or we will use ours and say so.',
    rules: ['Powder coating subcontracted', 'Offcuts kept unless you ask'],
    active: true,
  },

  // ------------------------------------------------------------------- Lisbon
  wl('p-l3', 'p4', 'workshop', 'Bosch tile cutter + SDS drill', 'Wet cutter and a hammer drill with the full bit set.', 'Benfica', 200, 2, 8, 0, 'No extras', 'Garage under the building. Water connection for the cutter is on the wall.', ['Rinse the cutter tray', 'Back the same day']),
  wl('p-l4', 'p3', 'creator', 'Photo studio with cyc wall', '60 m², white cyc, two strobes and stands.', 'Alcântara', 1100, 2, 10, 0, 'No extras', 'Old factory block, unit 7. Strobes and stands stay; bring your own modifiers and cards.', ['No shoes on the cyc', 'Repaint charged if you mark it', 'Last session ends 21:00']),
  bl({
    id: 'i-l7',
    ownerId: 'i7',
    category: 'finishing',
    title: 'Anodising line, clear and black',
    blurb: 'Type II in the valley, next door to half the machine shops on here.',
    district: 'Lumezzane',
    machine: 'Anodising line, 3.5 m tanks',
    materials: ['Aluminium 6061', 'Aluminium 7075'],
    maxDims: { x: 3500, y: 1200, z: 900 },
    unitsPerHour: 75,
    setupHours: 1.8,
    ratePerHour: 5200,
    setupFee: 8500,
    instructions: 'Tell us the coating thickness in microns and where the jig marks may go. Parts arrive deburred.',
    rules: ['Jig marks are unavoidable, you choose where', 'No welded assemblies with trapped cavities'],
  }),
  bl({
    id: 'f-l7',
    ownerId: 'f6',
    category: 'freight',
    title: 'Lyon–Barcelona semi, Fridays',
    blurb: 'Southbound every Friday, back empty on Monday. Part loads welcome either way.',
    district: 'Vaulx-en-Velin',
    machine: 'Curtainsider, 33 pallet spaces',
    maxDims: { x: 1200, y: 800, z: 2400 },
    unitsPerHour: 1.1,
    setupHours: 2,
    ratePerHour: 5800,
    setupFee: 7200,
    instructions: 'Loading Thursday afternoon at Vaulx. CMR raised at loading, POD scanned on delivery.',
    rules: ['Palletised only', 'No temperature-controlled goods', 'Max 900 kg per pallet'],
  }),
  wl('n-l7', 'n6', 'warehousing', 'Bonded warehouse, Amsterdam-Noord', 'Customs-bonded and general storage on the IJ, ten minutes from the port.', 'Amsterdam-Noord', 12, 24, 2160, 1500, 'Inbound handling per pallet', 'Entrance on the quay side. Goods in 07:00 to 16:00, book a dock slot in advance.', ['Palletised and wrapped', 'Bonded stock needs paperwork before arrival', 'Stock report on request']),
  wl('p-l6', 'p5', 'events', 'Rooftop PA and festoon lighting', 'Two powered tops, a sub, a small mixer and 40 m of festoon.', 'Arroios', 900, 8, 48, 5000, 'Delivery in central Lisbon', 'Stored on the ground floor, two flights down to the van. Festoon is on reels, please roll it back.', ['Outdoor use in dry weather only', 'Returned in the same cases', 'Deposit agreed before pickup']),
  {
    id: 'p-l5',
    ownerId: 'p2',
    category: 'additive',
    mode: 'batch',
    title: 'Prusa MK4 ×2',
    blurb: 'Two machines running unattended overnight in the workshop.',
    district: 'Marvila',
    machine: 'Prusa MK4 ×2',
    materials: ['PLA', 'PETG', 'ABS', 'ASA'],
    maxDims: { x: 250, y: 210, z: 220 },
    toleranceMm: 0.3,
    unitsPerHour: 0.7,
    setupHours: 0.5,
    ratePerHour: 650,
    setupFee: 800,
    instructions: 'STL or 3MF. I confirm orientation with you before the first layer goes down.',
    rules: ['Pickup only', 'No food-contact parts']
    ,
    active: true,
  },
]

const euSlots: Slot[] = [
  // Amsterdam
  ...recur('n-l3', [1, 2, 3, 5, 6], 9, 19),
  win('n-l5', 2, 8, 20),
  win('n-l5', 3, 8, 20),
  win('n-l5', 5, 8, 20),
  win('n-l6', 1, 6, 110, 60),
  win('n-l6', 9, 6, 110, 60),

  // Paris
  ...recur('f-l4', [0, 1, 2, 3, 4], 9, 19),
  win('f-l5', 3, 8, 22),
  win('f-l5', 4, 8, 22),
  win('f-l6', 2, 6, 100, 56),
  win('f-l6', 11, 6, 100, 56),

  // Milan
  ...recur('i-l3', WEEK, 9, 19),
  ...recur('i-l4', [0, 1, 2, 3, 4], 9, 20),
  win('i-l5', 1, 6, 102, 58),
  win('i-l5', 10, 6, 102, 58),
  win('i-l6', 3, 6, 78, 36),
  win('i-l6', 12, 6, 78, 36),

  // Lisbon
  ...recur('p-l3', WEEK, 9, 19),
  ...recur('p-l4', [0, 1, 2, 3, 4, 5], 9, 21),
  win('p-l5', 0, 18, 33, 15),
  win('p-l5', 2, 18, 56, 36),
  win('p-l5', 5, 18, 56, 36),
  win('p-l6', 2, 10, 23), win('p-l6', 3, 10, 23), win('p-l6', 9, 10, 23),

  // Brescia finishing, next door to the machine shops it serves
  win('i-l7', 2, 6, 20, 12),
  win('i-l7', 5, 6, 20, 12),
  win('i-l7', 9, 6, 20, 12),

  // Lyon southbound, every Friday
  win('f-l7', 4, 14, 38, 14),
  win('f-l7', 11, 14, 38, 14),

  // Bonded space, continuous
  win('n-l7', 0, 0, 24 * 60, 24 * 60),
]


/**
 * Stand-ins for the photographs an owner would upload.
 *
 * Real listings carry real uploads. These are a small curated pool per category,
 * handed out by rotation rather than by hashing the id: a hash spreads evenly in
 * theory and in practice puts the same picture on two cards sitting next to each
 * other, which reads as a bug rather than as a placeholder. Rotation guarantees a
 * category exhausts its pool before it repeats anything.
 */
const PHOTOS: Record<CategoryId, string[]> = {
  fabrication: [
    '1516110833967-0b5716ca1387',
    '1558618666-fcd25c85cd64',
    '1567789884554-0b844b597180',
    '1581091226825-a6a2a5aee158',
  ],
  additive: ['1611273426858-450d8e3c9fce', '1581092160562-40aa08e78837'],
  finishing: [
    '1504328345606-18bbc8c9d7d1',
    '1581578731548-c64695cc6952',
    '1574359411659-15573a27fd0c',
    '1611117775350-ac3950990985',
  ],
  print: [
    '1452860606245-08befc0ff44b',
    '1489987707025-afc232f7ea0f',
    '1581094288338-2314dddb7ece',
  ],
  freight: [
    '1601584115197-04ecc0da31d7',
    '1565043666747-69f6646db940',
    '1595246140625-573b715d11dc',
  ],
  warehousing: ['1553413077-190dd305871c', '1586528116311-ad8dd3c8310d'],
  workshop: [
    '1581092918056-0c4c3acd3789',
    '1621905251189-08b45d6a269e',
    '1517420704952-d9f39e95b43e',
    '1556740738-b6a63e27c4df',
    '1504328345606-18bbc8c9d7d1',
  ],
  events: ['1493225457124-a3eb161ffa5f', '1516450360452-9312f5e86fc7'],
  creator: ['1526406915894-7bcd65f60845', '1612690669207-fed642192c40'],
}

const photoUrl = (id: string, w: number) =>
  `https://images.unsplash.com/photo-${id}?w=${w}&q=70&auto=format&fit=crop`

function withPhotos(all: Listing[]): Listing[] {
  const taken: Partial<Record<CategoryId, number>> = {}
  return all.map((l) => {
    const set = PHOTOS[l.category]
    const n = taken[l.category] ?? 0
    taken[l.category] = n + 1
    const cover = set[n % set.length]
    const second = set[(n + 1) % set.length]
    return {
      ...l,
      photos:
        cover === second ? [photoUrl(cover, 900)] : [photoUrl(cover, 900), photoUrl(second, 900)],
    }
  })
}

export const owners: Owner[] = [...berlinOwners, ...euOwners]
export const listings: Listing[] = withPhotos([...berlinListings, ...euListings])
export const slots: Slot[] = [...berlinSlots, ...euSlots]

// ------------------------------------------------------------------ reviews
//
// Written from each owner's real record rather than invented alongside it: a
// shop with thirty jobs at 4.9 gets four reviews that read like 4.9, an owner
// with nothing done yet gets none and shows as new. Text is per part of the
// chain, because what a buyer praises about a mill is not what they praise
// about a van.

type Line = { text: string; tags: string[]; floor: number }

const LINES: Record<CategoryGroup, Line[]> = {
  make: [
    { floor: 5, text: 'First article came back measured and in spec. The rest of the run matched it, which is the whole point.', tags: ['Great quality', 'As described'] },
    { floor: 5, text: 'They flagged a feature that would have doubled the cost before running it. Changed the drawing, saved a week.', tags: ['Quick replies', 'Fair price'] },
    { floor: 5, text: 'Sent a STEP on Monday night, parts in a box by Thursday. Deburred without being asked.', tags: ['Ready on time', 'Great quality'] },
    { floor: 4, text: 'Good finish and a clear quote. Pickup took a while to arrange but the parts were right.', tags: ['Great quality', 'As described'] },
    { floor: 5, text: 'Exactly what the listing said. Photos of the setup before they started, which I appreciated.', tags: ['As described', 'Clear handover'] },
    { floor: 4, text: 'Solid work at a better price than the two shops I usually use. Will send the next batch here.', tags: ['Fair price'] },
    { floor: 5, text: 'Tolerances held across all fifty. Material cert included without me chasing it.', tags: ['Great quality', 'Ready on time'] },
    { floor: 3, text: 'Parts were fine, but it ran a day late and I had to ask twice for an update.', tags: ['As described'] },
    { floor: 3, text: 'Quality was good. Communication was slow and the setup fee was more than I expected.', tags: ['Great quality'] },
  ],
  move: [
    { floor: 5, text: 'Photo at pickup, photo at drop, exactly as promised. Pallets arrived wrapped the way they left.', tags: ['Clear handover', 'Ready on time'] },
    { floor: 5, text: 'Half the price of booking a dedicated van for three pallets. Would not ship any other way now.', tags: ['Fair price'] },
    { floor: 5, text: 'Booking closed at four, goods were in Hamburg by ten the next morning. No drama at all.', tags: ['Ready on time', 'Quick replies'] },
    { floor: 4, text: 'Space was clean and racked, stock report every week. Getting a dock slot took some back and forth.', tags: ['As described', 'Clear handover'] },
    { floor: 5, text: 'They called ahead when the ring road closed and rerouted. Arrived inside the window anyway.', tags: ['Quick replies', 'Ready on time'] },
    { floor: 4, text: 'Did what it said. Paperwork could be clearer, but nothing went missing and nothing was damaged.', tags: ['As described'] },
    { floor: 3, text: 'Arrived fine but three hours after the slot, and the driver had not been told about the tail lift.', tags: ['Fair price'] },
  ],
  equip: [
    { floor: 5, text: 'Everything in the cases, charged and labelled. Handover took five minutes and they showed me the quirks.', tags: ['Clear handover', 'As described'] },
    { floor: 5, text: 'Replied within ten minutes on a Sunday. The kit was better kept than my own.', tags: ['Quick replies', 'Great quality'] },
    { floor: 5, text: 'Booked for an afternoon, saved me buying something I use twice a year. Exactly the point of this.', tags: ['Fair price'] },
    { floor: 4, text: 'Great space and good light. Access instructions could be clearer, I rang the wrong bell.', tags: ['As described', 'Great quality'] },
    { floor: 5, text: 'Ready when I arrived, spare blades out on the bench. Would book again without thinking.', tags: ['Ready on time', 'Clear handover'] },
    { floor: 4, text: 'Does what it says. One battery was low, they sent a spare over within the hour.', tags: ['Quick replies'] },
    { floor: 5, text: 'Treated room is properly treated, not just foam on a wall. Recorded a whole episode in one take.', tags: ['Great quality', 'As described'] },
    { floor: 3, text: 'Fine for the price, but the handover was rushed and one lead was missing.', tags: ['Fair price'] },
  ],
}

const REVIEWERS: [string, string][] = [
  ['Maja K.', 'MK'], ['Julien P.', 'JP'], ['Sofia R.', 'SR'], ['Henrik L.', 'HL'],
  ['Aylin D.', 'AD'], ['Marco B.', 'MB'], ['Noor V.', 'NV'], ['Felix W.', 'FW'],
  ['Carla M.', 'CM'], ['Oskar T.', 'OT'], ['Lina S.', 'LS'], ['Ruben H.', 'RH'],
  ['Elif A.', 'EA'], ['Paulo G.', 'PG'], ['Ida N.', 'IN'], ['Theo F.', 'TF'],
]

function seedReviews(all: Listing[], who: Owner[]): Review[] {
  const byId = new Map(who.map((o) => [o.id, o]))
  const out: Review[] = []
  for (const l of all) {
    const o = byId.get(l.ownerId)
    if (!o || o.jobsDone === 0) continue
    const n = Math.min(o.jobsDone, 4)
    const avg = o.ratingSum / o.jobsDone
    const late = o.jobsDone - o.onTimeJobs
    let h = 0
    for (const ch of l.id) h = (h * 31 + ch.charCodeAt(0)) >>> 0
    const pool = LINES[category(l.category).group]
    const used = new Set<string>()
    for (let i = 0; i < n; i++) {
      // One review in four lands a star below the average, so a 4.6 reads as a
      // 4.6 rather than as four fives.
      const rating = Math.max(3, Math.min(5, i === 2 && avg < 4.85 ? Math.floor(avg) : Math.round(avg)))
      const fits = pool.filter((p) => p.floor === rating)
      // Never the same sentence twice on one listing. Prefer a line written for
      // this rating; when those run out, take the unused line nearest to it.
      const rotate = <T,>(xs: T[]) => xs.map((_, k) => xs[(h + i + k) % xs.length])
      const nearest = [...pool].sort((a, b) => Math.abs(a.floor - rating) - Math.abs(b.floor - rating))
      const line =
        rotate(fits).find((p) => !used.has(p.text)) ??
        nearest.find((p) => !used.has(p.text)) ??
        pool[(h + i) % pool.length]
      used.add(line.text)
      const [author, initials] = REVIEWERS[(h + i * 3) % REVIEWERS.length]
      out.push({
        id: `rv_${l.id}_${i}`,
        listingId: l.id,
        ownerId: o.id,
        author,
        initials,
        rating,
        onTime: !(late > 0 && i === n - 1 && rating < 5),
        text: line.text,
        tags: line.tags,
        at: new Date(base.getTime() - (i * 19 + (h % 11) + 2) * 86_400_000).toISOString(),
      })
    }
  }
  return out
}

export const reviews: Review[] = seedReviews(listings, owners)


export const world = { owners, listings, slots, districts, reviews }

/** Where the buyer is searching from. Berlin-first, and the only city seeded. */
export const HOME_DISTRICT = 'Kreuzberg'

/**
 * One request already waiting in the Earn inbox, so the owner side is not empty
 * on first run. Somebody nearby wants two hours of a saw that would otherwise
 * sit in a cupboard tonight, which is the whole pitch, inbound.
 */
export function seedBookings(now = new Date()): Booking[] {
  const me = owners.find((o) => o.id === ME)!
  const saw = listings.find((l) => l.id === 'l9')!
  const mine = slots.filter((s) => s.listingId === saw.id)

  const req: WindowRequest = {
    mode: 'window',
    category: 'workshop',
    hours: 2,
    earliest: now.toISOString(),
    latest: new Date(now.getTime() + 5 * 86_400_000).toISOString(),
    district: HOME_DISTRICT,
    maxDistanceKm: 10,
  }

  const offer = earliestOffer(mine, 2, now.toISOString(), req.latest)
  if (!offer) return []

  const match = matchForOffer(req, saw, me, offer, 1.4)
  if (!match) return []

  return [
    {
      id: 'bk_seed_1',
      match,
      requirement: req,
      status: 'requested',
      createdAt: new Date(now.getTime() - 22 * 60_000).toISOString(),
      requesterId: 'o17',
    },
  ]
}
