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
import { t } from '../i18n.ts'
import { shareFile } from '../native.ts'

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
    throw new ApiError(t('Cannot reach Cappy. Check your connection and try again.'), 0, 'offline')
  }
  return res
}

async function call<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await send(method, path, body, headers)
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

export type AppConfig = { minVersion: string; latestVersion?: string }
export const useAppConfig = () =>
  useQuery({
    queryKey: ['appConfig'],
    queryFn: () => get<AppConfig>('/app-config'),
    staleTime: 10 * 60_000,
    retry: false, // an older backend without it must not block the app
  })

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
export const rateRenter = (id: string, quality: number) => post<Booking>(`/bookings/${id}/rate-renter`, { quality })

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
}
export const useInvoices = () => {
  const session = useSession()
  return useQuery({ queryKey: ['invoices', session?.sub], queryFn: () => get<Invoice[]>('/payments/invoices'), enabled: Boolean(session) })
}
/** The printable invoice needs the token, so it is fetched and opened as a blob. */
export async function openInvoice(number: string): Promise<void> {
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
export const startIdentity = () => post<Identity>('/payments/identity/session')
export const getIdentity = () => get<Identity>('/payments/identity')

/** A listing as the owner writes it: ids and the owner come from the server. */
export type ListingDraft = Listing extends infer L ? (L extends Listing ? Omit<L, 'id' | 'ownerId'> : never) : never

/** Creates carry an Idempotency-Key made once per form (U-6): a double tap or a
 *  retried request after a timeout is the same listing, not two. */
const idem = (key?: string) => (key ? { 'Idempotency-Key': key } : undefined)

export const addListing = (listing: ListingDraft, slots: Omit<Slot, 'id' | 'listingId'>[], address: string, key?: string) =>
  post<{ listing: Listing; slots: Slot[] }>('/listings', { listing, slots, address }, idem(key))
export const updateListing = (id: string, listing: ListingDraft, address: string) =>
  put<Listing>(`/listings/${id}`, { listing, address })
export const addSlots = (id: string, slots: Omit<Slot, 'id' | 'listingId'>[]) => post<Slot[]>(`/listings/${id}/slots`, slots)
export const removeSlot = (id: string, slotId: string) => del<void>(`/listings/${id}/slots/${slotId}`)
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
    // Idempotent, so a blip (a 503 while a service restarts) is retried; a
    // real failure still reaches the caller, which says so and rolls back.
    retry: transient,
    retryDelay: backoff,
    onSettled: () => qc.invalidateQueries({ queryKey: ['saved'] }),
  })
}

// --- messages, evidence, reports, blocks ------------------------------------------------------

export type Message = { id: string; senderId: string; body: string; at: string; mine: boolean }
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
export const useEvidence = (bookingId: string) =>
  useQuery({ queryKey: ['evidence', bookingId], queryFn: () => get<Evidence[]>(`/bookings/${bookingId}/evidence`) })
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
  reason: ReportReason
  details: string
  status: 'open' | 'actioned' | 'dismissed'
  createdAt: string
  decision?: string
  statement?: string
}
export const sendReport = (r: { targetType: ReportTarget; targetId: string; reason: ReportReason; details: string; email?: string }) =>
  post<Report>('/reports', r)

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
export const decideReport = (id: string, action: 'dismiss' | 'take_down' | 'suspend', statement: string) =>
  post<Report>(`/admin/reports/${id}/decide`, { action, statement })
export const takeDownListing = (id: string, statement: string) => post<void>(`/admin/listings/${id}/take-down`, { statement })
export const suspendOwner = (id: string, statement: string) => post<void>(`/admin/owners/${id}/suspend`, { statement })
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
    queryKey: ['notices', session?.sub],
    // ponytail: first page only; "older" with `next` when someone has more than a page.
    queryFn: () => getNotices(),
    enabled: Boolean(session),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}
export const markNoticesRead = (ids?: string[]) => post<void>('/notifications/read', ids ? { ids } : {})
export const signOutEverywhere = () => post<void>('/me/sign-out-everywhere')
