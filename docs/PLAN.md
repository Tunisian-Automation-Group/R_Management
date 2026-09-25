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

## Phase 1 — Shared foundations (`backend/libs/cappy_common`) — f4d318b
- [x] Settings with `APP_ENV`; production refuses to boot with demo or unsafe settings
- [x] JWT verification against a JWKS (Cognito), `Principal`, FastAPI dependencies; no identity header
- [x] Internal-call authentication (shared service token) for `/internal/*`
- [x] Structured JSON logs, request-id propagation, optional OpenTelemetry
- [x] Liveness `/healthz` and readiness `/readyz` (checks the database)
- [x] Unhandled-exception handler that never leaks internals
- [x] Sortable, collision-safe ids (ULID-style)
- [x] Cursor pagination helper
- [x] Transactional outbox + relay (`SKIP LOCKED`); SNS publisher; SQS consumer with
      idempotency table; in-memory implementation for tests
- [x] Database: pool settings, statement timeout, `create_all` only outside prod
- [x] Test helpers: a local JWT issuer and JWKS

## Phase 2 — Catalog — f4d318b
- [x] Remove destructive seed-on-start and `/admin/reset`; demo seeding becomes a CLI (ADR 0010)
- [x] Remove the public outcomes endpoint; outcomes only via `booking.rated`
- [x] `GET /me` + idempotent `PUT /me` profile provisioning from the JWT
- [x] Server-minted listing and slot ids
- [x] Indexed candidate query `POST /internal/candidates` (ADR 0001)
- [x] Paginated listing, owner and review reads; listing detail with owner
- [x] Free-text search endpoint
- [x] Photos: Pillow re-encode, EXIF stripped, S3 storage; only our own media URLs
- [x] Input length limits on every text field
- [x] Atomic, idempotent rating fold (`processed_events`)
- [x] Alembic migrations; `timestamptz` for slot windows

## Phase 3 — Matching — f4d318b
- [x] Replace the world cache with per-request candidates (catalog) + busy intervals (booking)
- [x] Offers exclude busy intervals
- [x] Responses carry the listing and owner a card needs (no client-side world)

## Phase 4 — Booking — f4d318b
- [x] `timestamptz` window columns + exclusion constraint (ADR 0004); SQLite overlap check
- [x] Outbox for every event; remove all wipe/reconcile/drop code and demo auto-accept
- [x] Request expiry sweep with `SKIP LOCKED`
- [x] `POST /internal/busy`
- [x] Payment states (`awaiting_payment` → `requested`) wired to payment events
- [x] Idempotency-Key on create; paginated list; server-minted ids
- [x] Alembic migrations

## Phase 5 — Payments (new service, ADR 0005) — 10be73e
- [x] Provider interface; Stripe implementation; fake implementation
- [x] Connect onboarding (account link, status); owners who cannot be paid are not bookable (041dded)
- [x] Authorise on request, capture on accept, cancel on decline/cancel/expiry, transfer on complete, refund
- [x] Webhook endpoint: signature verification, idempotent on event id
- [x] Tests against the fake and against stripe-mock

## Phase 6 — Notifications (new service, ADR 0006) — 8261aa1
- [x] SQS consumer for booking and payment events; SES sender; plain-text emails
- [x] Idempotent on event id; verified addresses only, looked up in Cognito (no copy kept); tests

## Phase 7 — Identity and the edge — f4d318b
- [x] Retire the accounts service
- [x] Gateway: route by allow-list, pass the token through (services verify it), header
      allow-list, body-size limit, security headers, never route `/internal`
- [-] Per-user rate limit in the gateway: needs shared state across tasks; WAF rate rules
      per IP at the edge instead, per-user when metrics show abuse
- [x] Update the routing table for new endpoints; routing tests

## Phase 8 — Local stack — a7df6fb
- [x] One non-root Dockerfile for all services; `python -m cappy_common.migrations <service>` (f4d318b)
- [x] Root `compose.yaml`: Postgres, LocalStack (S3, SNS, SQS, SES), cognito-local, services
- [x] Bootstrap script creating the pool, client, topic, queues, bucket (same names as Terraform)
- [x] Services migrate their own database on start locally; a one-off task in AWS
- [x] `make up`, `make test`, `make test-pg`, `make test-stripe`, `make seed-demo`, `make e2e`, `make codes`
- [x] End-to-end journey across the running stack, reproducible from `make clean`

## Phase 9 — Frontend — a868b20
- [x] Cognito auth client: sign up, confirm, sign in, refresh, reset, sign out
- [x] Data layer on TanStack Query; no `/world`, no client-side matching
- [x] Every screen reads server queries (browse, search, listing, bookings, earn, saved)
- [x] Profile onboarding (`PUT /me`)
- [x] Stripe Payment Element for booking; Connect onboarding for owners
- [x] Photo upload against the new endpoint
- [x] Type-check and build pass
- [ ] Exercise the Stripe card step in a browser with real test keys (only the fake provider was run)

