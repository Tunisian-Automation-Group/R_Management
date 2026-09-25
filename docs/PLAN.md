# Plan to production

Living document. The goal is fixed in [`GOAL.md`](GOAL.md); this is how we get
there. Steps are added, removed and reordered as the work teaches us; when a
step changes, the change log at the bottom says why.

Branch: `prod-readiness`. Commits as tunisian-automation. Not pushed.

Status: `[x]` done (with the commit that did it) · `[~]` in progress ·
`[ ]` not started · `[-]` dropped (with the reason).

## Phase 0 — Understand and decide
- [x] Read every service, the frontend's data layer, compose and docs
- [x] Baseline: 111 backend tests pass, lint clean
- [x] Write the review with severities → `docs/review/2026-09-principal-review.md` (ae26b32)
- [x] Record decisions as ADRs 0001–0010 → `docs/adr/` (ae26b32)
- [x] Move the frontend to `web/`; remove confidential decks from the tree (ae26b32)

## Phase 1 — Shared foundations (`backend/libs/cappy_common`)
- [ ] Settings with `APP_ENV`; production refuses to boot with demo or unsafe settings
- [ ] JWT verification against a JWKS (Cognito), `Principal`, FastAPI dependencies; no identity header
- [ ] Internal-call authentication (shared service token) for `/internal/*`
- [ ] Structured JSON logs, request-id propagation, optional OpenTelemetry
- [ ] Liveness `/healthz` and readiness `/readyz` (checks the database)
- [ ] Unhandled-exception handler that never leaks internals
- [ ] Sortable, collision-safe ids (ULID-style)
- [ ] Cursor pagination helper
- [ ] Transactional outbox + relay (`SKIP LOCKED`); SNS publisher; SQS consumer with
      idempotency table; in-memory implementation for tests
- [ ] Database: pool settings, statement timeout, `create_all` only outside prod
- [ ] Test helpers: a local JWT issuer and JWKS

## Phase 2 — Catalog
- [ ] Remove destructive seed-on-start and `/admin/reset`; demo seeding becomes a CLI (ADR 0010)
- [ ] Remove the public outcomes endpoint; outcomes only via `booking.rated`
- [ ] `GET /me` + idempotent `PUT /me` profile provisioning from the JWT
- [ ] Server-minted listing and slot ids
- [ ] Indexed candidate query `POST /internal/candidates` (ADR 0001)
- [ ] Paginated listing, owner and review reads; listing detail with owner
- [ ] Free-text search endpoint
- [ ] Photos: Pillow re-encode, EXIF stripped, S3 storage; only our own media URLs
- [ ] Input length limits on every text field
- [ ] Atomic, idempotent rating fold (`processed_events`)
- [ ] Alembic migrations; `timestamptz` for slot windows

## Phase 3 — Matching
- [ ] Replace the world cache with per-request candidates (catalog) + busy intervals (booking)
- [ ] Offers exclude busy intervals
- [ ] Responses carry the listing and owner a card needs (no client-side world)

## Phase 4 — Booking
- [ ] `timestamptz` window columns + exclusion constraint (ADR 0004); SQLite overlap check
- [ ] Outbox for every event; remove all wipe/reconcile/drop code and demo auto-accept
- [ ] Request expiry sweep with `SKIP LOCKED`
- [ ] `POST /internal/busy`
- [ ] Payment states (`awaiting_payment` → `requested`) wired to payment events
- [ ] Idempotency-Key on create; paginated list; server-minted ids
- [ ] Alembic migrations

## Phase 5 — Payments (new service, ADR 0005)
- [ ] Provider interface; Stripe implementation; fake implementation
- [ ] Connect onboarding (account link, status)
- [ ] Authorise on request, capture on accept, cancel on decline/cancel/expiry, transfer on complete, refund
- [ ] Webhook endpoint: signature verification, idempotent on event id
- [ ] Tests against the fake and against stripe-mock

## Phase 6 — Notifications (new service, ADR 0006)
- [ ] SQS consumer for booking and payment events; SES sender; templates
- [ ] Idempotent on event id; tests

## Phase 7 — Identity and the edge
- [ ] Retire the accounts service
- [ ] Gateway: verify JWT, route, strip hop headers, body-size limit, per-user rate limit,
      security headers, never route `/internal`
- [ ] Update the routing table for new endpoints; routing tests

## Phase 8 — Local stack
- [ ] Root `compose.yaml`: Postgres, LocalStack (Cognito, S3, SNS, SQS, SES), stripe-mock, services
- [ ] Bootstrap script creating the pool, client, topic, queues, bucket (same names as Terraform)
- [ ] Migrations as a one-off `migrate` service
- [ ] `make up`, `make test`, `make seed-demo`, `make e2e`; `.env.example` documents the LocalStack token
- [ ] End-to-end smoke test across the running stack

## Phase 9 — Frontend
- [ ] Cognito auth client: sign up, confirm, sign in, refresh, reset, sign out
- [ ] Data layer on TanStack Query; stop loading `/world`
- [ ] Every screen reads server queries (browse, search, listing, bookings, earn, saved)
- [ ] Profile onboarding (`PUT /me`)
- [ ] Stripe Payment Element for booking; Connect onboarding for owners
- [ ] Photo upload against the new endpoint
- [ ] Type-check, build, and the domain check still pass

## Phase 10 — Infrastructure and delivery
- [ ] Terraform modules: network, Aurora, ECS + Service Connect + ALB, CloudFront + WAF + S3,
      Cognito, SNS/SQS/DLQ, SES, Secrets, ECR, observability; `staging` and `prod` roots
- [ ] `terraform validate` clean; plan against LocalStack where supported
- [ ] GitHub Actions CI: lint, type-check, unit tests, Postgres integration tests, image builds, terraform validate
- [ ] GitHub Actions CD: OIDC, push to ECR, run migrations, deploy ECS, publish web

## Phase 11 — Prove it
- [ ] Full stack up locally; e2e passes: sign up → verify → list with photo → search → book → pay →
      accept → complete → rate → review visible → notification sent
- [ ] Concurrency test: two simultaneous bookings of one window → exactly one succeeds
- [ ] Load sanity: candidate query and search stay flat as listings grow (10× seed)
- [ ] Docs: root README, runbook, API reference refreshed
- [ ] Final review against `GOAL.md`; every definition-of-done row has evidence

## Definition of done

| Goal criterion | Evidence | Status |
|---|---|---|
| Safe | security test suite; no `/admin`, no identity header, prod settings guard test | [ ] |
| Correct | exclusion-constraint test on Postgres; outbox/idempotency tests; no delete-on-start code | [ ] |
| Scales | no `/world`; candidate query plan uses indexes; pagination on every list | [ ] |
| Complete | e2e script passes the full journey | [ ] |
| Operable | migrations; `/readyz`; JSON logs with request id; alarms in Terraform | [ ] |
| Deployable | `terraform validate` clean; CI/CD workflows | [ ] |
| Testable locally | `make up && make e2e`; `make test` with no Docker | [ ] |
| Documented | README, runbook, ADRs | [ ] |

## Change log

- 2026-09-25 — Plan created. LocalStack Pro token available, so Cognito is emulated
  locally rather than through a third-party mock (ADR 0009).
