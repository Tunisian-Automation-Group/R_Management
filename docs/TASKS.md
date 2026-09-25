# Tasks

The working list, fed by three sources:
- the failure catalogue ([`resilience.md`](resilience.md), `F-nn`);
- the independent browser verification rounds (`V<round>-<n>`);
- the external research ([`research/`](research/)).

Every task ends with a test, a load run or a verifier pass that proves it.

Status: `[ ]` open · `[~]` in progress · `[x]` done (commit) · `[-]` dropped (why)

## Contracts agreed between web and backend for this batch

- `POST /listings` and `PUT /listings/{id}` accept a top-level `address` (≤ 200 chars) next to
  `listing` and `slots`. It is never in public listing responses. `GET /me/listings` items carry it.
- `GET /bookings/{id}` carries `handover: {address, instructions}` for both parties once the
  booking is accepted, active or completed (not before, and never for cancelled ones).
- `GET /api/app-config` → `{minVersion, latestVersion}`. The shells send `X-App-Version`;
  below `minVersion` the app shows a forced-update screen.
- A `503` carries `Retry-After` (seconds); clients wait at least that long before retrying.

## Verification round 1 — web (V1)

- [x] V1-1 Owners reach their accepted, active and completed bookings: `/bookings` has an "I'm hosting" view (`role=owner`), and Earn links each confirmed booking
- [x] V1-2 Photos display: the Vite proxy forwards `/media`; relative media URLs resolve against the API origin (web and native shells)
- [x] V1-3 Legal pages: Impressum, Privacy Policy and Terms, filled from build config (`VITE_LEGAL_*`), shown as "to be completed" rather than fake brackets when unset; the "prototype" footer removed
- [x] V1-4 Profile: edit name, kind and district; export my data; delete my account (confirm sheet → `DELETE /me` → Cognito `DeleteUser` → signed out); Terms/Privacy links; consent line on sign-up
- [x] V1-5 Forgot password: validate the email format; the right error message for an unknown address (never "email and password do not match")
- [x] V1-6 Remove listing: confirm first; buttons that don't shift under the pointer
- [x] V1-7 Edit a published listing (title, blurb, price, photos, rules, address, windows)
- [x] V1-8 Handover address shown to the buyer once accepted (see contracts); owner enters the address when listing
- [x] V1-9 Remove the "Cash or bank transfer" house-rule chip (it invites off-platform payment)
- [x] V1-10 The map respects category and filters; its legend matches the times
- [x] V1-11 Owner rating and listing reviews are labelled apart ("Nadia · 4.7 from 22 jobs" vs "This listing · 4.8 from 4 reviews"); "new here" only for an owner with no jobs
- [x] V1-13 The week chart draws every sold booking, not only the first
- [x] V1-14 A real 404 page; signed-out deep links keep their target through sign-in
- [x] V1-15 Search, category and filters in the URL (shareable, back button works)
- [x] V1-16 Search results show the price; readable "nothing free" state; Enter submits
- [x] V1-17 The chosen slot survives sign-in in the middle of booking
- [x] V1-18 Bookings and requests sorted by start time
- [x] V1-19 Idle and free-this-week figures subtract sold hours and match the windows
- [x] V1-20 "Earned" counts completed bookings only; "upcoming" shown apart
- [x] V1-21 The owner's view of a booking shows the buyer, not the owner
- [x] V1-22 Declined and cancelled bookings say the hold was released, not "receives €…"
- [x] V1-23 Confirmed state with a success icon
- [x] V1-24 Contrast of the earnings preview (WCAG AA)
- [x] V1-25 Listing form: focus the first error, label every input, `4,00 €` formatting, districts grouped by city, duration chips from the listing's own minimum
- [x] V1-26 "Free now" only when a bookable window (≥ the minimum) is actually left
- [x] V1-27 The chosen city persists; sign-out clears the person's home district
- [x] V1-29 Accessibility: an `<h1>` per screen, a per-route `<title>`, nav before main, a skip link
- [x] V1-30 The confirm sheet shows the chosen start time
- [x] V1-31 The start button says the hand-over opens 30 minutes before the booked time
- [x] V1-32 Hero photo alignment on desktop
- [x] V1-33 The "+" glyph in display titles
- [x] V1-35 The review tag summary matches the tags on the reviews
- [x] T-04 Honour `Retry-After`; forced-update screen from `/api/app-config` (see contracts)

