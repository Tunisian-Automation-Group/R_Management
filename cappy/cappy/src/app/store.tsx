import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
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
import * as repo from '../data/repo.ts'
import type { Account } from '../data/repo.ts'

/** Who is signed in on this device, as the accounts service knows them. */
export type Session = Account

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
  /** Why the first load failed, when it did. The shell offers a retry. */
  loadError: string | null
  /** Null while browsing anonymously. Browsing is open; acting needs a person. */
  session: Session | null
  world: World
  bookings: Booking[]
  /** Listings this person hearted, newest first. A shortlist, not a booking. */
  saved: string[]
  search: Search
  toast: string | null
}

// Domain events, not UI events. Each maps to something that really happens on
// the server: the store applies it here first, forwards it, then takes the
// server's answer as the truth.
export type Event =
  | {
      type: 'WORLD_LOADED'
      world: World
      bookings: Booking[]
      saved: string[]
      homeDistrict: string
      session: Session | null
    }
  | { type: 'LOAD_FAILED'; message: string }
  | { type: 'LOAD_RETRY' }
  /** What the server says now. Any part may be omitted to leave it as it is. */
  | { type: 'SYNCED'; world?: World; bookings?: Booking[]; saved?: string[] }
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
 *
 * The district is a placeholder until `GET /me` says where this person starts.
 */
export const defaultSearch: Search = {
  district: 'Kreuzberg',
  categoryId: null,
  hours: 4,
  quantity: 50,
  maxDistanceKm: 75,
  withinDays: 14,
  query: '',
}

