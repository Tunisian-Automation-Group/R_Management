// The capacity graph.
//
// One network, one atomic unit: a capacity slot. A resin printer free overnight,
// a 5-axis mill free between contracts and half a truck going to Lyon on Thursday
// are the same thing, idle capacity someone will pay for. They differ only in how
// the buyer says what they want,
//   'window' : "I need it from 18:00 for two hours"   (tools, AV, creator, space)
//   'batch'  : "I need 500 of these by the 14th"      (making, finishing, freight)
// Everything downstream (feasibility, availability, pricing, matching) is shared.
//
// There is deliberately no consumer/industry split. One capacity graph, several
// demand pools: a buyer who books a laser cutter on Monday, a powder coater on
// Wednesday and a pallet to Milan on Friday is one buyer, not three markets. The
// same graph is what lets a neighbour sell hours on a printer sitting in a spare
// room, because from the engine's point of view that is the same kind of object
// as a factory selling second-shift capacity.

/** Integer cents. Never floats for money. */
export type Cents = number

/** ISO-8601 instant. */
export type Iso = string

export type BookingMode = 'window' | 'batch'

/**
 * Three things a buyer needs to get a physical job done, and the network sells
 * all three. Splitting them is what keeps nine categories legible: you arrive
 * knowing whether you need something made, moved, or lent to you.
 */
export type CategoryGroup = 'make' | 'move' | 'equip'

/**
 * Nine categories across the chain, because a part that cannot be finished and
 * cannot be shipped is not a delivered order. Freight is in here on purpose: it
 * is the step that makes capacity in Lumezzane usable from Berlin, and without
 * it a pan-European capacity graph is a directory of places you cannot reach.
 */
export type CategoryId =
  // make
  | 'fabrication'
  | 'additive'
  | 'finishing'
  | 'print'
  // move
  | 'freight'
  | 'warehousing'
  // equip
  | 'workshop'
  | 'events'
  | 'creator'

export type Material =
  | 'PLA'
  | 'PETG'
  | 'ABS'
  | 'ASA'
  | 'TPU'
  | 'Resin'
  | 'Aluminium 6061'
  | 'Aluminium 7075'
  | 'Stainless 304'
  | 'Steel S235'
  | 'Brass'
  | 'POM'
  | 'Acrylic'
  | 'Plywood'

/** Bounding box in millimetres. */
export type Dims = { x: number; y: number; z: number }

/** A neighbourhood somewhere in Europe. Keyed by name across the whole registry,
 *  so names stay unique, 'Kreuzberg', 'Le Marais', 'Jordaan'. */
export type District = {
  name: string
  /** The true city. Potsdam is Potsdam, not Berlin. */
  city: string
  /** The market it trades in. Potsdam is in Berlin's, Lumezzane in Brescia's.
   *  Kept separate from `city` so labels stay honest while distance still
   *  decides what anyone can actually reach. */
  metro: string
  /** ISO-3166-1 alpha-2. Eurozone only for now, so one currency everywhere. */
  country: string
  lat: number
  lng: number
}

export type Owner = {
  id: string
  name: string
  /** Two letters. We show initials rather than invented photographs of real-looking people. */
  initials: string
  kind: 'person' | 'business'
  district: string
  verified: boolean
  /** Sum of 1-5 stars across rated bookings, kept as a sum so a new rating folds in. */
  ratingSum: number
  jobsDone: number
  onTimeJobs: number
  joinedYear: number
  /** Median minutes to respond to a request. Buyers care about this more than stars. */
  responseMins: number
}

type ListingBase = {
  id: string
  ownerId: string
  category: CategoryId
  title: string
  blurb: string
  district: string
  /**
   * What the owner photographed. The first is the cover.
   *
   * The old rule here was that a listing has no photograph, on the grounds that
   * a stock photo of someone else's machine would be a lie. That was right about
   * stock photography and wrong about this product: these are pictures the owner
   * takes of their own kit, which is the most honest thing on the listing. A
   * buyer deciding between two mills wants to see the two mills.
   *
   * Optional, because a listing is valid before anyone uploads anything, and the
   * plate still covers that case.
   */
  photos?: string[]
  /** Shown after booking. Real handover detail, not marketing. */
  instructions: string
  rules: string[]
  active: boolean
}

export type WindowListing = ListingBase & {
  mode: 'window'
  ratePerHour: Cents
  minHours: number
  maxHours: number
  /** Consumables or turnaround the owner charges once: detergent, fuel, a clean. */
  extraFee: Cents
  extraLabel: string
}

