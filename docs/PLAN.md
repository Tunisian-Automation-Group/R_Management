# Plan to production

Living document. The goal is fixed in [`GOAL.md`](GOAL.md); this is how we get
there. Steps are added, removed and reordered as the work teaches us; when a
step changes, the change log at the bottom says why.

Branch: `prod-readiness`. Commits as tunisian-automation. Not pushed.

Status: `[x]` done (with the commit that did it) · `[~]` in progress ·
`[ ]` not started · `[-]` dropped (with the reason).

## Resume here (end of 2026-09-26)

**How a day runs** (GOAL 15; the user's words: "continue again tomorrow doing
exactly the same thing"). Each round:
1. research agents study the big apps, law and security and add tasks to
   [`TASKS.md`](TASKS.md), with their sources in `docs/research/`;
2. one backend fork and one web fork build in parallel. Each owns its
   files, commits nothing and never stashes. I commit after `make test`
   and every web `check:*` pass, chaining with `&&` so a red suite can't
   commit;
3. an independent verifier checks the web version (desktop) and the app
   version (390 px) in Chrome, signing in only with the demo buttons;
4. a docs-sync agent brings FEATURES, INFRA, FLOWS and DATA up to date
   (CLAUDE.md "Living docs").

Nothing is ever pushed or applied to real AWS (GOAL 12). Markets are all
of Europe, the US and Canada (GOAL 16, ADR 0013).

**Start tomorrow with:**
1. `make up`, then `make e2e`, to prove the stack from clean.
2. **Verification round 4** on both versions, in EN, DE and FR, as buyer,
   host and staff. It covers everything built since round 3:
   - 18+, business identity, no-shows, good faith;
   - private evidence, the ID-check consent, the staff console approving
     held listings and removing content;
   - the public report form, the offline start, `/pay/return`, currency
     formatting and French.
3. **The web follow-ups the last backend round (235eeaa) created.** They're
   in FLOWS.md §23:
   - `conversation_closed`;
   - the `charged` flag in the cancel sheet;
   - the new decline reason, in DE and FR;
   - the "messages are not emailed" copy;
   - the country at payout onboarding;
   - `identityProvider` driving the ID-check UI;
   - booking currency lowercase vs quote currency uppercase.
4. **The next build tasks, in order:**
   - M-2: the market configuration, which the thresholds and ranking marked
     `ponytail` still need;
   - M-5 to M-8: places as geo points instead of Berlin districts;
   - U-17: the Keychain and Keystore;
   - the open technical P items: P-5 CSP in the shells, P-11 TLS inside the
     VPC, P-31 app hardening, P-32 scanning and pinning;
   - the S items: S-12 late return, S-17 bank fingerprints, S-20 duplicate
     photos, S-21 dispute offers, S-23 web vitals, S-27 review prompt,
     S-28 review-collusion signals;
   - T-35c per-journey burn alarms; M-46 names per cell;
   - pruning `revoked_sessions` and `rate_hits`.
5. **A fresh research pass** on what nobody has looked at yet: seller
   onboarding and listing-quality benchmarks, search relevance, support
   tooling, and pricing and fee transparency across markets.

**Waiting on the owner** (business and legal, not code):
- G-B1: insurance. It blocks S-8 and S-9, damage claims and deposits.
- G-B2 to G-B4: counsel on the withdrawal right per category and on the
  policies; the DPAs and DPIA; the BZSt/DAC7 registration.
- M-1: the North America legal entity and Stripe platform. M-11: VAT and
  sales tax on the fee per market, with a tax adviser.
- P-13, P-15, P-17, P-19, P-21, P-29, P-30: the privacy programme per
  jurisdiction (breach procedure, policies, biometric consent, transfers,
  privacy officer and representatives, CPRA process).
- The GitHub environments need `LEGAL`, `AWS_IMAGES_ROLE_ARN` and so on
  before any deploy (runbook step 2). The first real AWS apply is the
  owner's call.
- Rotate the LocalStack and GitHub tokens that were pasted in chat, purge
  the `Capacity_Exchange_*.pptx` decks from git history, and consider
  making the repository private.

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

## Phase 12 — Independent review and fixes
- [x] Three independent reviews (security, reliability, booking/money flow); findings fixed:
      OIDC trust narrowed to the deploy workflow on main (no PR role); upload decoding bounded;
      ids encoded between services; paused listings hidden from matching; gateway holds no
      internal token; booking time rules, disputes and failed captures (ADR 0011); intents made
      without holding a DB connection and safe under racing retries; Stripe calls bounded and
      redrive-safe beyond the 24 h idempotency window; webhook row locks; versioned payout
      readiness; SQS batches handled concurrently with a 120 s visibility; outbox/processed
      pruning; consumers scale on backlog; keep-alive above the ALB idle timeout; deploy fails
      when ECS rolled back; AdminGetUser + adaptive retries for email; web role-aware booking
      screen, resumable payment, pay-state reset
- [-] Per-event source verification: a sender sets its own source, so it proves nothing;
      per-publisher topics if the threat model needs it (runbook, known limits)

## Phase 13 — Store ready, payments for real, verified by someone else (GOAL items 9–11)
- [x] Stripe test mode end to end: CLI forwards webhooks in the stack; e2e confirms with Stripe's
      test card and follows capture and a real transfer to a verified test connected account (72693fb)
- [x] Account deletion and data export (App Store, GDPR) (141924b)
- [x] Native shells decided: Capacitor (ADR 0012); gateway CORS for the shells (141924b)
- [x] Public reads on the Aurora reader (450d397); shared vocabulary cached at the edge (98f0364)
- [ ] Web: delete account + export in Profile; privacy and terms pages; media URLs resolved
      against the API origin; Capacitor projects (ios/android), deep-link files
- [ ] Independent browser verification: rounds until a full pass finds nothing
- [ ] Load test against the local stack: no errors under sustained concurrent use

## Phase 14 — Resilience, research and launch gaps (docs/TASKS.md is the working list)
- [x] Failure catalogue (docs/resilience.md): every scenario handled or decided
- [x] Research: scale practices (docs/research/2026-09-scale-practices.md), launch gaps (docs/research/2026-09-launch-gaps.md)
- [x] Load: 50 concurrent browsers + racing buyers, 0 failures; spike 30→300/s, 0 failures, p99 ≈ 220 ms
- [x] Browser verification rounds 1 and 2 fixed (66 findings); round 3 after the trust features' UI
- [x] Trust and compliance (API): messaging with masking, blocks, reports and moderation (DSA 16/17), check-in/out evidence, identity verification (Stripe Identity), fraud rules, DAC7 tags, German notifications
- [x] Web UI for the trust features (c0f3aac), German UI and Capacitor shells (15811c2)
- [x] Soon-after-launch features: instant book, blind two-way reviews, cancellation policies with partial
      refunds (gated on counsel), duration discounts, fee invoices, analytics pipeline
- [x] Soak: 20 min, flat latency, memory, connections and queues; third review round fixed (3942e35)
- [x] Web for the latest features (b120dd0), verification round 3 (d2baff3, 23 findings, all fixed)
- [ ] First AWS apply; breakpoint and soak tests on staging (L-5) — the owner's call

## Phase 15 — Members only, a welcome, the loop, every market (GOAL 13–16)
- [x] Signed-in only, enforced by the server (0d0d1b5) and the web (f081c9f); a welcome for first-timers
- [x] App UX research (U-1..U-40, 33 done), stores and marketplace (S-1..S-32, 13 done)
- [x] Security review (P-1..P-34): the technical highs and mediums fixed (9d28a0e, ffb2990, 40fbc5f, f303350)
- [x] Data rights: deletion and export complete, with a test that walks every table (235eeaa)
- [x] Living docs: FEATURES, INFRA, FLOWS, DATA (1928895..1216719), kept in sync each round
- [x] Markets: research and ADR 0013 (0472163); currency per listing, the owner's country, French (db417ca, f42a4ef, 235eeaa)
- [ ] Verification round 4 on both versions (tomorrow)
- [ ] Market configuration and places as geo points (M-2, M-5..M-8)

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
- 2026-09-25 — Independent reviews found real defects in the money flow and CI trust; fixed in
  phase 12, decisions in ADR 0011. Catalog migration 0002 was edited in place (never deployed).
- 2026-09-26 — Members only (GOAL 13), the welcome (GOAL 14) and the loop (GOAL 15) built.
  The markets are Europe, the US and Canada (GOAL 16), so ADR 0013 gives two cells, and
  currencies, countries and French came in. The living docs were added at the owner's request.
  One commit (235eeaa) landed with a timing-dependent test red; it was fixed in 7ef9b2c, and
  commits are now chained on a green suite.