## Verification round 2 (V2)

Contract changes for this round:
- `Booking.canStartFrom` (ISO): when the hand-over can first be marked. The app uses it instead of a constant.
- `reviews.average` is absent (not null) when a listing has no reviews.
- Removing a listing declines its pending requests (reason "The listing was removed"). Accepted bookings stand.
- `GET /owners/{id}` is 404 for a deleted account. Reviews by deleted accounts carry no `authorId`.

Web:
- [x] V2-1 BLOCKER: a listing with no reviews crashes (`reviews.average` undefined)
- [x] V2-3 Typing in a sheet (rating note, dispute) jumps focus to Close (Sheet effect re-runs on each render)
- [x] V2-4 Picking a city centres on its first district (Brandenburg for Berlin): use the district nearest the city's centre; district search in the picker
- [x] V2-5 The start button from `canStartFrom`, not a hard-coded 30 minutes
- [x] V2-6 The listing form saves values nobody chose (materials, rules, hidden spec defaults); category-specific placeholders and prices
- [x] V2-7 The decline sheet's "your listing stays live" is only said when true
- [x] V2-8 Data export that works in the store shells and Safari
- [x] V2-10 Forgot password never reveals whether an account exists
- [x] V2-11 Drop the EU ODR link (the platform closed in July 2025)
- [x] V2-13 Accessibility: no button inside a button; errors tied to fields (`aria-describedby`); navigation as links
- [x] V2-14 "Free now" only for what is bookable now (the 2-hour lead included)
- [x] V2-15 Sort, tabs and "needed within" in the URL, and matching the filter options
- [x] V2-17 Saving an edit needs one click
- [x] V2-18 Confirm "Mark as handed back"; toasts on sign-out and account deletion
- [x] V2-19 "3D printing" capitalisation; one price format; label the owner rating on search rows

Backend:
- [x] V2-2 Double booking: a completed or disputed booking still holds its window (busy windows and the exclusion constraint)
- [x] V2-7b Removing a listing declines its pending requests
- [x] V2-9 Save/unsave 503: not reproducible (four saves and unsaves 204, direct and through the proxy); it coincided with a service restart, when 503 + Retry-After is right. The web must show the failure and retry (web task)
- [x] V2-12 Deleted accounts: owner page 404, no `authorId` on their reviews; reviewers shown as "First L."
- [x] V2-16 A review is dated when it was written, never in the future
- [x] V2-20 The load test cancels the bookings it makes; demo data rebuilt clean
- [-] V2-19b Seed photos that match their listings: demo data only

## Verification round 1 — backend and data (V1)

- [x] V1-8b Handover address: stored on the listing (owner only), returned on the booking once accepted
- [x] V1-12 The e2e uses its own owner and removes what it creates; demo data stays clean
- [ ] V1-28 Refresh token: kept in the native shells' secure storage (Capacitor Preferences/Keychain); on the web it stays in storage under the CSP (accepted risk, ADR 0012)
- [ ] V1-34 Seed photos that match their listings (cosmetic; demo only)
- [-] V1-3 real legal text: needs the company's details from the owner of the business (asked)

## Resilience (F)

