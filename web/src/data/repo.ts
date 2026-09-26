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
  Business,
  Quote,
  Requirement,
  Review,
  Slot,
} from '../domain/types.ts'
import type { ReviewSummary } from '../domain/reviews.ts'
import type { SortKey } from '../domain/match.ts'
import { useMemo } from 'react'
import { attemptKeys } from '../domain/attempt.ts'
import { accessToken, endSession, refresh, useSession } from './auth.ts'
import { lang, t } from '../i18n.ts'
import { isNative, platform, shareFile } from '../native.ts'
import { flagOn } from '../domain/flags.ts'

/**
 * Same origin by default: the gateway (or CloudFront) serves the app at / and
 * the API at /api, and the Vite dev server proxies /api to the gateway, so
 * nothing needs CORS. Set VITE_API_URL when the app is hosted apart from it.
 */
const API: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'

/** Where relative media paths (`/media/…`) live: the API's origin when the app
 *  is hosted apart from it (a native shell), this origin otherwise. */
const MEDIA_ORIGIN = /^https?:\/\//.test(API) ? new URL(API).origin : ''
export const mediaUrl = (src: string) => (src.startsWith('/') ? `${MEDIA_ORIGIN}${src}` : src)

/** Where a bank or card check sends the buyer back. A shell has no web origin
 *  of its own (capacitor://localhost), so it is the API's domain, which the
 *  apps claim as universal / app links for /pay/. */
export const payReturnUrl = (bookingId: string) =>
  `${MEDIA_ORIGIN || location.origin}/pay/return?booking=${encodeURIComponent(bookingId)}`

/** This build's version, sent on every call so the server can tell old apps to update. */
export const APP_VERSION: string = __APP_VERSION__

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    /** Seconds the server asked us to wait before trying again (503s). */
    public readonly retryAfter?: number,
    /** When a refusal stops applying, if the server said (409 open_obligations). */
    public readonly until?: string,
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
        'X-App-Version': APP_VERSION,
        // The server renders notifications (and its messages) in the app's language.
        'Accept-Language': lang(),
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
    // Still refused with a fresh token: this session was ended elsewhere
    // (sign out everywhere, a deleted account; P-24). Sign out once, cleanly,
    // in every tab, instead of retrying.
    if (res.status === 401 && (await tokenExpired(res.clone()))) endSession()
  } catch {
    throw new ApiError(t('Cannot reach Cappy. Check your connection and try again.'), 0, 'offline')
  }
  return res
}

const tokenExpired = async (res: Response) =>
  (await res.json().catch(() => ({})))?.error?.code === 'token_expired'

async function call<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  return read<T>(await send(method, path, body, headers))
}