const initial: State = {
  ready: false,
  loadError: null,
  session: null,
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
      return {
        ...state,
        ready: true,
        loadError: null,
        session: e.session,
        world: e.world,
        bookings: e.bookings,
        saved: e.saved,
        // Only the first load moves the search origin: a person who switched
        // city and then lost the connection keeps the city they chose.
        search: state.ready ? state.search : { ...state.search, district: e.homeDistrict },
      }

    case 'LOAD_FAILED':
      return { ...state, loadError: e.message }

    case 'LOAD_RETRY':
      return { ...state, loadError: null }

    case 'SYNCED':
      return {
        ...state,
        world: e.world ?? state.world,
        bookings: e.bookings ?? state.bookings,
        saved: e.saved ?? state.saved,
      }

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
      // ranks for everyone else from now on. The server does the same and its
      // record replaces this one on the next sync.
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
        saved: state.saved.filter((id) => id !== e.id),
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

/**
 * The server call behind an event, and which parts of the state to re-read
 * once it lands. Events with no entry are the app's own business.
 */
type Sync = { world?: true; bookings?: true; saved?: true }

function forward(e: Event): { call: Promise<unknown>; then: Sync } | null {
  switch (e.type) {
    case 'BOOKING_REQUESTED':
      // The server prices the window itself; its quote replaces the preview.
      return { call: repo.requestBooking(e.booking), then: { bookings: true } }
    case 'BOOKING_ACCEPTED':
      return { call: repo.acceptBooking(e.id), then: { bookings: true } }
    case 'BOOKING_DECLINED':
      return { call: repo.declineBooking(e.id, e.reason), then: { bookings: true } }
    case 'BOOKING_STARTED':
      return { call: repo.startBooking(e.id), then: { bookings: true } }
    case 'BOOKING_COMPLETED':
      return { call: repo.completeBooking(e.id), then: { bookings: true } }
    case 'BOOKING_CANCELLED':
      return { call: repo.cancelBooking(e.id), then: { bookings: true } }
    case 'BOOKING_RATED':
      // The owner's record and the new review come back with the world.
      return { call: repo.rateBooking(e.id, e.outcome), then: { bookings: true, world: true } }
    case 'LISTING_ADDED':
      return { call: repo.addListing(e.listing, e.slots), then: { world: true } }
    case 'LISTING_PAUSED':
      return { call: repo.pauseListing(e.id), then: { world: true } }
    case 'LISTING_RESUMED':
      return { call: repo.resumeListing(e.id), then: { world: true } }
    case 'LISTING_REMOVED':
      return { call: repo.removeListing(e.id), then: { world: true, saved: true } }
    case 'LISTING_SAVED':
      return { call: repo.saveListing(e.id), then: { saved: true } }
    case 'LISTING_UNSAVED':
      return { call: repo.unsaveListing(e.id), then: { saved: true } }
    default:
      return null
  }
}

async function fetchSync(parts: Sync): Promise<Extract<Event, { type: 'SYNCED' }>> {
  const [world, bookings, saved] = await Promise.all([
    parts.world ? repo.getWorld() : undefined,
    parts.bookings ? repo.getBookings() : undefined,
    parts.saved ? repo.getSaved() : undefined,
  ])
  return { type: 'SYNCED', world, bookings, saved }
}

const messageOf = (err: unknown) =>
  err instanceof Error && err.message ? err.message : 'Something went wrong. Please try again.'

/** Signing in, up and out. Each one reloads everything as that person. */
export type Auth = {
  signIn: (email: string, password: string) => Promise<void>
  register: (input: {
    email: string
    password: string
    name: string
    kind: 'person' | 'business'
    district: string
  }) => Promise<void>
  signOut: () => Promise<void>
}

const Ctx = createContext<{ state: State; send: (e: Event) => void; auth: Auth } | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reduce, initial)
  // Writes are forwarded one after another, so a reply to an earlier write can
  // never overwrite the effect of a later one.
  const queue = useRef<Promise<void>>(Promise.resolve())

  const load = useCallback(async () => {
    try {
      // The world is public. Who this is, what they booked and what they
      // hearted need a session; anonymous browsing gets the world alone.
      const session = await repo.getAccount()
      const [world, me, bookings, saved] = await Promise.all([
        repo.getWorld(),
        session ? repo.getMe() : null,
        session ? repo.getBookings() : [],
        session ? repo.getSaved() : [],
      ])
      dispatch({
        type: 'WORLD_LOADED',
        world,
        bookings,
        saved,
        homeDistrict: me?.homeDistrict ?? defaultSearch.district,
        session,
      })
    } catch (err) {
      dispatch({ type: 'LOAD_FAILED', message: messageOf(err) })
    }
  }, [])

  const auth = useMemo<Auth>(
    () => ({
      signIn: async (email, password) => {
        await repo.signIn(email, password)
        await load()
      },
      register: async (input) => {
        await repo.register(input)
        await load()
      },
      signOut: async () => {
        await repo.signOut()
        await load()
      },
    }),
    [load],
  )

  useEffect(() => {
    void load()
  }, [load])

  const send = useCallback(
    (e: Event) => {
      if (e.type === 'LOAD_RETRY') {
        dispatch(e)
        void load()
        return
      }
      dispatch(e)
      const fwd = forward(e)
      if (!fwd) return
      queue.current = queue.current
        .then(async () => {
          try {
            await fwd.call
            dispatch(await fetchSync(fwd.then))
          } catch (err) {
            // The server refused or is unreachable: say so, and put the screen
            // back to what the server holds rather than leave a phantom state.
            dispatch({ type: 'TOAST', message: messageOf(err) })
            try {
              dispatch(await fetchSync({ world: true, bookings: true, saved: true }))
            } catch {
              // Still offline. The next write, or a retry, will resync.
            }
          }
        })
        .catch(() => undefined)
    },
    [load],
  )

  // Hosts with nobody behind them are simulated on the server, which accepts
  // their requests after a few seconds; real hosts answer when they get to it.
  // Poll while anything is waiting on someone else, and re-read on focus so a
  // request answered on another device shows up.
  const me = state.session?.id
  const waiting = state.bookings.some((b) => b.status === 'requested' && b.match.ownerId !== me)

  useEffect(() => {
    if (!state.ready || !state.session) return
    const refresh = () => {
      if (document.visibilityState === 'hidden') return
      void repo
        .getBookings()
        .then((bookings) => dispatch({ type: 'SYNCED', bookings }))
        .catch(() => undefined)
    }
    const timer = waiting ? setInterval(refresh, 3000) : null
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      if (timer) clearInterval(timer)
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [state.ready, state.session, waiting])

  const value = useMemo(() => ({ state, send, auth }), [state, send, auth])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useCappy() {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useCappy used outside AppProvider')
  return ctx
}

/** The signed-in person's owner id, or '' when nobody is. Comparing an owner
 *  id against '' is always false, which is the right answer for a stranger. */
export function useMe(): string {
  return useCappy().state.session?.id ?? ''
}

/** Lookups every screen needs, memoised against the world. */
export function useLookups() {
  const { state } = useCappy()
  const ME = state.session?.id ?? ''
  return useMemo(
    () => ({
      owner: (id: string) => state.world.owners.find((o) => o.id === id),
      listing: (id: string) => state.world.listings.find((l) => l.id === id),
      slotsFor: (listingId: string) =>
        state.world.slots.filter((s) => s.listingId === listingId),
      myListings: () => state.world.listings.filter((l) => l.ownerId === ME),
      /** The signed-in person's owner record. Only call it behind a session check. */
      me: () => state.world.owners.find((o) => o.id === ME)!,
      /**
       * Reviews on a listing, newest first. The ones this person wrote appear
       * the instant they rate, read straight off the booking; the server writes
       * the same review under the same id (`rv_<bookingId>`) a moment later, so
       * that copy is dropped rather than shown twice. Reviews other accounts
       * wrote through the app carry `authorId` and read like any other.
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
        const ownIds = new Set(own.map((r) => r.id))
        return [
          ...own,
          ...state.world.reviews.filter((r) => r.listingId === listingId && !ownIds.has(r.id)),
        ].sort(byRecent)
      },
    }),
    [state.world, state.bookings, ME],
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
