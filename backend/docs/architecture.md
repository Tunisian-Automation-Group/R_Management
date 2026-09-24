# Architecture

## Services and what they own

| Service  | Owns                                                    | Talks to                           | Store    |
|----------|---------------------------------------------------------|------------------------------------|----------|
| gateway  | routing, CORS, the caller's identity header, the built web app | everything, over HTTP        | none     |
| catalog  | districts, owners, listings, idle windows, reviews, hearts | nobody (publishes events)       | Postgres |
| matching | feasibility, availability, pricing, ranking, browse, review summaries, the category and tag vocabulary | catalog (`GET /world`), cached | none |
| booking  | booking lifecycle, demo hosts                           | matching (`POST /match-for-offer`), catalog (`GET /world/version`, at startup) | Postgres |

Two rules keep the boundaries honest:

1. **A service never reads another service's tables.** Catalog and booking
   have separate databases in the same Postgres container. If booking needs
   an owner's name it asks catalog, or (as today) the frontend does.
2. **Domain logic lives in one place.** Every rule from the app's
   `src/domain/` is in `services/matching/matching/domain/`. Booking does not
   price anything; catalog does not decide what is feasible. The one table
   both catalog and matching need, the nine categories and their booking
   modes, sits in `cappy_common.categories` and matching re-exports it.

## One API for the website and the phone

The frontend is one codebase that runs as a website and as an installed PWA,
and the backend does not distinguish them: same endpoints, same JSON, same
`X-Cappy-User` header for identity (no cookies, so a native shell works the
same way). Two consequences shape the API:

- **Nothing the app needs is only in the seed.** `GET /me`, `/groups`,
  `/categories` and `/review-tags` exist so a client without `seed.ts` and
  without the domain package can still draw the browse screen and the rating
  sheet.
- **Optional fields are omitted, not `null`.** The app runs its own domain
  rules on the world it loads (`listing.toleranceMm === undefined`), so
  every router is `cappy_common.app.ApiRouter`, which sets
  `response_model_exclude_none` on every route.

The gateway can also serve the built app from `/` (`STATIC_DIR`), so the
website, the installed app and the API share one origin and the browser never
needs CORS. That is the recommended deployment; separate origins work too.

## Request flow: booking a saw

```
PWA ──POST /api/bookings──▶ gateway ──▶ booking
                                          │  POST /match-for-offer
                                          ▼
                                       matching ──GET /world (cached)──▶ catalog
                                          │
                                          ◀── Match {quote, reasons, distanceKm}
                                          │
                                        store row (status=requested)
                                        publish booking.requested
                                          │
PWA ◀────────── 201 Booking ◀─────────────┘
```

The client sends the requirement and the window it chose. The quote in the
stored booking is the matching service's answer, not the client's.

## Event flow: a rating changes the ranking, and becomes a review

```
booking ──booking.rated {bookingId, ownerId, listingId, requesterId, outcome, at}──▶ catalog
                                                │ one transaction:
                                                │   apply_outcome(): ratingSum, jobsDone, onTimeJobs
                                                │   insert review rv_<bookingId> on the listing
                                                ▼
                                        catalog.changed ──▶ matching drops its world cache
```

The handler is idempotent on the review id, so a redelivered event (Redis
Streams is at-least-once) neither double-counts the outcome nor writes the
review twice. A rating for a listing that has since been removed still moves
the owner's record; there is just no page left for the words.

Events go over Redis Streams (`cappy:events:<topic>`) with one consumer group
per service, so a service that is down when an event is published receives
it on restart. In tests and single-process runs `EVENT_BUS_URL=memory://`
swaps in an in-process bus with the same interface.

Topics, defined once in `cappy_common.events`:

| Topic                    | Producer | Consumers          | Payload                                   |
|--------------------------|----------|--------------------|-------------------------------------------|
| `booking.requested`      | booking  | (none yet)         | bookingId, requesterId, ownerId, listingId |
| `booking.status_changed` | booking  | (none yet)         | bookingId, from, to, by                   |
| `booking.rated`          | booking  | catalog            | bookingId, ownerId, listingId, requesterId, outcome, at, ratedAt |
| `catalog.changed`        | catalog  | matching           | what, id                                  |

The two unconsumed topics are where notifications (push, e-mail) and an
analytics sink plug in without touching the producers.

## The seed is versioned

The demo world is exported from the frontend's `seed.ts`, and the frontend
changes it. The catalog stores a fingerprint of the seed it loaded
(`GET /world/version`); on startup, a database built from a different edition
is rebuilt from the shipped one and `catalog.changed {what: "reset"}` is
published, the same event the demo reset publishes. Booking treats a reset as
"every booking now points at nothing": it wipes its table and reseeds the
inbox. At its own startup booking also compares the version it last saw with
the catalog's and does the same on a mismatch, and drops any row that no
longer parses against the current models, so a database that outlives a seed
change heals itself rather than failing every request. Matching just drops
its cache.

The frontend does the equivalent on the client: `repo.ts` stores a delta over
the seed, never the seed itself, for the same reason.

## Time

Every instant is an ISO-8601 string exactly as `Date.prototype.toISOString()`
writes it (UTC, milliseconds, `Z`). The domain functions take `now` as an
argument and never read the clock; routes default it to the current time and
accept `?now=` for reproducible answers. Seeded idle windows and seeded
reviews are anchored to local midnight in `SEED_TIMEZONE`, the same way the
app anchors them to the browser's midnight, so the demo never shows stale
dates.

## Identity

`X-Cappy-User` names the caller; the gateway forwards it and every service
defaults it to `DEMO_USER_ID` (`o1`, the account the app's Earn side speaks
for). Ownership is checked on every write: only the owner pauses or removes a
listing, only the owner accepts or declines, only the requester starts,
completes and rates; hearts are per caller. When real accounts arrive, the
gateway verifies a token and sets the header; the services do not change.

## What would change at scale

- **Photo uploads.** Listings carry photo URLs. An upload endpoint (object
  storage, signed PUT) is the missing piece; the catalog already refuses
  anything that is not an `http(s)` URL so image bytes never land in Postgres.
- **Slot consumption.** An accepted booking should split the idle window it
  sits in. Today neither the app nor the server does that; it belongs in
  catalog, triggered by `booking.status_changed` (to `accepted`).
- **World fan-out.** Matching pulls the entire world on a five-second TTL.
  With thousands of listings this becomes a per-district query against a
  catalog read model, and `catalog.changed` carries enough to update it
  incrementally.
- **A ranker.** `find_matches` weights are hand-tuned. The rating loop is
  accumulating the outcome data a learned ranker would need; `assess_feasibility`
  is the named seam for a probabilistic judgment layer, exactly as in the app.