/** The answer's body, or the ApiError it stands for. */
async function read<T>(res: Response): Promise<T> {
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown
  try {
    data = text ? JSON.parse(text) : undefined
  } catch {
    data = undefined // a proxy's HTML error page, say
  }
  if (!res.ok) {
    type Body = { code?: string; message?: string; detail?: string; until?: string; details?: { until?: string | null } }
    const top = data as (Body & { error?: Body }) | undefined
    const err = top?.error ?? (top?.code ? { ...top, message: top.message ?? top.detail } : undefined)
    const wait = Number(res.headers.get('Retry-After'))
    // A fault on our side says so, with the reference support can look up (U-24).
    const ref = res.headers.get('x-request-id')
    const ours = res.status >= 500 && res.status !== 503
    throw new ApiError(
      ours
        ? ref
          ? t('Something went wrong on our side. Try again; if it keeps happening, tell us reference {ref}.', { ref })
          : t('Something went wrong on our side. Try again in a moment.')
        : res.status === 429 && !err?.message
          ? Number.isFinite(wait) && wait > 0
            ? t('Too many tries. Wait {n} seconds and try again.', { n: Math.ceil(wait) })
            : t('Too many tries. Wait a few minutes and try again.')
          : // The server speaks English; the catalogue translates what it knows.
          err?.message
          ? t(err.message)
          : t('Something went wrong ({status}). Try again.', { status: res.status }),
      res.status,
      err?.code ?? 'error',
      Number.isFinite(wait) && wait > 0 ? wait : undefined,
      err?.details?.until ?? err?.until ?? top?.until ?? undefined,
    )
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
/** `slots` and `address` only on the owner's own listings (GET /me/listings). */
export type ListingView = {
  listing: Listing
  owner: Owner
  saved?: boolean
  slots?: Slot[]
  address?: string
  /** Waiting for a quick staff check before anyone else can see it. */
  held?: boolean
}
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
  /** ISO 4217 of `fromPrice` (M-3). */
  currency?: string
  freeNow: boolean
  windowStart: string
}
export type QuoteOut = { quote?: Quote; feasibility: { feasible: boolean; blockers: string[]; reasons: string[] } }
export type PaymentStart = { clientSecret: string; intentId: string }
export type BookingCreated = { booking: Booking; payment?: PaymentStart }
export type PaymentsConfig = { provider: 'fake' | 'stripe'; publishableKey?: string }
export type ConnectStatus = { connected: boolean; payoutsEnabled: boolean; detailsSubmitted: boolean }
export type PaymentView = { bookingId: string; status: string; amount: number; currency: string }
export type Profile = {
  name: string
  kind: 'person' | 'business'
  district: string
  /** Needed when the profile is first created (S-5). */
  adult?: boolean
  business?: Business
}

// --- the cache ----------------------------------------------------------------------

// A 4xx will not change on a retry; only the network or a 5xx might.
const transient = (n: number, err: unknown) => n < 2 && !(err instanceof ApiError && err.status >= 400 && err.status < 500)
// Back off, and never sooner than the server asked: a busy service that
// says "come back in 5 s" must not get every client back in 1.
const backoff = (n: number, err: unknown) =>
  Math.max(Math.min(1000 * 2 ** n, 30_000), err instanceof ApiError && err.retryAfter ? err.retryAfter * 1000 : 0)

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: transient, retryDelay: backoff },
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

/** Free-text search needs three characters (what the trigram index can use). */
export const SEARCH_MIN = 3

export const useSearch = (q: string, metro?: string) =>
  useQuery({
    queryKey: ['search', q, metro],
    queryFn: () => get<Page<ListingView>>(`/search${qs({ q: q.trim(), metro, limit: 30 })}`),
    enabled: q.trim().length >= SEARCH_MIN,
    placeholderData: keepPreviousData,
  })

// The API leaves out fields it has no value for (no reviews yet: no average).
// Fill them here, once, so no screen meets `undefined` where it expects null.
export const getListing = (id: string) =>
  get<ListingDetail>(`/listings/${id}`).then((d) => ({
    ...d,
    reviews: {
      ...d.reviews,
      count: d.reviews?.count ?? 0,
      topTags: d.reviews?.topTags ?? [],
      average: d.reviews?.average ?? null,
      onTimeShare: d.reviews?.onTimeShare ?? null,
    },
  }))
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

export type AppConfig = {
  minVersion: string
  latestVersion?: string
  flags?: Record<string, boolean>
  rollouts?: Record<string, number>
}
export const useAppConfig = () =>
  useQuery({
    queryKey: ['appConfig'],
    queryFn: () => get<AppConfig>('/app-config'),
    staleTime: 10 * 60_000,
    retry: false, // an older backend without it must not block the app
  })

// --- crash reports (S-7) ------------------------------------------------------------------

const reported = new Set<string>()
/**
 * Tells the server a screen broke: the message, stack, route and version, never
 * who it was (no token, no ids beyond the path) and nothing stored on the
 * device, so no consent is needed (§ 25 TDDDG). Once per message, at most 10 a session.
 */
export function reportClientError(error: unknown): void {
  const e = error instanceof Error ? error : new Error(String(error))
  const message = (e.message || 'unknown error').slice(0, 2000)
  if (reported.has(message) || reported.size >= 10) return
  reported.add(message)
  void fetch(`${API}/client-errors`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    keepalive: true,
    body: JSON.stringify({
      message,
      stack: e.stack?.slice(0, 6000),
      route: location.pathname.slice(0, 300),
      appVersion: APP_VERSION.slice(0, 40),
      platform,
    }),
  }).catch(() => {}) // a report that cannot be sent is not worth a second error
}

/** Whether a feature is on for the signed-in person (S-26). Off while app-config loads. */
export function useFlag(name: string): boolean {
  const config = useAppConfig()
  const session = useSession()
  return flagOn(name, config.data, session?.sub)
}

