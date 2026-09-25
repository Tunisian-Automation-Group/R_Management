// The only module that knows where data lives: the Cappy API, over HTTP, read
// through TanStack Query so every screen shares one cache.
//
// The server serialises the app's own types (camelCase, integer cents, ISO
// strings, optional fields left out rather than null), so reads come back as
// the types in domain/types.ts. Matching, pricing and availability all happen
// on the server; the app shows what it is told.
import {
  QueryClient,
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query'
import type {
  Booking,
  District,
  Listing,
  Match,
  Offer,
  Outcome,
  Owner,
  Quote,
  Requirement,
  Review,
  Slot,
} from '../domain/types.ts'
import type { ReviewSummary } from '../domain/reviews.ts'
import type { SortKey } from '../domain/match.ts'
import { accessToken, refresh, useSession } from './auth.ts'

/**
 * Same origin by default: the gateway (or CloudFront) serves the app at / and
 * the API at /api, and the Vite dev server proxies /api to the gateway, so
 * nothing needs CORS. Set VITE_API_URL when the app is hosted apart from it.
 */
const API: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message)
  }
}

async function send(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<Response> {
  const form = body instanceof FormData
  const attempt = async () => {
    const token = await accessToken()
    return fetch(`${API}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(body !== undefined && !form ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      },
      body: body === undefined ? undefined : form ? body : JSON.stringify(body),
    })
  }
  let res: Response
  try {
    res = await attempt()
    // An access token revoked or expired early: refresh once and try again.
    if (res.status === 401 && (await refresh())) res = await attempt()
  } catch {
    throw new ApiError('Cannot reach Cappy. Check your connection and try again.', 0, 'offline')
  }
  return res
}

async function call<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await send(method, path, body, headers)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? (JSON.parse(text) as unknown) : undefined
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string } } | undefined)?.error
    throw new ApiError(err?.message ?? `${method} ${path} failed (${res.status})`, res.status, err?.code ?? 'error')
  }
  return data as T
}

const get = <T>(path: string) => call<T>('GET', path)
const post = <T>(path: string, body?: unknown, headers?: Record<string, string>) => call<T>('POST', path, body, headers)
const put = <T>(path: string, body?: unknown) => call<T>('PUT', path, body)
const del = <T>(path: string) => call<T>('DELETE', path)
const qs = (params: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

// --- shapes the server returns beyond the domain types ------------------------------

export type Page<T> = { items: T[]; nextCursor?: string }
export type Me = { id: string; homeDistrict: string; owner?: Owner }
export type City = { city: string; country: string; lat: number; lng: number; listings: number }
export type MatchView = { match: Match; listing: Listing; owner: Owner }
/** `slots` only on the owner's own listings (GET /me/listings). */
export type ListingView = { listing: Listing; owner: Owner; saved?: boolean; slots?: Slot[] }
export type ListingDetail = {
  listing: Listing
  owner: Owner
  district: District
  slots: Slot[]
  reviews: ReviewSummary
  saved?: boolean
}
export type Spotlight = {
  listing: Listing
  owner: Owner
  offer: Offer
  distanceKm: number
  fromPrice: number
  freeNow: boolean
  windowStart: string
}
export type QuoteOut = { quote?: Quote; feasibility: { feasible: boolean; blockers: string[]; reasons: string[] } }
export type PaymentStart = { clientSecret: string; intentId: string }
export type BookingCreated = { booking: Booking; payment?: PaymentStart }
export type PaymentsConfig = { provider: 'fake' | 'stripe'; publishableKey?: string }
export type ConnectStatus = { connected: boolean; payoutsEnabled: boolean; detailsSubmitted: boolean }
export type PaymentView = { bookingId: string; status: string; amount: number; currency: string }
export type Profile = { name: string; kind: 'person' | 'business'; district: string }

// --- the cache ----------------------------------------------------------------------

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // A 4xx will not change on a retry; only the network or a 5xx might.
      retry: (n, err) => n < 2 && !(err instanceof ApiError && err.status >= 400 && err.status < 500),
    },
  },
})

const REF = { staleTime: Infinity } // reference data: districts, cities

export const useMeQuery = () => {
  const session = useSession()
  return useQuery({ queryKey: ['me', session?.sub], queryFn: () => get<Me>('/me'), enabled: Boolean(session) })
}

export const useDistricts = () =>
  useQuery({ queryKey: ['districts'], queryFn: () => get<Record<string, District>>('/districts'), ...REF })

export const useCities = () => useQuery({ queryKey: ['cities'], queryFn: () => get<City[]>('/cities'), ...REF })

export const useSpotlight = (district: string, maxKm: number, withinHours = 24) =>
  useQuery({
    queryKey: ['spotlight', district, maxKm, withinHours],
    queryFn: () => get<Spotlight[]>(`/browse/spotlight${qs({ district, maxKm, withinHours, limit: 60 })}`),
    enabled: Boolean(district),
    placeholderData: keepPreviousData,
  })

export const useMatches = (requirement: Requirement | null, sort: SortKey) =>
  useQuery({
    queryKey: ['matches', requirement, sort],
    queryFn: () => post<MatchView[]>('/matches', { requirement, sort, limit: 50 }),
    enabled: Boolean(requirement),
    placeholderData: keepPreviousData,
  })

export const useSearch = (q: string, metro?: string) =>
  useQuery({
    queryKey: ['search', q, metro],
    queryFn: () => get<Page<ListingView>>(`/search${qs({ q: q.trim(), metro, limit: 30 })}`),
    enabled: q.trim().length >= 2, // the server wants two characters
    placeholderData: keepPreviousData,
  })

export const getListing = (id: string) => get<ListingDetail>(`/listings/${id}`)
export const getOwner = (id: string) => get<Owner>(`/owners/${id}`)

export const useListing = (id: string | undefined) =>
  useQuery({ queryKey: ['listing', id], queryFn: () => getListing(id!), enabled: Boolean(id) })

export const useReviews = (id: string | undefined) =>
  useQuery({
    queryKey: ['reviews', id],
    // ponytail: first 100 reviews; add "load more" with nextCursor once a listing has more.
    queryFn: () => get<Page<Review>>(`/listings/${id}/reviews${qs({ limit: 100 })}`),
    enabled: Boolean(id),
  })

export const useQuote = (listingId: string | undefined, requirement: Requirement | null) =>
  useQuery({
    queryKey: ['quote', listingId, requirement],
    queryFn: () => post<QuoteOut>('/quote', { requirement, listingId }),
    enabled: Boolean(listingId && requirement),
    placeholderData: keepPreviousData,
  })

export const useOffers = (listingId: string | undefined, hours: number | null) =>
  useQuery({
    queryKey: ['offers', listingId, hours],
    queryFn: () => get<Offer[]>(`/listings/${listingId}/offers${qs({ hours: hours ?? undefined, limit: 120 })}`),
    enabled: Boolean(listingId && hours),
    placeholderData: keepPreviousData,
  })

export const useOwner = (id: string | undefined) =>
  useQuery({ queryKey: ['owner', id], queryFn: () => getOwner(id!), enabled: Boolean(id) })

/** Still waiting on someone else: the page keeps itself current. */
const LIVE = new Set(['awaiting_payment', 'requested'])

export const useBookings = (role: 'requester' | 'owner') => {
  const session = useSession()
  return useQuery({
    queryKey: ['bookings', role, session?.sub],
    // ponytail: newest 100; page with nextCursor when someone has more.
    queryFn: () => get<Page<Booking>>(`/bookings${qs({ role, limit: 100 })}`),
    enabled: Boolean(session),
    refetchInterval: (q) => (q.state.data?.items.some((b) => LIVE.has(b.status)) ? 4000 : false),
  })
}

export const useBooking = (id: string | undefined) =>
  useQuery({
    queryKey: ['booking', id],
    queryFn: () => get<Booking>(`/bookings/${id}`),
    enabled: Boolean(id),
    refetchInterval: (q) => (q.state.data && LIVE.has(q.state.data.status) ? 2500 : false),
  })

export const useSaved = () => {
  const session = useSession()
  return useQuery({
    queryKey: ['saved', session?.sub],
    queryFn: () => get<Page<ListingView>>(`/saved${qs({ limit: 100 })}`),
    enabled: Boolean(session),
  })
}

export const useMyListings = () => {
  const session = useSession()
  return useQuery({
    queryKey: ['myListings', session?.sub],
    queryFn: () => get<Page<ListingView>>(`/me/listings${qs({ limit: 100 })}`),
    enabled: Boolean(session),
  })
}

export const usePaymentsConfig = () =>
  useQuery({ queryKey: ['paymentsConfig'], queryFn: () => get<PaymentsConfig>('/payments/config'), ...REF })

export const useConnectStatus = () => {
  const session = useSession()
  return useQuery({
    queryKey: ['connect', session?.sub],
    queryFn: () => get<ConnectStatus>('/payments/connect/status'),
    enabled: Boolean(session),
  })
}

// --- writes -------------------------------------------------------------------------

export const saveProfile = (p: Profile) => put<Owner>('/me', p)

/** The server prices the window itself; the Idempotency-Key makes a retried
 *  tap (a flaky network, a double click) the same booking, not two. */
export const requestBooking = (
  body: { requirement: Requirement; listingId: string; slotId: string; start: string; end: string },
  idempotencyKey: string,
) => post<BookingCreated>('/bookings', body, { 'Idempotency-Key': idempotencyKey })

export type BookingAction = 'accept' | 'start' | 'complete' | 'cancel'
export const actOnBooking = (id: string, action: BookingAction) => post<Booking>(`/bookings/${id}/${action}`)
export const declineBooking = (id: string, reason: string) => post<Booking>(`/bookings/${id}/decline`, { reason })
export const rateBooking = (id: string, outcome: Outcome) => post<Booking>(`/bookings/${id}/rate`, outcome)

/** A listing as the owner writes it: ids and the owner come from the server. */
export type ListingDraft = Listing extends infer L ? (L extends Listing ? Omit<L, 'id' | 'ownerId'> : never) : never

export const addListing = (listing: ListingDraft, slots: Omit<Slot, 'id' | 'listingId'>[]) =>
  post<{ listing: Listing; slots: Slot[] }>('/listings', { listing, slots })
export const pauseListing = (id: string) => post<Listing>(`/listings/${id}/pause`)
export const resumeListing = (id: string) => post<Listing>(`/listings/${id}/resume`)
export const removeListing = (id: string) => del<void>(`/listings/${id}`)

export const startPayouts = () => post<{ url: string }>('/payments/connect/onboarding')

/** One photograph in, its URL out, to go in `Listing.photos`. */
export async function uploadPhoto(image: Blob, filename = 'photo.jpg'): Promise<string> {
  const form = new FormData()
  form.append('file', image, filename)
  return (await call<{ url: string }>('POST', '/uploads', form)).url
}

/** A write, then re-read whatever it changed. Errors reach the caller. */
export function useWrite<A extends unknown[], R>(fn: (...args: A) => Promise<R>, invalidates: QueryKey[]) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (args: A) => fn(...args),
    onSettled: () => Promise.all(invalidates.map((queryKey) => qc.invalidateQueries({ queryKey }))),
  })
}

/** Hearting. The button shows the tap at once (mutation variables); the
 *  server's list replaces it when the write lands. */
export function useSaveToggle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, on }: { id: string; on: boolean }) => (on ? put(`/saved/${id}`) : del(`/saved/${id}`)),
    onSettled: () => qc.invalidateQueries({ queryKey: ['saved'] }),
  })
}

