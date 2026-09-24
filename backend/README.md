# Cappy backend

The server side of [Cappy](../cappy/cappy) ("rent the hour, not the thing"):
four Python microservices behind one gateway, sharing a small common library.
One API serves the website and the same app installed on a phone.

```
gateway   :8000   one origin for the app and the API; checks sessions, routes /api/* by path
catalog   :8001   districts, owners, listings, idle windows, reviews, hearts, photos (Postgres)
matching  :8002   feasibility, availability, pricing, ranking, vocabulary (stateless)
booking   :8003   request → accept → active → completed → rated (Postgres)
accounts  :8004   sign up, sign in, sessions (Postgres)
redis             events between services (Redis Streams)
```

The frontend's domain rules (`src/domain/*.ts`) are ported 1:1 into the
matching service, and the frontend's `World` and `Booking` JSON shapes are
served unchanged, so wiring the app up is a one-file change in `data/repo.ts`
plus one call per reducer event. See
[docs/frontend-integration.md](docs/frontend-integration.md).

## Run the whole stack

Needs Docker. Build the app first if you want the gateway to serve it; skip
that and the gateway is API-only.

```bash
(cd ../cappy/cappy && npm install && npm run build)   # optional: dist/ for the gateway to serve
cp .env.example .env
docker compose up --build
# http://localhost:8000          the web app (when built)
# http://localhost:8000/api/…    the API; OpenAPI per service at :8001/docs, :8002/docs, :8003/docs
curl http://localhost:8000/api/health
curl http://localhost:8000/api/world | head -c 400
```

**Docker inside WSL2:** WSL stops the Linux VM, and with it the Docker daemon,
about a minute after the last WSL session closes. Every service carries
`restart: unless-stopped`, so the stack recovers as soon as WSL starts again
(any `wsl` command does that), but while nothing keeps WSL open the gateway is
down. Keep a terminal open in the distro, or run `wsl -d Ubuntu -- sleep
infinity` in the background, when you want the stack up between uses.

The catalog seeds the same demo world the app ships with: 70 owners, 78
listings across nine categories, 250 idle windows and 275 reviews across
Berlin, Amsterdam, Eindhoven, Paris, Lyon, Milan, Brescia and Lisbon. The
booking service puts one request in the Earn inbox (two hours of the saw),
exactly as the app does on a cold start. Browsing needs no account; to book,
list or answer requests, create one in the app or sign in as the seeded
owner: **nadia@cappy.demo / cappy-demo**.

**Upgrading a stack that ran before accounts existed:** Postgres only runs
`docker/postgres-init.sql` on an empty volume, so create the new database
once: `docker compose exec postgres psql -U cappy -d postgres -c "CREATE
DATABASE cappy_accounts"`, then `docker compose up --build`. Or start clean
with `docker compose down -v`.

## Run the tests

Needs [uv](https://docs.astral.sh/uv/). No Docker, no Postgres, no Redis: the
tests use SQLite in memory and an in-process event bus.

```bash
uv sync --all-packages
uv run pytest -q
```

`services/matching/tests/test_matching_domain.py` is the port of the app's own
`npm run check`: the same assertions, run against the same seed. If the two
codebases ever disagree on a cent or a rank, this is where it shows.

## Run one service without Docker

Every service falls back to SQLite and an in-memory bus when the compose
environment is absent, so a single service can be poked at on its own:

```bash
make dev-catalog     # http://localhost:8001/docs
make dev-matching    # needs catalog on :8001
make dev-booking     # needs matching on :8002
make dev-gateway     # STATIC_DIR=../cappy/cappy/dist to serve the app too
```

## Keep the seed in step with the app

The demo world is exported from the frontend, not written twice:

```bash
make seed    # node scripts/export-seed.mjs ../cappy/cappy > libs/cappy_common/cappy_common/fixtures/seed.json
```

Run it whenever `src/data/seed.ts` changes, then `uv run pytest -q`. Needs
Node 22.18+ (it imports the TypeScript directly).

A running stack notices the new seed by itself: the catalog fingerprints the
seed it loaded and rebuilds the world on the next start when the shipped one
differs, and the booking service drops the bookings that pointed at the old
world. No `docker compose down -v` needed; `docker compose up --build` is
enough.

## Layout

```
libs/cappy_common/       models (types.ts port), categories, settings, event bus, HTTP client, DB, app shell
  cappy_common/fixtures/seed.json   the demo world, exported from the frontend (make seed)
services/catalog/        system of record for the world: listings, windows, reviews, hearts
services/matching/       pure domain + thin routes; reads the world from catalog
services/booking/        booking state machine + demo hosts
services/gateway/        reverse proxy with a routing table; serves the built app
scripts/export-seed.mjs  regenerates fixtures/seed.json from ../cappy/cappy/src/data/seed.ts
docs/                    architecture, API, frontend integration
```

## Design notes

- **One API, two clients.** Website and installed app are the same build;
  a native shell would be a third. So identity is a header (no cookies),
  optional fields are omitted rather than `null` (the app runs
  `=== undefined` checks on what it loads), and `GET /me`, `/groups`,
  `/categories`, `/review-tags` exist so a client without the seed can still
  draw every screen.
- **Quotes are never trusted from the client.** `POST /api/bookings` sends the
  requirement and the chosen window; the booking service asks matching to
  price it. The frontend's `matchForOffer` still runs locally for the preview,
  and the server's answer is the one that is stored.
- **Ratings close the loop across services, and become reviews.**
  `POST /bookings/{id}/rate` publishes `booking.rated`; the catalog folds it
  into the owner's record *and* writes it as `Review rv_<bookingId>` on the
  listing, in one transaction, idempotently; then publishes `catalog.changed`
  and matching drops its cached world. Delivery is Redis Streams with a
  consumer group per service, so a restart never loses a rating.
- **Money is integer cents, rounding is JavaScript's.** `cappy_common.jsmath`
  reproduces `Math.round` and `toFixed` so the server agrees with the app to
  the cent.
- **Identity is a session at the gateway, a header inside.** The app sends a
  bearer token; the gateway checks it with the accounts service and sets
  `X-Cappy-User`, the only identity the services trust. Nothing a client
  sends can name someone else, and `/internal/…` never leaves the network.

## What is not real

Same list as the app, plus the server-side equivalents:

- Hosts with no account behind them are simulated: the booking service
  accepts their requests after `DEMO_AUTO_ACCEPT_SECONDS` (default 5.5). Set
  it to `0` to turn that off. Anyone who has signed up answers for themselves.
- Accounts have no email verification, password reset or rate limiting yet.
  The session token sits in the browser's storage, as on any single-page app.
- No money moves. Quotes are computed and stored; nothing is charged.
- Photos an owner uploads live on the `mediadata` Docker volume, not in
  object storage, and are never deleted when a listing is removed. The seed's
  photos are curated stand-ins, as in the app.
- Accepted bookings do not yet carve the booked hours out of the idle window,
  matching the app's current behaviour. That is the next real piece of work.
- `POST /api/admin/reset` wipes both databases (bookings, hearts, the world)
  back to the seed. Do not expose it beyond a demo.