export type BatchListing = ListingBase & {
  mode: 'batch'
  /** The machine, the line, or the vehicle. Whatever actually does the work. */
  machine: string
  /** Absent where the question does not apply: a truck does not stock a material. */
  materials?: Material[]
  /** Per unit. A build envelope on a mill, the load box on a van. */
  maxDims: Dims
  /** Tightest tolerance held, in mm. Absent where nothing is being held to one. */
  toleranceMm?: number
  unitsPerHour: number
  setupHours: number
  ratePerHour: Cents
  setupFee: Cents
}

export type Listing = WindowListing | BatchListing

/** An idle window. This is the product. */
export type Slot = {
  id: string
  listingId: string
  start: Iso
  end: Iso
  /** Usable hours inside the window, a 3-day factory gap is not 72 machine-hours. */
  hoursUsable: number
}

export type WindowRequest = {
  mode: 'window'
  category: CategoryId
  hours: number
  earliest: Iso
  latest: Iso
  district: string
  maxDistanceKm: number
}

export type BatchRequest = {
  mode: 'batch'
  category: CategoryId
  quantity: number
  material?: Material
  dims?: Dims
  toleranceMm?: number
  deadline: Iso
  district: string
  maxDistanceKm: number
}

export type Requirement = WindowRequest | BatchRequest

export type Quote = {
  hours: number
  /** rate × hours */
  base: Cents
  extra: Cents
  extraLabel: string
  /** What the buyer pays. */
  total: Cents
  /** 15% of total, the fee sits inside the total, it is not added on top. */
  platformFee: Cents
  ownerNet: Cents
}

export type Match = {
  listingId: string
  ownerId: string
  slotId: string
  /** The concrete window this booking would occupy, not the whole idle gap. */
  start: Iso
  end: Iso
  score: number
  /** 1 while feasibility is rules-based. A calibrated probability if that ever changes. */
  confidence: number
  reasons: string[]
  quote: Quote
  distanceKm: number
}

export type BookingStatus =
  | 'requested'
  | 'accepted'
  | 'declined'
  | 'active'
  | 'completed'
  | 'cancelled'

export type Outcome = {
  onTime: boolean
  quality: number
  /** What the buyer wrote. Becomes a review the next buyer reads. */
  note?: string
  /** The short things people say most, picked rather than typed. */
  tags?: string[]
}

/**
 * The feedback loop, as the next buyer sees it. The ranking already moves on
 * outcomes (on time, quality); a review is the same outcome with the reason
 * attached, which is the part a stranger deciding whether to trust an owner
 * actually reads.
 */
export type Review = {
  id: string
  listingId: string
  ownerId: string
  author: string
  initials: string
  /** 1 to 5. */
  rating: number
  onTime: boolean
  text: string
  tags: string[]
  at: Iso
}

export type Booking = {
  id: string
  match: Match
  requirement: Requirement
  status: BookingStatus
  createdAt: Iso
  /** Who asked. Absent means the app's own user, present when someone is
   *  requesting capacity from them, which is what the Earn inbox shows. */
  requesterId?: string
  /** Set when the owner declines, so the buyer is told why rather than just refused. */
  declineReason?: string
  outcome?: Outcome
}

export type World = {
  owners: Owner[]
  listings: Listing[]
  slots: Slot[]
  districts: Record<string, District>
  reviews: Review[]
}

/** Null until they have been rated at all, "new" is not the same as "bad". */
export const rating = (o: Owner): number | null =>
  o.jobsDone > 0 ? o.ratingSum / o.jobsDone : null

/** Unrated owners sit mid-scale rather than at zero. */
export const reliability = (o: Owner): number =>
  o.jobsDone > 0 ? o.onTimeJobs / o.jobsDone : 0.5

/** Fold a finished booking into the owner's record. Pure, returns a new owner.
 *  This is the write half of the loop: outcomes change where people rank next time. */
export const applyOutcome = (o: Owner, outcome: Outcome): Owner => ({
  ...o,
  ratingSum: o.ratingSum + outcome.quality,
  jobsDone: o.jobsDone + 1,
  onTimeJobs: o.onTimeJobs + (outcome.onTime ? 1 : 0),
})

export const isWindow = (l: Listing): l is WindowListing => l.mode === 'window'
export const isBatch = (l: Listing): l is BatchListing => l.mode === 'batch'