- [x] T-01 Load shedding at the gateway: bounded in-flight requests per task, fast `503` + `Retry-After`
- [x] T-03 Per-upstream bulkheads and per-route timeouts in the gateway
- [x] T-05 Last-known-good JWKS so new tasks verify tokens during a Cognito outage
- [x] T-08 Search needs 3+ characters (trigram index), checked with a plan at scale
- [x] T-09 100 photos per person per day; uploads never used on a listing swept after a day (a shared file only when nobody holds it)
- [x] T-10 Nearest-first candidates: districts nearest first (the nearest 200), each answered from its own index, stopping at the cap. At 100k listings: 16.8 ms local (was 36), 21 ms EU-wide (was 47)
- [x] T-11 Matching degrades without busy windows when booking is down
- [x] T-16 Exponential backoff per SQS message before the DLQ (hours, not minutes)
- [x] T-19 Chargebacks: record `charge.dispute.*`, hold the payout, alarm
- [x] T-20 Cap open unpaid bookings per person (card testing)
- [x] T-22 SES suppression list and bounce/complaint alarms
- [-] T-24 RDS Proxy: not yet. Research puts the trigger at roughly 500 tasks or connections above 70% of the maximum; the Terraform `check connection_budget` fails before that happens
- [x] T-25 Backup-restore drill in the runbook
- [x] T-26 Region-outage decision recorded (RPO/RTO)
- [x] T-29 Minimum app version (`/api/app-config`)
- [x] T-31 Push notifications (backend): devices register their APNs/FCM token (`POST/DELETE /api/notifications/devices`); every email is also a push through SNS Mobile Push; dead devices and deleted accounts are forgotten. Store credentials go into SNS platform applications (runbook). App side: with the Capacitor shells
- [x] T-33 Tracing: OpenTelemetry on in AWS through an ADOT sidecar to X-Ray; trace context travels inside events, so one trace spans the request, the outbox, SNS/SQS and the handler
- [x] T-34 Synthetic canary every 5 min (web, categories, search, internal routes private, sign-in required) with an alarm
- [x] T-35 SLOs and error budgets (docs/slo.md)
- [x] T-35b Burn-rate alarms (14.4x over 1 h and 5 min pages; 6x over 6 h and 30 min tickets)
- [~] T-36 Deploys roll back on the 5xx and fast-burn alarms (done); native ECS canary with an alternate target group once there is real AWS to verify it on
- [x] T-02 WAF Bot Control (common) on in prod, scoped away from Stripe webhooks, non-browser user agents counted, not blocked
- [-] T-06 Cognito threat protection: off (Plus tier, about $0.02/MAU = ~$20k/month at 1M users); a Terraform switch turns it on when account-takeover attempts show up
- [x] B-5 WAF rate rules would have blocked Stripe's webhooks at scale (few source IPs): the webhook path is exempt; signatures protect it

## Found while doing these

- [x] B-1 Two people uploading the same picture: only the first could use it (media is now owned per person)
- [x] B-3 Editing a seeded listing failed: photos it already shows were checked as new uploads
- [x] B-4 Racing buyers for one window got 500s (deadlocks and timeouts inside the exclusion constraint): per-listing advisory lock, contention mapped to 409
- [x] B-2 Local bootstrap failed once queue settings changed (it now updates existing queues)

## From the research (R)

- [x] R-0 Card authorisations expire after 7 days: already safe (capture at accept, at most 24 h after the request)
- [x] R-1 Payments reconciliation sweep: intents stuck in an intermediate state converge with Stripe
- [x] R-2 Reject an idempotency key reused with a different request body
- [x] R-3 Full jitter in the relay poll, the sweeps and client retry backoff
- [x] R-4 Public GETs: `s-maxage` plus `stale-while-revalidate` and `stale-if-error` at the edge (with T-07)
- [x] R-5 Connection budget written down and asserted; replica-lag alarm; reader in promotion tier 1
- [x] R-10 Kill switches (settings): stop new bookings, stop payouts, stop new listings, without a deploy
- [x] R-11 Game-day runbook (Aurora failover, stop half the tasks) with AWS FIS
- [ ] R-13 Web deletion page for Google Play (`/account/delete`)

## Launch gaps (G) — from docs/research/2026-09-launch-gaps.md

