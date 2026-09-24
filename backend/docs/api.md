# API

Everything below is reachable through the gateway at `/api/...`. Each service
also serves its own OpenAPI at `/docs`. JSON is camelCase and matches the
frontend's `src/domain/types.ts` field for field. Optional fields are
**omitted** when absent, never sent as `null`: the app runs its own domain
rules on what it loads and those rules test `=== undefined`. Errors are always

```json
{ "error": { "code": "not_found", "message": "listing l99 not found" } }
```

with codes `invalid` (422), `forbidden` (403), `not_found` (404),
`conflict` (409), `upstream` (502).

Send `X-Cappy-User: <ownerId>` to act as someone; it defaults to `o1`. The
same header works from the website and from a native shell: identity is a
header, not a cookie, so nothing depends on the browser.

## Vocabulary

What a client needs to draw the browse screen and the rating sheet without
shipping the seed. Served by matching, static.

| Method | Path                  | Query      | Returns                                  |
|--------|-----------------------|------------|------------------------------------------|
| GET    | `/api/groups`         |            | `GroupMeta[]` — make, move, equip        |
| GET    | `/api/categories`     | `?group=`  | `CategoryMeta[]` (nine; `group`, `mode`, `quickHours` / `unitNoun`) |
| GET    | `/api/review-tags`    |            | `string[]` — the six things people say   |
| GET    | `/api/me`             |            | `{ id, homeDistrict, owner? }` for the caller (catalog) |

## Catalog

| Method | Path                             | Body / query                          | Returns             |
|--------|----------------------------------|---------------------------------------|---------------------|
| GET    | `/api/world`                     |                                       | `World` (owners, listings, slots, districts, reviews) |
| GET    | `/api/world/version`             |                                       | `{ version }` — which edition of the seed the world was built from |
| GET    | `/api/districts`                 |                                       | `Record<name, District>` |
| GET    | `/api/owners`                    |                                       | `Owner[]`           |
| GET    | `/api/owners/{id}`               |                                       | `Owner`             |
| POST   | `/api/owners/{id}/outcomes`      | `Outcome`                             | `Owner` (updated)   |
| GET    | `/api/listings`                  | `?ownerId=`                           | `Listing[]`         |
| GET    | `/api/listings/{id}`             |                                       | `Listing`           |
| GET    | `/api/listings/{id}/slots`       |                                       | `Slot[]`            |
| GET    | `/api/listings/{id}/reviews`     |                                       | `Review[]`, newest first |
| GET    | `/api/reviews`                   |                                       | `Review[]`, newest first |
| POST   | `/api/listings`                  | `{ listing: Listing, slots: Slot[] }` | same, 201           |
| POST   | `/api/listings/{id}/pause`       |                                       | `Listing`           |
| POST   | `/api/listings/{id}/resume`      |                                       | `Listing`           |
| DELETE | `/api/listings/{id}`             |                                       | 204                 |
| POST   | `/api/uploads`                   | multipart, one `file`                 | `{ url, contentType, bytes }`, 201 |
| GET    | `/media/{name}`                  |                                       | the photograph, cached forever |
| GET    | `/api/saved`                     |                                       | `string[]` — listing ids the caller hearted, newest first |
| PUT    | `/api/saved/{listingId}`         |                                       | `string[]` (updated) |
| DELETE | `/api/saved/{listingId}`         |                                       | `string[]` (updated) |

`POST /api/listings` accepts the exact object the app's AddListing screen
builds (client-generated ids included) and rejects: an `ownerId` that is not
the caller, an unknown district, a category whose booking mode does not match
the listing's `mode`, a duplicate id, a slot that ends before it starts, a
slot claiming more usable hours than it lasts, and `photos` that are not
`http(s)` URLs (upload the image first, send its address) or more than 12 of
them. A batch listing may leave `materials` and `toleranceMm` out: a truck
does not stock a material, and feasibility treats the absence as "cannot
promise that", not as zero.

Saving is idempotent both ways and per caller. A removed listing drops out of
everyone's shortlist; a demo reset clears it.

**Photos.** `POST /api/uploads` takes one JPEG, PNG or WebP (decided from the
bytes, not the filename) up to `MEDIA_MAX_BYTES` (10 MB) and returns the URL to
put in `Listing.photos`. Files are named by content hash, so the same picture
is one file and every URL is immutable; the gateway serves them at `/media/…`
on the app's origin. The app shrinks pictures to 1600 px JPEG before sending.
Files live on the `mediadata` volume (`MEDIA_DIR`); an object-storage backend
replaces `catalog/media.py` and nothing else.

