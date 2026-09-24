// The only module that knows where data lives: the Cappy backend, over HTTP.
//
// Reads return the app's own types verbatim, because the server serialises the
// same shapes (camelCase, integer cents, ISO strings, optional fields left out
// rather than null). Writes are one call per reducer event; the store forwards
// each event here after applying it optimistically, then re-reads what the
// server says so its answer (the quote, the status a demo host gave) is the
// one that sticks.
//
// Nothing is persisted in the browser any more. The service worker caches the
// app shell, not the data, so a stale copy of the world cannot linger.
import type { Booking, Listing, Outcome, Slot, World } from '../domain/types.ts'

/**
 * Same origin by default: the gateway serves the app at / and the API at /api,
 * and the Vite dev server proxies /api to the backend (see vite.config.ts), so
 * neither the website nor a phone on the LAN needs CORS. Set VITE_API_URL when
 * the app is hosted apart from the API, or wrapped in a native shell.
 */
const API: string = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'

/**
 * Who the app speaks for. Until real accounts exist the backend defaults to
 * the seeded owner `o1`, and this header lets a second browser act as someone
 * else (VITE_CAPPY_USER=o5 npm run dev) to answer a request from the other side.
 */
export const ME: string = (import.meta.env.VITE_CAPPY_USER as string | undefined) || 'o1'

/** Who the client is speaking for, and where their searches start. */
export type Me = { id: string; homeDistrict: string }

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
  ) {
    super(message)
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers: {
        Accept: 'application/json',
        'X-Cappy-User': ME,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError('Cannot reach Cappy. Check your connection and try again.', 0, 'offline')
  }
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
const post = <T>(path: string, body?: unknown) => call<T>('POST', path, body)
const put = <T>(path: string, body?: unknown) => call<T>('PUT', path, body)
const del = <T>(path: string) => call<T>('DELETE', path)

// --- reads --------------------------------------------------------------------

export const getMe = (): Promise<Me> => get('/me')
export const getWorld = (): Promise<World> => get('/world')
export const getBookings = (): Promise<Booking[]> => get('/bookings')
export const getSaved = (): Promise<string[]> => get('/saved')

// --- writes: one per reducer event ----------------------------------------------

/**
 * Sends the choice, not the match. The app built the match locally for the
 * preview; the server prices the same window itself and stores its own answer.
 * The client's id is kept so the screen that navigated to it still finds it.
 */
export const requestBooking = (b: Booking): Promise<Booking> =>
  post('/bookings', {
    id: b.id,
    requirement: b.requirement,
    listingId: b.match.listingId,
    slotId: b.match.slotId,
    start: b.match.start,
    end: b.match.end,
  })

export const acceptBooking = (id: string): Promise<Booking> => post(`/bookings/${id}/accept`)
export const declineBooking = (id: string, reason: string): Promise<Booking> =>
  post(`/bookings/${id}/decline`, { reason })
export const startBooking = (id: string): Promise<Booking> => post(`/bookings/${id}/start`)
export const completeBooking = (id: string): Promise<Booking> => post(`/bookings/${id}/complete`)
export const cancelBooking = (id: string): Promise<Booking> => post(`/bookings/${id}/cancel`)
export const rateBooking = (id: string, outcome: Outcome): Promise<Booking> =>
  post(`/bookings/${id}/rate`, outcome)

export const addListing = (listing: Listing, slots: Slot[]): Promise<{ listing: Listing; slots: Slot[] }> =>
  post('/listings', { listing, slots })
export const pauseListing = (id: string): Promise<Listing> => post(`/listings/${id}/pause`)
export const resumeListing = (id: string): Promise<Listing> => post(`/listings/${id}/resume`)
export const removeListing = (id: string): Promise<void> => del(`/listings/${id}`)

/**
 * One photograph in, its URL out, to go in `Listing.photos`. Multipart, so
 * the JSON helper above does not apply. The URL is same-origin (`/media/…`)
 * unless the API is hosted apart, in which case it is absolute.
 */
export async function uploadPhoto(image: Blob, filename = 'photo.jpg'): Promise<string> {
  const form = new FormData()
  form.append('file', image, filename)
  let res: Response
  try {
    res = await fetch(`${API}/uploads`, { method: 'POST', headers: { 'X-Cappy-User': ME }, body: form })
  } catch {
    throw new ApiError('Cannot reach Cappy. Check your connection and try again.', 0, 'offline')
  }
  const data = (await res.json().catch(() => undefined)) as
    | { url?: string; error?: { code?: string; message?: string } }
    | undefined
  if (!res.ok || !data?.url) {
    throw new ApiError(data?.error?.message ?? `upload failed (${res.status})`, res.status, data?.error?.code ?? 'error')
  }
  return data.url
}

export const saveListing = (id: string): Promise<string[]> => put(`/saved/${id}`)
export const unsaveListing = (id: string): Promise<string[]> => del(`/saved/${id}`)

/** Demo: the server forgets every booking and heart and reseeds the world. */
export async function reset(): Promise<void> {
  await post('/admin/reset')
  try {
    // Older builds kept a copy of the world in the browser; clear it too so it
    // can never shadow what the server now says.
    for (const old of ['cappy.delta.v1', 'cappy.v1', 'cappy.v2', 'cappy.v3-eu']) localStorage.removeItem(old)
  } catch {
    // Nothing stored, nothing to clear.
  }
}