/** a < b for dotted versions ("1.2.10" > "1.2.9"). */
export function versionBelow(a: string, b: string): boolean {
  const pa = a.split('.').map(Number)
  const pb = b.split('.').map(Number)
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] || 0) - (pb[i] || 0)
    if (d !== 0) return d < 0
  }
  return false
}

// --- writes -------------------------------------------------------------------------

export const saveProfile = (p: Profile) => put<Owner>('/me', p)

/** Everything of mine the platform holds, as a file download. */
export async function exportMyData(): Promise<void> {
  const res = await send('GET', '/me/export')
  if (!res.ok) throw new ApiError(t('Could not prepare your data. Try again.'), res.status, 'export')
  const blob = await res.blob()
  // A store shell has no downloads: the file goes to the share sheet.
  if (await shareFile('cappy-my-data.json', await blob.text())) return
  const file = new File([blob], 'cappy-my-data.json', { type: 'application/json' })
  // Phones (and the store shells' web views) cannot save an <a download>; they
  // can hand a file to the share sheet ("Save to Files", mail, AirDrop).
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: t('My Cappy data') })
      return
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return // they closed the sheet
    }
  }
  const url = URL.createObjectURL(file)
  const a = document.createElement('a')
  a.href = url
  a.download = file.name
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
  // Safari starts the download after the click returns: revoking at once
  // cancels it. A minute is plenty.
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

/** The server side of deleting an account (409 while a booking is open). */
export const deleteMe = () => del<void>('/me')

/** The server prices the window itself; the Idempotency-Key makes a retried
 *  tap (a flaky network, a double click) the same booking, not two. */
export const requestBooking = (
  body: { requirement: Requirement; listingId: string; slotId: string; start: string; end: string },
  idempotencyKey: string,
) => post<BookingCreated>('/bookings', body, { 'Idempotency-Key': idempotencyKey })

export type BookingAction = 'accept' | 'start' | 'complete' | 'cancel'
export const actOnBooking = (id: string, action: BookingAction) => post<Booking>(`/bookings/${id}/${action}`)
export const declineBooking = (id: string, reason: string) => post<Booking>(`/bookings/${id}/decline`, { reason })
export const disputeBooking = (id: string, reason: string) => post<Booking>(`/bookings/${id}/dispute`, { reason })
/** The card step for a booking still awaiting payment (404 once there is nothing to pay). */
export const getBookingPayment = (id: string) => get<PaymentStart>(`/bookings/${id}/payment`)
export const rateBooking = (id: string, outcome: Outcome, key?: string) => post<Booking>(`/bookings/${id}/rate`, outcome, idem(key))
/** Two-way reviews: the owner rates the renter once the booking is completed. */
export const rateRenter = (id: string, quality: number, key?: string) =>
  post<Booking>(`/bookings/${id}/rate-renter`, { quality }, idem(key))
/** Either side says the other never came (S-11): allowed from the start (the owner: +30 min) to +2 h. */
export const reportNoShow = (id: string) => post<Booking>(`/bookings/${id}/no-show`)

export type CancellationQuote = { refundAmount: number; currency: string; policy: string }
/** What cancelling now would refund, straight from the server's rule. */
export const useCancellationQuote = (id: string, enabled: boolean) =>
  useQuery({
    queryKey: ['cancellation', id],
    queryFn: () => get<CancellationQuote>(`/bookings/${id}/cancellation`),
    enabled,
    staleTime: 0,
  })

