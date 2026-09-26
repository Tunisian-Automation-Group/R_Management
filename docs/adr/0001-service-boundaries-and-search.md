# 0001. Keep the service split; search is an indexed candidate query

## Context
Matching needs listings, owners, slots and districts to rank anything, and
today gets them by pulling `GET /world` (the entire catalog) every five
seconds per instance, then scanning it per request. The browser does the same
on every page load. Cost grows with the size of the database, not with the
size of the answer.

## Decision
Keep catalog, matching and booking as separate deployables, but change what
crosses the boundary. Catalog exposes `POST /internal/candidates`: given a
category, an origin, a radius and a time window, it returns only the listings
that could possibly answer (indexed on category, active flag and district
coordinates, with an open slot overlapping the window), capped, plus exactly
the owners, slots and districts they reference, as a small `World`. Matching
feeds that to the unchanged domain functions. Booking supplies the intervals
already taken (`POST /internal/busy`), so offers exclude them.

The client stops loading the world. Every screen asks the API for what it
shows, paginated.

## Rejected
- *Merge matching into catalog.* Removes a hop, but couples pricing and ranking
  releases to the system of record, and matching is the CPU-heavy part that
  should scale on its own.
- *A search cluster (OpenSearch) now.* Right at tens of millions of listings or
  for free-text relevance; today Postgres with the right indexes answers the
  candidate query in milliseconds and has one less thing to run. The candidate
  endpoint is the seam where it would plug in.
- *Keep the world cache and fan invalidation out with pub/sub.* Fixes
  staleness, not size.

## Consequences
One extra service call per search (catalog, and booking in parallel). The
domain code is untouched and its tests still hold. Candidate caps mean a
search returns the best of the nearest few hundred, which is what a person
can use anyway.
