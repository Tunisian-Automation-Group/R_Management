import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react'
import type {
  Booking,
  BookingStatus,
  CategoryId,
  Listing,
  Outcome,
  Requirement,
  Review,
  Slot,
  World,
} from '../domain/types.ts'
import { byRecent } from '../domain/reviews.ts'
import { applyOutcome } from '../domain/types.ts'
import { category } from '../domain/categories.ts'
import { ME, HOME_DISTRICT } from '../data/seed.ts'
import * as repo from '../data/repo.ts'

export { ME }

export type Search = {
  /** Where the user is searching from. A district name; its city and country
   *  come from the registry, so switching city is a single field change. */
  district: string
  categoryId: CategoryId | null
  /** Window mode: how long you want it. */
  hours: number
  /** Batch mode: how many you need. */
  quantity: number
  maxDistanceKm: number
  /** How far out you are willing to look. */
  withinDays: number
  query: string
}

export type State = {
  ready: boolean
  world: World
  bookings: Booking[]
  /** Listings this person hearted, newest first. A shortlist, not a booking. */
  saved: string[]
  search: Search
  toast: string | null
}

// Domain events, not UI events. Each maps to something that would really happen,
// so a backend grows around this shape rather than replacing it.
export type Event =
  | { type: 'WORLD_LOADED'; world: World; bookings: Booking[]; saved: string[] }
  | { type: 'LISTING_SAVED'; id: string }
  | { type: 'LISTING_UNSAVED'; id: string }
  | { type: 'SEARCH_CHANGED'; patch: Partial<Search> }
  | { type: 'BOOKING_REQUESTED'; booking: Booking }
  | { type: 'BOOKING_ACCEPTED'; id: string }
  | { type: 'BOOKING_DECLINED'; id: string; reason: string }
  | { type: 'BOOKING_STARTED'; id: string }
  | { type: 'BOOKING_COMPLETED'; id: string }
  | { type: 'BOOKING_CANCELLED'; id: string }
  | { type: 'BOOKING_RATED'; id: string; outcome: Outcome }
  | { type: 'LISTING_ADDED'; listing: Listing; slots: Slot[] }
  | { type: 'LISTING_PAUSED'; id: string }
  | { type: 'LISTING_REMOVED'; id: string }
  | { type: 'LISTING_RESUMED'; id: string }
  | { type: 'TOAST'; message: string }
  | { type: 'TOAST_CLEARED' }
  | { type: 'DEMO_RESET'; world: World }

const emptyWorld: World = { owners: [], listings: [], slots: [], districts: {}, reviews: [] }

/**
 * One radius for everyone. Fabrication is regional and a saw is local, but the
 * old split forced the user to declare which kind of buyer they were before the
 * app would show them anything. 75 km covers a city and its industrial belt,
 * which is the catchment the plan targets, and it is one of Browse's own RADII
 * so the filter opens with the current value selected.
 */
export const defaultSearch: Search = {
  district: HOME_DISTRICT,
  categoryId: null,
  hours: 4,
  quantity: 50,
  maxDistanceKm: 75,
  withinDays: 14,
  query: '',
}

const initial: State = {
  ready: false,
  world: emptyWorld,
  bookings: [],
  saved: [],
  search: defaultSearch,
  toast: null,
}

const setStatus = (bookings: Booking[], id: string, status: BookingStatus, extra?: Partial<Booking>) =>
  bookings.map((b) => (b.id === id ? { ...b, status, ...extra } : b))

/** Pure. Same state plus same event always gives the same next state. */
export function reduce(state: State, e: Event): State {
  switch (e.type) {
    case 'WORLD_LOADED':
      return { ...state, ready: true, world: e.world, bookings: e.bookings, saved: e.saved }

    case 'LISTING_SAVED':
      return state.saved.includes(e.id) ? state : { ...state, saved: [e.id, ...state.saved] }

    case 'LISTING_UNSAVED':
      return { ...state, saved: state.saved.filter((id) => id !== e.id) }

    case 'SEARCH_CHANGED': {
      const search = { ...state.search, ...e.patch }

      // Carrying the last duration into a new category produces guaranteed-empty
      // searches: two hours of a PA rig is below every minimum
      // booking in those categories. Adopt the category's own first option.
      const pickedCategory =
        e.patch.categoryId !== undefined && e.patch.categoryId !== state.search.categoryId
      if (pickedCategory && search.categoryId) {
        const meta = category(search.categoryId)
        if (meta.mode === 'window' && meta.quickHours?.length && e.patch.hours === undefined) {
          search.hours = meta.quickHours[0]
        }
      }

      return { ...state, search }
    }

    case 'BOOKING_REQUESTED':
      return { ...state, bookings: [e.booking, ...state.bookings] }

    case 'BOOKING_ACCEPTED':
      return { ...state, bookings: setStatus(state.bookings, e.id, 'accepted') }

    case 'BOOKING_DECLINED':
      return {
        ...state,
        bookings: setStatus(state.bookings, e.id, 'declined', { declineReason: e.reason }),
      }

    case 'BOOKING_STARTED':
      return { ...state, bookings: setStatus(state.bookings, e.id, 'active') }

    case 'BOOKING_COMPLETED':
      return { ...state, bookings: setStatus(state.bookings, e.id, 'completed') }

    case 'BOOKING_CANCELLED':
      return { ...state, bookings: setStatus(state.bookings, e.id, 'cancelled') }

    case 'BOOKING_RATED': {
      const booking = state.bookings.find((b) => b.id === e.id)
      if (!booking || booking.outcome) return state
      // The write half of the loop: a finished booking changes where this owner
      // ranks for everyone else from now on.
      return {
        ...state,
        world: {
          ...state.world,
          owners: state.world.owners.map((o) =>
            o.id === booking.match.ownerId ? applyOutcome(o, e.outcome) : o,
          ),
        },
        bookings: state.bookings.map((b) => (b.id === e.id ? { ...b, outcome: e.outcome } : b)),
      }
    }

    case 'LISTING_ADDED':
      return {
        ...state,
        world: {
          ...state.world,
          listings: [e.listing, ...state.world.listings],
          slots: [...state.world.slots, ...e.slots],
        },
      }

    case 'LISTING_REMOVED':
      return {
        ...state,
        world: {
          ...state.world,
          listings: state.world.listings.filter((l) => l.id !== e.id),
          slots: state.world.slots.filter((s) => s.listingId !== e.id),
        },
      }

    case 'LISTING_PAUSED':
    case 'LISTING_RESUMED': {
      const active = e.type === 'LISTING_RESUMED'
      return {
        ...state,
        world: {
          ...state.world,
          listings: state.world.listings.map((l) => (l.id === e.id ? { ...l, active } : l)),
        },
      }
    }

    case 'TOAST':
      return { ...state, toast: e.message }

    case 'TOAST_CLEARED':
      return { ...state, toast: null }

    case 'DEMO_RESET':
      return { ...initial, ready: true, world: e.world }

    default:
      return state
  }
}