export type Invoice = {
  number: string
  bookingId: string
  net: number
  vatRateBps: number
  vat: number
  gross: number
  currency: string
  issuedAt: string
  /** What it is for, from the server (V3-2): "Cappy fee for …". */
  description?: string
  title?: string
  serviceStart?: string
  serviceEnd?: string
}
export const useInvoices = () => {
  const session = useSession()
  return useQuery({ queryKey: ['invoices', session?.sub], queryFn: () => get<Invoice[]>('/payments/invoices'), enabled: Boolean(session) })
}
/** The printable invoice needs the token, so it is fetched and opened as a blob. */
export async function openInvoice(number: string): Promise<void> {
  // A store shell has no tabs: the invoice goes to the share sheet (print, save, mail).
  if (isNative) {
    const res = await send('GET', `/payments/invoices/${encodeURIComponent(number)}`)
    if (!res.ok) throw new ApiError(t('Could not open the invoice. Try again.'), res.status, 'error')
    await shareFile(`${number}.html`, await res.text())
    return
  }
  const win = window.open('', '_blank') // opened in the click, or popup blockers step in
  const res = await send('GET', `/payments/invoices/${encodeURIComponent(number)}`)
  if (!res.ok) {
    win?.close()
    throw new ApiError(t('Could not open the invoice. Try again.'), res.status, 'error')
  }
  const url = URL.createObjectURL(new Blob([await res.text()], { type: 'text/html' }))
  if (win) win.location.href = url
  else window.location.href = url
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

export type Identity = { status: 'none' | 'pending' | 'requires_input' | 'verified'; clientSecret?: string }
/** Stripe Identity: a one-time document and selfie check (payments service). */
/** Starts the ID check. `consent` is the person's tick in the sheet (P-18): the
 *  server records it with the session and refuses without it. */
export const startIdentity = () => post<Identity>('/payments/identity/session', { consent: true })
export const getIdentity = () => get<Identity>('/payments/identity')

/** A listing as the owner writes it: ids and the owner come from the server. */
export type ListingDraft = Listing extends infer L ? (L extends Listing ? Omit<L, 'id' | 'ownerId'> : never) : never

/** Creates carry an Idempotency-Key (U-6): a double tap or a retried request
 *  after a timeout is the same listing, not two. */
const idem = (key?: string) => (key ? { 'Idempotency-Key': key } : undefined)

/** One Idempotency-Key per attempt at the same request (FL-1, domain/attempt.ts). */
export function useAttemptKey() {
  return useMemo(() => attemptKeys(), [])
}

export const addListing = (listing: ListingDraft, slots: Omit<Slot, 'id' | 'listingId'>[], address: string, key?: string) =>
  post<{ listing: Listing; slots: Slot[]; held?: boolean }>('/listings', { listing, slots, address }, idem(key))
/** Whether one of my listings waits for a staff check (an edit can put it there).
 *  ponytail: reads my first 100 listings; a per-listing field when owners have more. */
export const listingHeld = async (id: string) =>
  (await get<Page<ListingView>>(`/me/listings${qs({ limit: 100 })}`)).items.some((v) => v.listing.id === id && v.held)
export const updateListing = (id: string, listing: ListingDraft, address: string) =>
  put<Listing>(`/listings/${id}`, { listing, address })
export const addSlots = (id: string, slots: Omit<Slot, 'id' | 'listingId'>[]) => post<Slot[]>(`/listings/${id}/slots`, slots)
export const removeSlot = (id: string, slotId: string) => del<void>(`/listings/${id}/slots/${slotId}`)
export const pauseListing = (id: string) => post<Listing>(`/listings/${id}/pause`)
export const resumeListing = (id: string) => post<Listing>(`/listings/${id}/resume`)
export const removeListing = (id: string) => del<void>(`/listings/${id}`)

export const startPayouts = () => post<{ url: string }>('/payments/connect/onboarding')

/** One photograph in, its URL out, to go in `Listing.photos`. `onProgress`
 *  gets 0–1 as it goes up (U-25): fetch cannot report that, XHR can. */
export async function uploadPhoto(
  image: Blob,
  filename = 'photo.jpg',
  onProgress?: (share: number) => void,
  /** `evidence`: a hand-over photo, stored privately (P-27). The answer is an
   *  `evidence:<name>` reference, not a picture: preview from the local file. */
  purpose: 'listing' | 'evidence' = 'listing',
): Promise<string> {
  const form = new FormData()
  form.append('file', image, filename)
  const path = purpose === 'evidence' ? '/uploads?purpose=evidence' : '/uploads'
  if (!onProgress) return (await call<{ url: string }>('POST', path, form)).url
  const attempt = async () => {
    const token = await accessToken()
    return new Promise<Response>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API}${path}`)
      xhr.setRequestHeader('Accept', 'application/json')
      xhr.setRequestHeader('X-App-Version', APP_VERSION)
      xhr.setRequestHeader('Accept-Language', lang())
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
      xhr.onload = () => {
        const headers = new Headers()
        for (const h of ['x-request-id', 'retry-after']) {
          const v = xhr.getResponseHeader(h)
          if (v) headers.set(h, v)
        }
        resolve(new Response(xhr.status === 204 ? null : xhr.responseText, { status: xhr.status, headers }))
      }
      xhr.onerror = () => reject(new Error('network'))
      xhr.send(form)
    })
  }
  let res: Response
  try {
    res = await attempt()
    if (res.status === 401 && (await refresh())) res = await attempt()
  } catch {
    throw new ApiError(t('Cannot reach Cappy. Check your connection and try again.'), 0, 'offline')
  }
  return (await read<{ url: string }>(res)).url
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
    // Idempotent, so a blip (a 503 while a service restarts) is retried; a
    // real failure still reaches the caller, which says so and rolls back.
    retry: transient,
    retryDelay: backoff,
    onSettled: () => qc.invalidateQueries({ queryKey: ['saved'] }),
  })
}

// --- messages, evidence, reports, blocks ------------------------------------------------------

export type Message = {
  id: string
  senderId: string
  body: string
  at: string
  mine: boolean
  /** The server saw an ask to pay outside Cappy (U-12); shown, never blocked. */
  flagged?: boolean
}
/** What the server puts where contact details were, before a booking is accepted. */
export const HIDDEN_CONTACT = '[shared once the booking is accepted]'

/** The conversation on a booking, oldest first, polled while it is on screen. */
export const useMessages = (bookingId: string) =>
  useQuery({
    queryKey: ['messages', bookingId],
    // ponytail: the newest 100 only; page with nextCursor when conversations get longer.
    queryFn: () => get<Page<Message>>(`/bookings/${bookingId}/messages${qs({ limit: 100 })}`),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
export const sendMessage = (bookingId: string, body: string, key?: string) =>
  post<Message>(`/bookings/${bookingId}/messages`, { body }, idem(key))

export type EvidenceStage = 'check_in' | 'check_out'
export type Evidence = { id: string; by: string; stage: EvidenceStage; photos: string[]; note?: string; at: string }
/** Hand-over photos come back as signed links that last 15 minutes (P-27):
 *  the list is read again well before they lapse, and on a 403 (EvidencePanel). */
export const useEvidence = (bookingId: string) =>
  useQuery({
    queryKey: ['evidence', bookingId],
    queryFn: () => get<Evidence[]>(`/bookings/${bookingId}/evidence`),
    staleTime: 5 * 60_000,
    refetchInterval: 10 * 60_000,
  })
export const addEvidence = (bookingId: string, stage: EvidenceStage, photos: string[], note?: string, key?: string) =>
  post<Evidence>(`/bookings/${bookingId}/evidence`, { stage, photos, note: note || undefined }, idem(key))

export type ReportTarget = 'listing' | 'owner' | 'message' | 'review'
export const REPORT_REASONS = [
  ['illegal', 'Illegal content or activity'],
  ['fraud', 'Fraud or a scam'],
  ['unsafe', 'Unsafe'],
  ['counterfeit', 'Counterfeit or stolen'],
  ['spam', 'Spam'],
  ['offensive', 'Offensive or abusive'],
  ['privacy', 'Shares someone’s private information'],
  ['other', 'Something else'],
] as const
export type ReportReason = (typeof REPORT_REASONS)[number][0]
export type Report = {
  id: string
  targetType: ReportTarget
  targetId: string
  /** Reports from people, or notices the system raises for staff (S-17, S-18). */
  reason: ReportReason | SystemReason
  details: string
  status: 'open' | 'actioned' | 'dismissed'
  createdAt: string
  decision?: string
  statement?: string
  statementOfReasons?: StatementOfReasons
}
export type SystemReason = 'reliability' | 'linked_to_suspended'
/** DSA Art. 17: what the affected person is told after a take-down or suspension. */
export type StatementOfReasons = {
  restriction: string
  facts: string
  automated: boolean
  ground: 'law' | 'terms'
  clause: string
  redress: string
}
/** How a decision rests: the rule or law, and whether a machine made it. */
export type Grounds = { ground: 'law' | 'terms'; clause?: string; automated: boolean }
export const sendReport = (
  r: { targetType: ReportTarget; targetId: string; reason: ReportReason; details: string; email?: string; goodFaith: true },
  key?: string,
) => post<Report>('/reports', r, idem(key))

export const useBlocks = () => {
  const session = useSession()
  return useQuery({ queryKey: ['blocks', session?.sub], queryFn: () => get<string[]>('/me/blocks'), enabled: Boolean(session) })
}
export const blockPerson = (sub: string) => put<void>(`/me/blocks/${encodeURIComponent(sub)}`)
export const unblockPerson = (sub: string) => del<void>(`/me/blocks/${encodeURIComponent(sub)}`)

// --- staff (the server checks the admin group; this only shapes the UI) ------------------------

export type AuditEntry = {
  id: string
  actorId: string
  action: string
  targetType: string
  targetId: string
  reportId?: string
  statement: string
  at: string
}
export const getAdminReports = (status: Report['status'], cursor?: string) =>
  get<Page<Report>>(`/admin/reports${qs({ status, cursor })}`)
export type HeldListing = { id: string; ownerId: string; title: string; category: string; ratePerHour: number; heldAt: string }
/** New owners' expensive listings waiting for a look, oldest first (FL-5). */
export const getHeldListings = () => get<HeldListing[]>('/admin/listings/held')
export const approveListing = (id: string) => post<void>(`/admin/listings/${id}/approve`)
export type Decision = 'dismiss' | 'take_down' | 'suspend' | 'remove_content'
export const decideReport = (id: string, action: Decision, statement: string, g: Grounds) =>
  post<Report>(`/admin/reports/${id}/decide`, { action, statement, ...g })
export const takeDownListing = (id: string, statement: string, g: Grounds) =>
  post<void>(`/admin/listings/${id}/take-down`, { statement, ...g })
export const suspendOwner = (id: string, statement: string, g: Grounds) => post<void>(`/admin/owners/${id}/suspend`, { statement, ...g })
export const reinstateOwner = (id: string, statement: string) => post<void>(`/admin/owners/${id}/reinstate`, { statement })
export const resolveDispute = (id: string, outcome: 'pay_owner' | 'refund_buyer') =>
  post<Booking>(`/admin/bookings/${id}/resolve`, { outcome, by: 'console' })
export const useAudit = () => useQuery({ queryKey: ['audit'], queryFn: () => get<AuditEntry[]>(`/admin/audit${qs({ limit: 100 })}`) })


// --- notification centre (U-22), sign-out everywhere (U-35) -----------------------------------

export type Notice = { id: string; kind: string; title: string; body: string; link?: string; at: string; read: boolean }
export type NoticePage = { items: Notice[]; next?: string; unread: number }
const EMPTY_NOTICES: NoticePage = { items: [], unread: 0 }
/** Tolerates a backend without the centre yet (404): an empty bell, not an error. */
const getNotices = (cursor?: string) =>
  get<NoticePage>(`/notifications${qs({ cursor })}`).catch((e: unknown) => {
    if (e instanceof ApiError && e.status === 404) return EMPTY_NOTICES
    throw e
  })
export const useNotices = () => {
  const session = useSession()
  return useQuery({
    queryKey: ['notices', session?.sub, lang()],
    // ponytail: first page only; "older" with `next` when someone has more than a page.
    queryFn: () => getNotices(),
    enabled: Boolean(session),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}
export type NoticeChannel = { push: boolean; email: boolean }
export type NoticeCategory = 'bookings' | 'messages' | 'payouts' | 'marketing'
export type NoticeSettings = { categories: Record<NoticeCategory, NoticeChannel> }
/** Per-category push/email choices (V3-21); null when the backend has none yet (404). */
export const useNoticeSettings = () => {
  const session = useSession()
  return useQuery({
    queryKey: ['noticeSettings', session?.sub],
    queryFn: () =>
      get<NoticeSettings>('/notifications/settings').catch((e: unknown) => {
        if (e instanceof ApiError && e.status === 404) return null
        throw e
      }),
    enabled: Boolean(session),
  })
}
export const saveNoticeSettings = (s: NoticeSettings) => put<NoticeSettings>('/notifications/settings', s)
export const markNoticesRead = (ids?: string[]) => post<void>('/notifications/read', ids ? { ids } : {})
export const signOutEverywhere = () => post<void>('/me/sign-out-everywhere')
