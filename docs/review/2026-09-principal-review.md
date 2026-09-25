# Principal engineering review: Cappy, September 2026

Scope: everything in this repository at `8a70850` — the five Python services
under `backend/`, the React PWA under `cappy/cappy/`, the compose stack and
the docs. Goal: launch on AWS for millions of users.

**Verdict.** The code is careful and well tested (111 tests, lint clean,
unusually honest docs). It is built as a *demo*, and several demo behaviours
are actively dangerous in production. None of them can be fixed by
configuration alone. The blockers are: two unauthenticated endpoints that
destroy or corrupt data, startup code that deletes production data, an
identity model that trusts a plain header, double-booking, and an architecture
in which every request (server) and every page load (client) touches the whole
database.

Severity: **P0** exploitable or loses data today · **P1** blocks launch ·
**P2** needed at scale · **P3** hygiene.

## P0 — exploitable or loses data

| # | Finding | Where |
|---|---------|-------|
| 1 | `POST /api/admin/reset` is routed by the gateway with no authentication. One anonymous request wipes all three databases and every session. | `gateway/main.py` `reset()` |
| 2 | Anyone can rewrite any owner's rating. The gateway forwards everything under `/owners/`, and `POST /owners/{id}/outcomes` in the catalog takes no identity. Trust and ranking are the product. | `gateway/routing.py`, `catalog/routes.py` `record_outcome` |
| 3 | The catalog **deletes and rebuilds its database on startup** whenever the shipped `seed.json` differs from the one it loaded (`seed_on_start` defaults to true). The first deploy after anyone edits the seed deletes every real listing, review and heart. | `catalog/seed.py` `seed_if_stale`, `catalog/main.py` |
| 4 | Booking **wipes its table** on `catalog.changed{what:reset}`, on a world-version mismatch at startup, and deletes any row that fails to parse against the current models (so a model change silently deletes history). | `booking/workers.py` `wipe_bookings`, `drop_unreadable`, `reconcile_world` |
| 5 | Services trust `X-Cappy-User` with no verification, and compose publishes every service port (8001–8004) on the host. Anyone who reaches a service directly is whoever they claim to be. `DEMO_USER_ID` defaults to `o1`, so a service with no header acts *as a real owner*. | `cappy_common/app.py`, `cappy_common/settings.py`, `docker-compose.yml` |
| 6 | A real account with a published password (`nadia@cappy.demo` / `cappy-demo`) is seeded by default. | `accounts/settings.py`, `.env.example` |
| 7 | The event bus acknowledges a message **even when its handler raised**, so a failed `booking.rated` is lost forever — contradicting the README. Consumer names are random per process, so a crashed consumer's pending messages are never reclaimed. Streams are unbounded. | `cappy_common/events.py` `RedisEventBus._loop` |
| 8 | The repository is **public** and contains `data/Capacity_Exchange_*.pptx`, slides marked "Confidential · Strategy working draft". | `cappy/cappy/data/` |

## P1 — blocks launch

**Correctness**

- **Double booking.** Offers are computed from idle windows without
  subtracting existing bookings, and nothing prevents two overlapping bookings
  on one listing. Two buyers can buy the same machine-hours.
- **Dual writes.** Every service writes its row and publishes the event inside
  the transaction *before* commit. A rollback after publish announces a booking
  that never existed; a crash between commit and publish loses the event. Needs
  a transactional outbox.
- **Sign-up is a distributed transaction with no compensation.** Accounts
  creates the catalog owner first, then its own row; any failure after the
  first call leaves an orphan owner.
- **Rating counters race.** `rating_sum`/`jobs_done` are read-modify-write in
  the app. `with_for_update` helps on Postgres, but nothing de-duplicates a
  replayed event except a review-id check that does not exist for deleted
  listings.
- **Client-chosen ids** for listings, slots and bookings (`bk_…` pattern only).
  Ids leak creation time, and `new_id` has 16 random bits per millisecond —
  collisions are a matter of load.

**Security**

- Hand-rolled auth with no email verification, password reset, MFA, lockout or
  rate limiting; login is measurably faster for unknown emails (enumeration),
  and unlimited scrypt makes login a CPU-exhaustion vector.