const Ctx = createContext<{ state: State; send: (e: Event) => void } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, send] = useReducer(reduce, initial)

  useEffect(() => {
    void Promise.all([repo.getWorld(), repo.getBookings(), repo.getSaved()]).then(
      ([world, bookings, saved]) => send({ type: 'WORLD_LOADED', world, bookings, saved }),
    )
  }, [])

  useEffect(() => {
    if (state.ready) void repo.persist(state.world, state.bookings, state.saved)
  }, [state.ready, state.world, state.bookings, state.saved])

  // Hosts in this build are seeded people, so their reply is simulated on a short
  // timer rather than leaving every request pending forever. Requests against the
  // user's own listings are left alone, those are answered for real under Earn.
  const waiting = state.bookings
    .filter((b) => b.status === 'requested' && b.match.ownerId !== ME)
    .map((b) => b.id)
    .join(',')

  useEffect(() => {
    if (!waiting) return
    const timers = waiting.split(',').map((id) =>
      setTimeout(() => send({ type: 'BOOKING_ACCEPTED', id }), 5500),
    )
    return () => timers.forEach(clearTimeout)
  }, [waiting])

  const value = useMemo(() => ({ state, send }), [state])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useCappy() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useCappy used outside AppProvider')
  return ctx
}

/** Lookups every screen needs, memoised against the world. */
export function useLookups() {
  const { state } = useCappy()
  return useMemo(
    () => ({
      owner: (id: string) => state.world.owners.find((o) => o.id === id),
      listing: (id: string) => state.world.listings.find((l) => l.id === id),
      slotsFor: (listingId: string) =>
        state.world.slots.filter((s) => s.listingId === listingId),
      myListings: () => state.world.listings.filter((l) => l.ownerId === ME),
      me: () => state.world.owners.find((o) => o.id === ME)!,
      /**
       * Seeded reviews plus the ones this person wrote. Their own are not stored
       * twice: a rated booking already carries the outcome, so it is read back
       * as a review here and appears on the listing the moment it is submitted.
       */
      reviewsFor: (listingId: string): Review[] => {
        const me = state.world.owners.find((o) => o.id === ME)
        const own: Review[] = state.bookings
          .filter((b) => b.match.listingId === listingId && b.outcome && !b.requesterId)
          .map((b) => ({
            id: `rv_${b.id}`,
            listingId,
            ownerId: b.match.ownerId,
            author: 'You',
            initials: me?.initials ?? 'ME',
            rating: b.outcome!.quality,
            onTime: b.outcome!.onTime,
            text: b.outcome!.note ?? '',
            tags: b.outcome!.tags ?? [],
            at: b.match.end,
          }))
        return [...own, ...state.world.reviews.filter((r) => r.listingId === listingId)].sort(byRecent)
      },
    }),
    [state.world, state.bookings],
  )
}

/** The search turned into something the matcher understands. */
export function buildRequirement(search: Search, now: Date): Requirement | null {
  if (!search.categoryId) return null
  const meta = category(search.categoryId)
  const until = new Date(now.getTime() + search.withinDays * 86_400_000).toISOString()

  if (meta.mode === 'window') {
    return {
      mode: 'window',
      category: search.categoryId,
      hours: search.hours,
      earliest: now.toISOString(),
      latest: until,
      district: search.district,
      maxDistanceKm: search.maxDistanceKm,
    }
  }
  return {
    mode: 'batch',
    category: search.categoryId,
    quantity: search.quantity,
    deadline: until,
    district: search.district,
    maxDistanceKm: search.maxDistanceKm,
  }
}
