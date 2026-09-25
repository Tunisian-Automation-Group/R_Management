# What can go wrong, and what happens then

A catalogue of the bad days this system will have, component by component:
what happens today, and what we do about it. Each gap has a task in
[`TASKS.md`](TASKS.md) (`T-nn`). The external research behind the choices is
in [`research/`](research/).

Status: ✅ handled · 🟡 partly · ❌ open (has a task)

## Edge and gateway

| # | Scenario | Today | Status |
|---|---|---|---|
| F1 | **Traffic spike** (press, TV, a viral post): 10× in minutes | Bounded in-flight requests per gateway task, a fifth kept for writes; beyond that a fast 503 with `Retry-After` (T-01). Spike test: L-2. | ✅ |
| F2 | **Scrapers and bots** hammer search | WAF per-IP limits, Bot Control in prod (never on Stripe's webhooks). Per-user limits (Redis) at the first abuse signal. | 🟡 |
| F3 | **One slow service** (matching) ties up every gateway connection, so bookings and profiles slow down too | A bulkhead per upstream service in the gateway: a slow service sheds only its own calls (T-03). | ✅ |
| F4 | **Retry storms**: a blip, then every client retries at once | Every 503/502/504 says `Retry-After`; clients wait at least that long, with jittered backoff (T-04, R-3). | ✅ |

## Identity

| # | Scenario | Today | Status |
|---|---|---|---|
| F5 | **Cognito outage** | Tasks start with the signing keys fetched at deploy, and refresh when Cognito is back (T-05). | ✅ |
| F6 | Account takeover (credential stuffing) | Cognito lockout; optional MFA; WAF. | 🟡 T-06 Cognito threat protection in prod |

## Catalog and search

| # | Scenario | Today | Status |
|---|---|---|---|
| F7 | **A hot listing** (shared widely): thousands of reads a second on one row | Anonymous listing, search, review, owner, offer and spotlight reads are cached at CloudFront for 30 s, `stale-while-revalidate` coalesces refreshes and `stale-if-error` serves 10 min through an origin failure. Everything else is served from the Aurora reader (T-07, R-4). | ✅ |
| F8 | **Two-letter searches** (`q=ab`): trigram indexes need three characters, so this is a full scan at a million listings | Three characters minimum, which the trigram index needs (T-08). | ✅ |
| F9 | **Upload abuse**: a free account fills S3 | 100 photos per person a day; unused uploads swept after a day (T-09). | ✅ |
| F10 | **EU-wide candidate search** (`maxKm=2000`) at a million listings: the bounding box matches most rows and then sorts them all | Districts are walked nearest first (at most 200), each from its own index, stopping at the cap. 100k listings: 17 ms local, 21 ms EU-wide (T-10). | ✅ |

## Matching

| # | Scenario | Today | Status |
|---|---|---|---|
| F11 | **Booking service slow or down**: every search waits for busy windows, then fails | Search answers without busy windows; selling a window still needs booking to confirm (T-11). | ✅ |

## Booking

| # | Scenario | Today | Status |
|---|---|---|---|
| F12 | Everyone wants the same window | The exclusion constraint lets exactly one win. **Found under test:** the losers waited on each other inside the constraint, then deadlocked or timed out (500s). Now bookings of one listing queue behind a per-listing transaction lock and each loser gets a 409. 50 simultaneous buyers × 3 rounds, run 6 times: one winner each, no 5xx. | ✅ |
| F13 | Payments slow while a booking is made | 503, booking kept; a retry with the same key gets the same intent. | ✅ |
| F14 | Sweeps fall behind after an outage | Batches of 100 until done, SKIP LOCKED across replicas. | ✅ |
| F15 | Clock skew between tasks | Fargate uses Amazon Time Sync; deadlines are minutes, not milliseconds. | ✅ |
| F20 | **Card testing**: a bot account creates bookings to try stolen cards | At most three bookings waiting for payment per person; Radar on (T-20). | ✅ |

## Payments

| # | Scenario | Today | Status |
|---|---|---|---|
| F16 | **Stripe down for an hour** | Each failed event waits 30 s doubling to 15 min, jittered, for 12 tries (about 2 h), then the DLQ and its alarm. Reconciliation catches lost webhooks (T-16, R-1). | ✅ |
| F17 | Duplicate or out-of-order webhooks | Deduplicated by event id, rows locked, state read back from Stripe. | ✅ |
| F18 | Card authorisation expires | Capture is at accept, at most 24 h later; authorisations last 7 days. | ✅ |
| F19 | **Chargeback** (`charge.dispute.created`) | Recorded; the payout is held; an alarm fires (T-19). | ✅ |
| F21 | Owner's account restricted before payout | The payout retries with backoff for about 2 h, then the DLQ and its alarm. The payouts kill switch holds everything (R-10). | ✅ |

## Notifications

| # | Scenario | Today | Status |
|---|---|---|---|
| F22 | **Bounces and complaints** pile up; SES suspends sending (also Cognito's codes, so nobody can sign up) | SES account suppression list; bounce and complaint alarms (T-22). | ✅ |

## Data

| # | Scenario | Today | Status |
|---|---|---|---|
| F23 | Aurora failover (~30 s) | Connections re-established (pre-ping); in-flight requests fail once; idempotency keys make retries safe. | ✅ |
| F24 | **Connection exhaustion** as tasks multiply | A Terraform check fails the plan if peak connections could exceed 80% of Aurora's maximum; RDS Proxy at the trigger (T-24). | ✅ |
| F25 | A bad migration or an operator mistake deletes data | Point-in-time restore with a rehearsal procedure in the runbook (T-25). | ✅ |
| F26 | **Region outage** (eu-central-1) | Decided: one region across three AZs; Global Database when commitments need it (T-26). | 🟡 |

## Events

| # | Scenario | Today | Status |
|---|---|---|---|
| F27 | Consumer lag | Scales on backlog; queue-age alarm. | ✅ |
| F28 | Poison message / poison outbox row | DLQ after retries; relay sets a row aside after 20 attempts. | ✅ |

## Mobile

| # | Scenario | Today | Status |
|---|---|---|---|
| F29 | **Old app versions** after an API change (people don't update) | Store builds send `X-App-Version`; below `/api/app-config`'s minimum they show an update screen (T-29). | ✅ |
| F30 | Flaky mobile network | Reads retry; booking creation is idempotent. | ✅ |
| F31 | No push notifications: owners miss requests (24 h to answer) | Push through SNS Mobile Push (APNs, FCM v1) alongside email (T-31). The shells register with the Capacitor plugin. | ✅ |

## Operations

| # | Scenario | Today | Status |
|---|---|---|---|
| F33 | "Why is this slow?" with no traces | OpenTelemetry to X-Ray through an ADOT sidecar; trace context rides inside events (T-33). | ✅ |
| F34 | Broken for users while every alarm is green | A CloudWatch Synthetics canary every 5 minutes, with an alarm (T-34). | ✅ |
| F35 | No agreed targets | `docs/slo.md`; multi-window burn-rate alarms (T-35). | ✅ |
| F36 | A bad release | Circuit breaker, plus rollback when the 5xx or fast-burn alarm fires during a deploy (T-36). | ✅ |