- Sessions checked by an HTTP call per request (cached 60 s per gateway
  instance, so sign-out does not propagate across instances).
- Listings accept photo URLs from **any** host over plain `http` (tracking
  pixels, mixed content, hot-linking). Uploads keep EXIF — a phone photo of
  kit at home carries the owner's GPS coordinates.
- No length limits on user text (review notes, titles, instructions) at the
  API boundary; no request-size limit at the gateway, which buffers whole
  bodies in memory.
- CORS default allows every private-LAN origin (a development convenience
  shipped as the default).
- No security headers (CSP, HSTS, frame-ancestors).

**Operability**

- Schema is `create_all()` at startup. No migrations, so no safe way to change
  a column once real data exists.
- `/healthz` is liveness only; nothing checks the database, so a load balancer
  keeps routing to an instance whose DB is down.
- Plain-text logs, no request id propagation between services, no tracing, no
  metrics, no alarms.
- The auto-accept sweep has no row locking (`SKIP LOCKED`), so two replicas
  both "accept"; the docs ask operators to disable it on all but one replica
  by hand.
- Timestamps stored as `String(30)`, which works for sorting ISO strings but
  cannot back a range constraint or an interval index.
- No infrastructure as code, no CI, no deployment path.

**Product gaps a real launch needs**

- No payments (the docs say so): nothing charges the buyer, holds funds, pays
  the owner out, or refunds.
- No notifications: an owner never learns a request arrived unless the app is
  open and polling.
- Requests never expire; an unanswered request holds nothing and blocks
  nothing, forever.
- Photos on a Docker volume; never deleted.

## P2 — needed at scale

- **The whole world, everywhere.** `GET /world` returns every owner, listing,
  slot and review. The app downloads it on every load and runs matching in the
  browser; the matching service pulls it every 5 s per instance and scans it
  linearly per request. At a million listings that is gigabytes per page load
  and a full-table scan per search.
- **Cache invalidation does not fan out.** Matching invalidates its world cache
  on `catalog.changed`, delivered through a consumer *group*, which hands each
  message to exactly one member. With N matching instances, N−1 never hear
  about the change.
- No pagination anywhere (`/listings`, `/owners`, `/reviews`, `/bookings`).
- A custom Python reverse proxy buffers every request and response; no
  streaming, no connection limits.
- Seed and demo concerns (`seed_inbox`, `demo_auto_accept`, fingerprints,
  `/admin/reset`) are woven through production code paths rather than living in
  a dev-only seeding tool.

## P3 — hygiene

- The frontend lives at `cappy/cappy/`; `.env.example` still carries an
  unrelated `JEV_API_KEY`.
- The repository root README is one line.
- `scrypt` N=2¹⁴ is below current OWASP guidance (2¹⁷) — moot once auth moves
  to Cognito.

## What is good, and is kept

- The domain port (`matching/domain/`) is pure, deterministic and tested
  against the frontend's own assertions. Keep it exactly; feed it smaller
  inputs.
- The booking state machine as data (`booking/state.py`).
- Integer-cent money and JS-compatible rounding.
- Content-hashed immutable media names.
- The one-error-shape convention and `exclude_none` responses.

## Decisions

Recorded as ADRs in `docs/adr/`. Summary:

1. Keep the service split, fix the data coupling: search becomes an indexed
   candidate query; nothing ever loads the whole world.
2. Identity from Amazon Cognito (email verification, reset, MFA, lockout);
   every service verifies the JWT itself. The accounts service is retired.
3. Events through a transactional outbox, published to SNS and consumed from
   one SQS queue per service with a dead-letter queue.
4. Double booking prevented by a Postgres exclusion constraint, the only place
   that can guarantee it under concurrency.
5. Payments through Stripe Connect: authorise on request, capture on accept,
   pay the owner out on completion, refund on cancellation.
6. Notifications by email through Amazon SES.
7. Photos re-encoded (EXIF stripped) and stored in S3 behind CloudFront.
8. AWS: CloudFront + WAF → ALB → ECS Fargate; Aurora PostgreSQL Serverless v2;
   Terraform; GitHub Actions with OIDC.
9. Local parity through LocalStack (Cognito, S3, SNS, SQS, SES) and stripe-mock:
   one `make up`.