## Phase 10 — Infrastructure and delivery — a868b20
- [x] Terraform: network, Aurora (database + role per service), ECS + Service Connect + ALB,
      CloudFront + WAF + CSP + S3, Cognito, SNS/SQS/DLQ, SES (DKIM/SPF/DMARC), Secrets, ECR,
      alarms; `staging` and `prod` roots; `bootstrap` for state and GitHub OIDC
- [x] `terraform validate` clean on every root; the event fabric applied to LocalStack and its
      routing proven (`make infra-local`)
- [x] GitHub Actions CI: lint, unit, Postgres, Stripe contract, web build, images, terraform, e2e
- [x] GitHub Actions CD: OIDC, ECR by sha, migrations before roll-out, ECS roll with rollback,
      web to S3 + invalidation, public smoke test
- [ ] First real `terraform apply` into an AWS account (needs the account, domain and Stripe keys)

## Phase 11 — Prove it
- [x] Full stack up locally; e2e passes: sign up → confirm → list with photo → search → book →
      pay → accept → complete → pay out → rate → review visible → emails sent
- [x] Concurrency test: twenty simultaneous bookings of one window → exactly one succeeds (f4d318b)
- [x] Load sanity (Postgres, 100k listings, all in one city = worst case): search 1–4 ms;
      candidates SQL 11 ms (36 ms end to end for the capped 300), from 16 ms at 10k
- [x] Docs: root README, runbook, API reference generated from code (`make openapi`)
- [x] Final review against `GOAL.md`

## Definition of done

| Goal criterion | Evidence | Status |
|---|---|---|
| Safe | token verification tests (forged, expired, wrong issuer/client, alg none); no `/admin`; identity header ignored (tests + e2e); `/internal` unreachable (gateway tests + e2e + deploy smoke); prod settings guard tests; CSP/HSTS; least-privilege IAM; secrets only in Secrets Manager | [x] |
| Correct | exclusion constraint proven with the pre-check disabled; outbox commit-only and idempotent dispatch tests; money follows the booking with idempotency keys; no delete-on-start code | [x] |
| Scales | no `/world`; bounded candidate query and trigram search measured at 100k; pagination on every list; stateless services with autoscaling; Aurora Serverless v2 | [x] |
| Complete | `make e2e` passes the full journey | [x] |
| Operable | migrations with drift tests; `/readyz`; JSON logs with request id; alarms + runbook | [x] |
| Deployable | `terraform validate` clean; CI/CD workflows; one image recipe | [x] (first apply pending an account) |
| Testable locally | `make up && make e2e`; `make test` with no Docker | [x] |
| Documented | README, runbook, ADRs, generated API reference | [x] |

## Change log

- 2026-09-25 — Plan created. LocalStack Pro token available, so Cognito is emulated
  locally rather than through a third-party mock (ADR 0009).
- 2026-09-25 — LocalStack licence has no Cognito (nor ECS/RDS/ELB/CloudFront/WAF); Cognito is
  emulated with cognito-local, the rest of AWS is covered by Terraform validate/plan (ADR 0009 updated).
- 2026-09-25 — Found while building foundations: FastAPI runs dependency teardown *after* the
  response, so the original per-request commit could fail after the client was told it
  succeeded. All routes now use `Tx` (`scope="function"`). Added to the review.
- 2026-09-25 — Found by a flaky test: pagination cursors rounded timestamps to milliseconds
  while rows keep microseconds, so pages could skip or repeat rows. Cursors now carry full precision.
- 2026-09-25 — `booking.requested` is not emitted: `booking.status_changed` (to `requested`)
  carries everything notifications and payments need. One event, one contract.
- 2026-09-25 — The gateway no longer authenticates: every service verifies the token, so there is
  no trusted hop to get wrong. The `/api/health` fan-out and the index page were removed (they
  advertised internal topology); the ALB checks each service's `/readyz`.
- 2026-09-25 — LocalStack's SQS `path` URLs are rejected by the Terraform provider; the classic
  `<host>/<account>/<queue>` form (`SQS_ENDPOINT_STRATEGY=off`) works for boto3 and Terraform alike.
- 2026-09-25 — This LocalStack licence has SES v1 but not v2: notifications use SES v1 SendEmail,
  identical in AWS. cognito-local does not mark email verified on confirmation (Cognito does);
  the e2e sets it explicitly with a comment.
- 2026-09-25 — Added `payment.payouts_ready` and `payable_owners` after the frontend work showed
  buyers could pick listings checkout would refuse.
- 2026-09-25 — Migrate creates a database and role per service; services never use the master user.
