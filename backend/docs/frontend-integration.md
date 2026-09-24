# Wiring the app to the backend

One frontend, two ways of reaching people: the website, and the same build
installed on a phone as a PWA (Share → Add to Home Screen). Both are the same
code talking to the same API, so everything here applies to both. The
differences are only about *where the app is served from*, which is the last
section.

The app's README promised that "swapping in a backend later touches one file
and zero call sites": `src/data/repo.ts`. That holds for reads. For writes,
the reducer's events map one-to-one onto backend calls, so the second change
is a small effect in `store.tsx` that forwards each event.

Nothing in `src/domain/` changes. The server runs the same rules; the client
keeps running them too, for instant previews.

## 1. Reads: `repo.ts`

```ts
const API = import.meta.env.VITE_API_URL ?? '/api'      // same origin by default
const headers = { 'Content-Type': 'application/json' }   // add X-Cappy-User to act as someone else

const get = <T>(path: string) => fetch(`${API}${path}`, { headers }).then((r) => r.json() as Promise<T>)

export const getWorld = (): Promise<World> => get('/world')       // includes reviews
export const getBookings = (): Promise<Booking[]> => get('/bookings')
export const getSaved = (): Promise<string[]> => get('/saved')
export const reset = () => fetch(`${API}/admin/reset`, { method: 'POST' }).then(() => undefined)
export const persist = async () => {}   // writes go through the events below
```

The JSON the gateway returns *is* the app's `World`, `Booking[]` and
`string[]`: camelCase, integer cents, ISO strings, optional fields left out
rather than `null` (so `listing.toleranceMm === undefined` keeps meaning what
it means), `requesterId` present only on inbound requests.

`ME` and `HOME_DISTRICT` come from `GET /me` instead of `seed.ts` once the
seed is no longer bundled; `GROUPS`, `CATEGORIES` and `REVIEW_TAGS` stay in
`src/domain/` (they are code, not data) and `GET /groups`, `/categories`,
`/review-tags` serve the same tables for a client that has no domain package.

## 2. Writes: one call per reducer event

| Reducer event        | Backend call                                                    |
|----------------------|-----------------------------------------------------------------|
| `BOOKING_REQUESTED`  | `POST /bookings { requirement, listingId, slotId, start, end }` |
| `BOOKING_ACCEPTED`   | `POST /bookings/{id}/accept`                                    |
| `BOOKING_DECLINED`   | `POST /bookings/{id}/decline { reason }`                        |
| `BOOKING_STARTED`    | `POST /bookings/{id}/start`                                     |
| `BOOKING_COMPLETED`  | `POST /bookings/{id}/complete`                                  |
| `BOOKING_CANCELLED`  | `POST /bookings/{id}/cancel`                                    |
| `BOOKING_RATED`      | `POST /bookings/{id}/rate { onTime, quality, note, tags }`      |
| `LISTING_ADDED`      | `POST /listings { listing, slots }`                             |
| `LISTING_PAUSED`     | `POST /listings/{id}/pause`                                     |
| `LISTING_RESUMED`    | `POST /listings/{id}/resume`                                    |
| `LISTING_REMOVED`    | `DELETE /listings/{id}`                                         |
| `LISTING_SAVED`      | `PUT /saved/{id}`                                               |
| `LISTING_UNSAVED`    | `DELETE /saved/{id}`                                            |
| `DEMO_RESET`         | `POST /admin/reset`                                             |

Details worth knowing:

- **`BOOKING_REQUESTED` sends the choice, not the match.** The app builds a
  `Match` locally with `matchForOffer` for the preview. Send the requirement
  and the selected offer; the response is the server's `Booking`, whose id
  and quote should replace the optimistic one. Reloading `getBookings()`
  after the call is enough.
- **The 5.5-second simulated host reply moves server-side.** Delete the
  `waiting` timer effect in `store.tsx` and poll `GET /bookings` (or refetch
  on focus) while any booking is `requested`. The booking service accepts
  seeded hosts' requests after `DEMO_AUTO_ACCEPT_SECONDS`; requests to `o1`
  stay pending until answered in Earn, exactly as now.
- **Rating writes the review on the server too.** `useLookups().reviewsFor`
  synthesises the person's own reviews from rated bookings as `rv_<bookingId>`
  so they appear the instant they are submitted. The catalog writes the same
  review under the same id on `booking.rated`, so after the next `getWorld()`
  the listing would show it twice. Either drop the synthesis once the backend
  is wired, or keep it for the instant feedback and filter
  `world.reviews` by `!r.id.startsWith('rv_bk_')` for bookings the app already
  has. Server reviews carry `authorId`, which is how to label them "You".
- **The seeded inbox request is the same one.** The booking service puts
  `bk_seed_1` (o17 wants two hours of the saw, `l9`) in the Earn inbox on a
  cold start, so `seedBookings()` in `repo.ts` goes.

## 3. Optional: let the server search

Browse, Listing and the headline numbers all run in the browser today, on the
world they loaded. That stays correct. When the world gets too big to ship,
the same functions are one call away:

| Client function            | Endpoint                                  |
|----------------------------|-------------------------------------------|
| `findMatches(req, world)`  | `POST /matches { requirement, sort }`     |
| `offersFor(slots, h, …)`   | `GET /listings/{id}/offers?hours=…`       |
| `quoteFor(req, listing)`   | `POST /quote { requirement, listingId }`  |
| `summarise(reviewsFor(id))`| `GET /listings/{id}/reviews/summary`      |
| `availableSoon(…)`         | `GET /browse/spotlight?district=…`        |
| `idleNearby(…)`            | `GET /browse/idle?district=…`             |
| `cities(…)` / `idleEurope` | `GET /browse/cities`, `GET /browse/europe`|
| `nearestDistrict(…)`       | `GET /districts/nearest?lat=…&lng=…`      |

## 4. Where the app is served from

**Same origin (recommended).** The gateway serves the built app at `/` and
the API at `/api`, so there is no CORS, the installed PWA and the website are
literally the same URL, and a deep link like `/listing/l9` on the phone
falls back to `index.html` for the app's router. Hashed assets are sent
immutable; `index.html`, the service worker and the manifest are `no-store`,
so an installed app picks up a new build on next launch.

```bash
cd cappy/cappy && npm run build          # -> dist/
cd ../../backend && docker compose up --build
# http://localhost:8000        the app
# http://localhost:8000/api    the API
```

Compose mounts `../cappy/cappy/dist` into the gateway; without a build there
the gateway is API-only and `/` returns a JSON index. Outside compose, set
`STATIC_DIR=/path/to/dist` on the gateway.

**Separate origins.** When the app is on a CDN, or a native shell (Capacitor,
React Native) wraps it, set `VITE_API_URL` to the gateway and list the app's
origin in `CORS_ORIGINS` (`capacitor://localhost` and `http://localhost` for
Capacitor). Identity is a header, so nothing depends on cookies, and a native
shell stores the user id however it likes.

A service worker only registers over HTTPS (or `localhost`), so to install
the PWA on a phone put the gateway behind TLS; a phone on the same Wi-Fi can
still open the app at the LAN address, which `CORS_ORIGIN_REGEX` already
allows in development.

## 5. Dev setup

```bash
# backend
cd backend && cp .env.example .env && docker compose up --build

# frontend, against the running backend
cd cappy/cappy && echo 'VITE_API_URL=http://localhost:8000/api' >> .env.local && npm run dev
```

`CORS_ORIGINS` in `backend/.env` already allows `http://localhost:5173`.