## Matching

| Method | Path                                    | Body / query                                      | Returns               |
|--------|-----------------------------------------|---------------------------------------------------|-----------------------|
| POST   | `/api/matches`                          | `{ requirement, now?, sort?: best\|price\|soonest\|nearest }` | `Match[]` |
| POST   | `/api/match-for-offer`                  | `{ requirement, listingId, slotId, start, end }`  | `Match`               |
| POST   | `/api/quote`                            | `{ requirement, listingId }`                      | `{ quote, feasibility }` |
| POST   | `/api/feasibility`                      | `{ requirement, listingId }`                      | `Feasibility`         |
| GET    | `/api/listings/{id}/offers`             | `?hours=&from=&until=&limit=`                     | `Offer[]`             |
| GET    | `/api/listings/{id}/reviews/summary`    |                                                   | `{ summary: ReviewSummary, reviews: Review[] }` |
| GET    | `/api/browse/spotlight`                 | `?district=&maxKm=&now=&withinHours=&limit=`      | `Spotlight[]`         |
| GET    | `/api/browse/idle`                      | `?district=&maxKm=&now=&horizonHours=`            | `IdleSummary`         |
| GET    | `/api/browse/cities`                    | `?now=&horizonHours=`                             | `CityStat[]`          |
| GET    | `/api/browse/europe`                    | `?now=&horizonHours=`                             | `IdleSummary`         |
| GET    | `/api/districts/nearest`                | `?lat=&lng=`                                      | `{ district, km }`    |

`now`, `from` and `until` are ISO-8601 and default to the current time (and
a week ahead for `until`). Passing them makes any answer reproducible.

`ReviewSummary` is the app's `summarise()`: `{ count, average, onTimeShare,
topTags: [{ tag, n }] }`, with `average` and `onTimeShare` absent until there
is at least one review, because "new" is not the same as "bad".

## Booking

| Method | Path                              | Body                                             | Returns      |
|--------|-----------------------------------|--------------------------------------------------|--------------|
| GET    | `/api/bookings`                   |                                                  | `Booking[]` for the caller, newest first |
| GET    | `/api/bookings/{id}`              |                                                  | `Booking`    |
| POST   | `/api/bookings`                   | `{ requirement, listingId, slotId, start, end, id? }` | `Booking`, 201 |
| POST   | `/api/bookings/{id}/accept`       |                                                  | `Booking`    |
| POST   | `/api/bookings/{id}/decline`      | `{ reason }`                                     | `Booking`    |
| POST   | `/api/bookings/{id}/start`        |                                                  | `Booking`    |
| POST   | `/api/bookings/{id}/complete`     |                                                  | `Booking`    |
| POST   | `/api/bookings/{id}/cancel`       |                                                  | `Booking`    |
| POST   | `/api/bookings/{id}/rate`         | `Outcome` `{ onTime, quality 1..5, note?, tags? }` | `Booking`  |

Who may do what:

| Action   | From                  | To          | By                 |
|----------|-----------------------|-------------|--------------------|
| accept   | requested             | accepted    | owner              |
| decline  | requested             | declined    | owner              |
| start    | accepted              | active      | requester          |
| complete | active                | completed   | requester          |
| cancel   | requested, accepted   | cancelled   | requester or owner |
| rate     | completed, once       |             | requester          |

`id` on `POST /api/bookings` is optional and client-generated (`bk_` plus 6 to
40 lowercase letters or digits), so the app can navigate to the booking it
just built before the server has answered; a reused id is a 409.

`GET /api/bookings` returns bookings the caller requested *and* bookings
against the caller's listings. `requesterId` is present only on the latter,
which is exactly how the app's Earn inbox tells them apart.

**Rating writes a review.** `tags` must come from `/api/review-tags`
(duplicates are dropped, unknown tags are a 422). The rating is folded into
the owner's record and appears on the listing as a `Review` with id
`rv_<bookingId>`, dated at the end of the booked window, authored by the
requester (`authorId` set), within one event hop. A client that shows its own
rating locally straight away can drop the server copy by that id.

## Gateway

| Method | Path                | Returns                                          |
|--------|---------------------|--------------------------------------------------|
| GET    | `/api/health`       | `{ ok, services: { catalog, matching, booking } }` |
| POST   | `/api/admin/reset`  | 204; wipes bookings and hearts, reseeds the world (demo) |
| GET    | `/`, `/{anything}`  | the built web app, when `STATIC_DIR` points at one (see [frontend-integration](frontend-integration.md)); otherwise a JSON index |
