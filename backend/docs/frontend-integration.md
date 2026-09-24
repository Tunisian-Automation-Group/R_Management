# Wiring the app to the backend

One frontend, two ways of reaching people: the website, and the same build
installed on a phone as a PWA (Share → Add to Home Screen). Both are the same
code talking to the same API, so everything here applies to both. The
differences are only about *where the app is served from*, which is the last
section.

The app is wired. This page records how, so the next change on either side
knows what the other expects.

The app's README promised that "swapping in a backend later touches one file
and zero call sites": `src/data/repo.ts`. That held for reads. For writes,
the reducer's events map one-to-one onto backend calls, so the second change
was `store.tsx` forwarding each event after applying it optimistically, then
re-reading what the server holds so its answer is the one that sticks.

Nothing in `src/domain/` changed. The server runs the same rules; the client
keeps running them too, for instant previews. `seed.ts` is no longer in the
bundle: it feeds `npm run check` and the backend's seed export, nothing else.

## 1. Reads: `repo.ts`

On load the store fetches, in parallel, `GET /me` (who the app speaks for and
where their searches start), `/world` (owners, listings, slots, districts,
reviews), `/bookings` and `/saved`. If any of that fails the shell shows the
error with a retry; nothing is cached in the browser.

The JSON the gateway returns *is* the app's `World`, `Booking[]` and
`string[]`: camelCase, integer cents, ISO strings, optional fields left out
rather than `null` (so `listing.toleranceMm === undefined` keeps meaning what
it means), `requesterId` present only on inbound requests.

`ME` is the account the `X-Cappy-User` header names: `o1` unless
`VITE_CAPPY_USER` says otherwise, which is how a second browser answers a
request from the other side. `GROUPS`, `CATEGORIES` and `REVIEW_TAGS` stay in
`src/domain/` (they are code, not data); `GET /groups`, `/categories` and
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

How the store does it (`forward()` in `store.tsx`):

- **Optimistic, then the server's word.** The reducer applies the event at
  once, the call goes out, and when it lands the store re-reads the parts it
  touched: bookings after a booking event, the world after a listing event,
  both after a rating (the owner's record and the new review come back with
  the world), the shortlist after a heart. Writes queue one behind another,
  so a slow reply can never overwrite a later change. A refused or failed
  call shows the server's message as a toast and resyncs everything.
- **`BOOKING_REQUESTED` sends the choice, not the match.** The app builds a
  `Match` locally with `matchForOffer` for the preview and navigates to the
  booking straight away, so it sends its own `id` along with the requirement
  and the selected offer. The server prices the window itself; its quote
  replaces the preview on the next read.
- **The simulated host reply is server-side.** While any request to another
  owner is pending the store polls `GET /bookings` every three seconds, and it
  re-reads on focus. Requests to `o1` stay pending until answered in Earn.
- **Rating writes the review on the server too.** `useLookups().reviewsFor`
  shows the person's own review the instant they rate, read off the booking as
  `rv_<bookingId>`; the catalog writes the same review under the same id on
  `booking.rated`, and the lookup drops that copy so it is never shown twice.
  Reviews other accounts wrote carry `authorId`.
- **The seeded inbox request comes from the server.** The booking service puts
  `bk_seed_1` (o17 wants two hours of the saw, `l9`) in the Earn inbox on a
  cold start, so `seedBookings()` in `repo.ts` is gone.

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

**Development.** `npm run dev` proxies `/api` to `VITE_API_PROXY` (default
`http://localhost:8000`), so the dev server on 5173 and a phone on the Vite
LAN URL are same-origin with the API too. `npm run preview` does the same.

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

# frontend, against the running backend (proxied, no env needed)
cd cappy/cappy && npm install && npm run dev
```

To answer your own request from the host's side, run a second dev server as
that owner: `VITE_CAPPY_USER=o5 npm run dev -- --port 5174`.