Engineering, before launch:
- [x] G-1 Admin console (web /admin and API: queue, decide, take down, suspend/reinstate, resolve disputes, audit; staff = Cognito group admin). The web console screens are next. Scope: moderation queue, take down or reinstate a listing, suspend a user with an Art. 17 statement of reasons, refund, pause payouts, resolve disputes; audited, role-gated
- [x] G-2 (API) DSA Art. 16 notice-and-action ("report this" on listings and profiles) with acknowledgement and outcome email; Art. 17 statements of reasons; Art. 11/12 contact points on the legal pages
- [x] G-3 Report (`POST /api/reports`, with G-2) and block users (`/api/me/blocks`): no messages or new bookings between them, either way. Reporting comes with G-2
- [x] G-4 In-app messaging per booking (`/api/bookings/{id}/messages`); phone numbers, emails, links and messenger handles masked until accepted; pushed to the other side (never emailed)
- [x] G-5 (API) Check-in and check-out photos on a booking (`/api/bookings/{id}/evidence`), the parties' own uploads, never swept
- [x] G-6 Checkout compliance: total price including the fee; "zahlungspflichtig buchen"; trader/private owner label; withdrawal information and the withdrawal button; review-verification statement; ranking parameters page
- [~] G-7 German localisation: every email and push in English and German, by the recipient's Cognito `locale` (done); the web UI and legal pages next (the app sets `locale` when the language changes)
- [x] G-8 (API) Renter identity verification with Stripe Identity (document + live selfie) for bookings above 300 € (and configurable categories); only the outcome is stored. Needs a DPIA before launch (G-B3)
- [x] G-9 Fraud rules: 10 booking requests and 20 new listings per person per day; a new owner's listing above 100 €/h waits for a staff check (`/api/admin/listings/held`, approve)
- [~] G-10 DAC7: every category tagged with its activity (`dac7` on /api/categories; counsel confirms). Left for the business: switch on Stripe Connect platform tax reporting in the dashboard (it collects TIN and date of birth in onboarding, and Stripe withholds payouts while they are missing) and register with the BZSt (G-B4)

- [x] G-11 Fee invoices to owners: issued at payout (or when a late cancellation keeps a fee), numbered without gaps per year (proven under 20 concurrent payouts), never duplicated, printable (`/api/payments/invoices`). VAT treated as German 19% included until counsel confirms reverse charge and OSS (G-B2)

Decisions for the business (not code):
- [ ] G-B1 Insurance partner or guarantee for damage (vans first) — owner of the business
- [ ] G-B2 Terms, cancellation policy, VAT treatment of the fee, withdrawal-right scope for storage and workshops — counsel
- [ ] G-B3 DPAs with every processor, records of processing, DPIA for ID checks — the business, with counsel
- [ ] G-B4 BZSt registration for DAC7

Soon after launch (backend done so far: instant book; cancellation policies flexible/moderate/strict with partial refunds and the owner's share of what is kept, and a refund preview (`/api/bookings/{id}/cancellation`), with only flexible enabled until counsel confirms (G-B2); two-way reviews, owners rating renters, with a renter record on profiles; publishing both reviews blind at once is still to do; duration discounts, a day rate from 8 h and a week rate from 40 h, set by the owner, on the hourly base only): helpdesk, analytics warehouse (done: SNS → Firehose → S3 → Athena, docs/analytics.md), feature flags and A/B tests, e-invoices (2027), KYBC, DSA Section 3 when no longer small.

## Load

- [x] L-1 `make load`: 50 concurrent browsers for 60 s plus contested bookings. Result: 20,580 requests, 0 failures; 5 contested windows, exactly 1 winner each; p50 about 100 ms, p95 about 430 ms (single-process containers on a laptop)
- [x] L-2 Spike: 30/s → 300/s for 60 s: 16,204 requests, 0 failures, p99 ≈ 220 ms, no shedding needed. At a 1,000/s target the single-process generator topped out (~125/s achieved) with 0 failures, p99 ≈ 1 s: the real breakpoint test belongs on staging (L-5)
- [x] L-3 Soak (20 min at 15/s, open model, 17,542 requests): 0 failures, p99 21–38 ms and flat, memory flat per service (±7 MiB), DB connections 21 → 21, every queue and DLQ empty. The hour-long run belongs on staging (L-5)
- [ ] L-5 Breakpoint and soak on staging in AWS with a distributed generator (k6 cloud or several workers), to size task maxima and ACUs
- [ ] L-4 Mixed journeys with an open arrival model (90% browse, 8% book, 2% accept/complete)
