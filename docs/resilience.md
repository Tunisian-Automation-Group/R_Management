# What can go wrong, and what happens then

A catalogue of the bad days this system will have, component by component:
what happens today, and what we do about it. Each gap has a task in
[`TASKS.md`](TASKS.md) (`T-nn`). The external research behind the choices is
in [`research/`](research/).

Status: ✅ handled · 🟡 partly · ❌ open (has a task)

## Edge and gateway

| # | Scenario | Today | Status |
|---|---|---|---|
| F1 | **Traffic spike** (press, TV, a viral post): 10× in minutes | ECS scales out on CPU and requests in 1–3 min; Aurora scales ACUs in seconds. Until new tasks are up, every request queues and latency explodes for everyone. | ❌ T-01 load shedding at the gateway (bounded concurrency, fast 503 + `Retry-After`) |
| F2 | **Scrapers and bots** hammer search | WAF per-IP rate limits; bots rotating IPs get through. | 🟡 T-02 WAF Bot Control and per-user limits |
| F3 | **One slow service** (matching) ties up every gateway connection, so bookings and profiles slow down too | One shared connection pool per upstream, 15 s timeout. | ❌ T-03 per-upstream bulkheads and tighter per-route timeouts |
| F4 | **Retry storms**: a blip, then every client retries at once | The web retries with backoff (TanStack Query); nothing tells clients when to come back. | 🟡 T-01 (`Retry-After`), T-04 client honours it |

## Identity

| # | Scenario | Today | Status |
|---|---|---|---|
| F5 | **Cognito outage** | Tokens are verified locally from cached keys, so signed-in people keep working. **But a task that starts during the outage cannot fetch the keys, so it rejects everyone.** Scaling out during an outage makes it worse. | ❌ T-05 last-known JWKS as a fallback |
| F6 | Account takeover (credential stuffing) | Cognito lockout; optional MFA; WAF. | 🟡 T-06 Cognito threat protection in prod |

## Catalog and search

| # | Scenario | Today | Status |
|---|---|---|---|
| F7 | **A hot listing** (shared widely): thousands of reads a second on one row | Served by the reader, uncached. | ❌ T-07 short edge cache for anonymous listing and search reads |
| F8 | **Two-letter searches** (`q=ab`): trigram indexes need three characters, so this is a full scan at a million listings | Allowed (`min_length=2`). | ❌ T-08 three characters minimum, or full-text for short terms |
| F9 | **Upload abuse**: a free account fills S3 | Size, pixel and concurrency limits per upload; no quota; orphaned photos never deleted. | ❌ T-09 per-user daily quota, orphan sweep |
| F10 | **EU-wide candidate search** (`maxKm=2000`) at a million listings: the bounding box matches most rows and then sorts them all | Capped at 300 results, but the sort before the cap is over everything. | ❌ T-10 nearest-first index (KNN on a GiST point index) and a tighter radius |

## Matching

| # | Scenario | Today | Status |
|---|---|---|---|
| F11 | **Booking service slow or down**: every search waits for busy windows, then fails | 5 s timeout, then an error. | ❌ T-11 degrade: answer without the busy filter (booking still refuses a taken window) |

## Booking

| # | Scenario | Today | Status |
|---|---|---|---|
| F12 | Everyone wants the same window | The exclusion constraint lets exactly one win; the rest get 409. | ✅ |
| F13 | Payments slow while a booking is made | 503, booking kept; a retry with the same key gets the same intent. | ✅ |
| F14 | Sweeps fall behind after an outage | Batches of 100 until done, SKIP LOCKED across replicas. | ✅ |
| F15 | Clock skew between tasks | Fargate uses Amazon Time Sync; deadlines are minutes, not milliseconds. | ✅ |
| F20 | **Card testing**: a bot account creates bookings to try stolen cards | WAF limits POSTs per IP. | ❌ T-20 cap open unpaid bookings per person; Stripe Radar rules |

## Payments

| # | Scenario | Today | Status |
|---|---|---|---|
| F16 | **Stripe down for an hour** | New bookings get 503. Captures, refunds and payouts retry 5 times × 120 s, **then land in the DLQ after 10 minutes**, needing a manual redrive. | ❌ T-16 exponential backoff per message (up to hours) before the DLQ |
| F17 | Duplicate or out-of-order webhooks | Deduplicated by event id, rows locked, state read back from Stripe. | ✅ |
| F18 | Card authorisation expires | Capture is at accept, at most 24 h later; authorisations last 7 days. | ✅ |
| F19 | **Chargeback** (`charge.dispute.created`) | Ignored. | ❌ T-19 record it, hold the payout, tell ops |
| F21 | Owner's account restricted before payout | The transfer fails, the event retries, then the DLQ. | 🟡 T-16, plus runbook |

## Notifications

| # | Scenario | Today | Status |
|---|---|---|---|
| F22 | **Bounces and complaints** pile up; SES suspends sending (also Cognito's codes, so nobody can sign up) | Not handled. | ❌ T-22 account-level suppression list, bounce/complaint alarms |

## Data

| # | Scenario | Today | Status |
|---|---|---|---|
| F23 | Aurora failover (~30 s) | Connections re-established (pre-ping); in-flight requests fail once; idempotency keys make retries safe. | ✅ |
| F24 | **Connection exhaustion** as tasks multiply | 15 per task; fine to ~50 tasks per service at 64 ACU. | ❌ T-24 RDS Proxy before it matters |
| F25 | A bad migration or an operator mistake deletes data | Point-in-time restore (14 days prod), deletion protection. Never rehearsed. | 🟡 T-25 restore drill in the runbook |
| F26 | **Region outage** (eu-central-1) | Down until the region returns. RPO minutes (backups), RTO hours. | 🟡 T-26 decision recorded; Aurora Global Database when revenue justifies |

## Events

| # | Scenario | Today | Status |
|---|---|---|---|
| F27 | Consumer lag | Scales on backlog; queue-age alarm. | ✅ |
| F28 | Poison message / poison outbox row | DLQ after retries; relay sets a row aside after 20 attempts. | ✅ |

## Mobile

| # | Scenario | Today | Status |
|---|---|---|---|
| F29 | **Old app versions** after an API change (people don't update) | Nothing stops a broken old client. | ❌ T-29 minimum supported version and a forced-update screen |
| F30 | Flaky mobile network | Reads retry; booking creation is idempotent. | ✅ |
| F31 | No push notifications: owners miss requests (24 h to answer) | Email only. | ❌ T-31 push via SNS → APNs/FCM |

## Operations

| # | Scenario | Today | Status |
|---|---|---|---|
| F33 | "Why is this slow?" with no traces | JSON logs with request ids; OpenTelemetry wired but off. | ❌ T-33 traces to X-Ray through an ADOT sidecar |
| F34 | Broken for users while every alarm is green | No outside-in checks. | ❌ T-34 CloudWatch Synthetics canary (browse, search, sign-in page) |
| F35 | No agreed targets | Alarms only. | ❌ T-35 SLOs and error budgets written down |
| F36 | A bad release | Circuit breaker rolls back; deploy fails loudly. | ✅ (canary deploys: T-36, later) |
