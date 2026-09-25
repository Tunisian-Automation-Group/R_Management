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

- [ ] V1-1 Owners reach their accepted, active and completed bookings: `/bookings` has an "I'm hosting" view (`role=owner`), and Earn links each confirmed booking
- [ ] V1-2 Photos display: the Vite proxy forwards `/media`; relative media URLs resolve against the API origin (web and native shells)
- [ ] V1-3 Legal pages: Impressum, Privacy Policy and Terms, filled from build config (`VITE_LEGAL_*`), shown as "to be completed" rather than fake brackets when unset; the "prototype" footer removed
- [ ] V1-4 Profile: edit name, kind and district; export my data; delete my account (confirm sheet → `DELETE /me` → Cognito `DeleteUser` → signed out); Terms/Privacy links; consent line on sign-up
- [ ] V1-5 Forgot password: validate the email format; the right error message for an unknown address (never "email and password do not match")
- [ ] V1-6 Remove listing: confirm first; buttons that don't shift under the pointer
- [ ] V1-7 Edit a published listing (title, blurb, price, photos, rules, address, windows)
- [ ] V1-8 Handover address shown to the buyer once accepted (see contracts); owner enters the address when listing
- [ ] V1-9 Remove the "Cash or bank transfer" house-rule chip (it invites off-platform payment)
- [ ] V1-10 The map respects category and filters; its legend matches the times
- [ ] V1-11 Owner rating and listing reviews are labelled apart ("Nadia · 4.7 from 22 jobs" vs "This listing · 4.8 from 4 reviews"); "new here" only for an owner with no jobs
- [ ] V1-13 The week chart draws every sold booking, not only the first
- [ ] V1-14 A real 404 page; signed-out deep links keep their target through sign-in
- [ ] V1-15 Search, category and filters in the URL (shareable, back button works)
- [ ] V1-16 Search results show the price; readable "nothing free" state; Enter submits
- [ ] V1-17 The chosen slot survives sign-in in the middle of booking
- [ ] V1-18 Bookings and requests sorted by start time
- [ ] V1-19 Idle and free-this-week figures subtract sold hours and match the windows
- [ ] V1-20 "Earned" counts completed bookings only; "upcoming" shown apart
- [ ] V1-21 The owner's view of a booking shows the buyer, not the owner
- [ ] V1-22 Declined and cancelled bookings say the hold was released, not "receives €…"
- [ ] V1-23 Confirmed state with a success icon
- [ ] V1-24 Contrast of the earnings preview (WCAG AA)
- [ ] V1-25 Listing form: focus the first error, label every input, `4,00 €` formatting, districts grouped by city, duration chips from the listing's own minimum
- [ ] V1-26 "Free now" only when a bookable window (≥ the minimum) is actually left
- [ ] V1-27 The chosen city persists; sign-out clears the person's home district
- [ ] V1-29 Accessibility: an `<h1>` per screen, a per-route `<title>`, nav before main, a skip link
- [ ] V1-30 The confirm sheet shows the chosen start time
- [ ] V1-31 The start button says the hand-over opens 30 minutes before the booked time
- [ ] V1-32 Hero photo alignment on desktop
- [ ] V1-33 The "+" glyph in display titles
- [ ] V1-35 The review tag summary matches the tags on the reviews
- [ ] T-04 Honour `Retry-After`; forced-update screen from `/api/app-config` (see contracts)

## Verification round 1 — backend and data (V1)

- [ ] V1-8b Handover address: stored on the listing (owner only), returned on the booking once accepted
- [ ] V1-12 The e2e uses its own owner and removes what it creates; demo data stays clean
- [ ] V1-28 Refresh token: kept in the native shells' secure storage (Capacitor Preferences/Keychain); on the web it stays in storage under the CSP (accepted risk, ADR 0012)
- [ ] V1-34 Seed photos that match their listings (cosmetic; demo only)
- [-] V1-3 real legal text: needs the company's details from the owner of the business (asked)

## Resilience (F)

- [ ] T-01 Load shedding at the gateway: bounded in-flight requests per task, fast `503` + `Retry-After`
- [ ] T-03 Per-upstream bulkheads and per-route timeouts in the gateway
- [ ] T-05 Last-known-good JWKS so new tasks verify tokens during a Cognito outage
- [ ] T-08 Search needs 3+ characters (trigram index), checked with a plan at scale
- [ ] T-09 Per-user daily upload quota; sweep orphaned photos
- [ ] T-10 Nearest-first candidates with a KNN GiST index; a sane maximum radius
- [ ] T-11 Matching degrades without busy windows when booking is down
- [ ] T-16 Exponential backoff per SQS message before the DLQ (hours, not minutes)
- [ ] T-19 Chargebacks: record `charge.dispute.*`, hold the payout, alarm
- [ ] T-20 Cap open unpaid bookings per person (card testing)
- [ ] T-22 SES suppression list and bounce/complaint alarms
- [ ] T-24 RDS Proxy (decide from the research; wire in Terraform)
- [ ] T-25 Backup-restore drill in the runbook
- [ ] T-26 Region-outage decision recorded (RPO/RTO)
- [ ] T-29 Minimum app version (`/api/app-config`)
- [ ] T-31 Push notifications (SNS → APNs/FCM) for owners' requests
- [ ] T-33 Tracing (ADOT → X-Ray)
- [ ] T-34 Synthetic canaries
- [ ] T-35 SLOs and error budgets
- [ ] T-02, T-06, T-36 decided from the research (Bot Control, Cognito threat protection, canary deploys)

## From the research (R)

- [x] R-0 Card authorisations expire after 7 days: already safe (capture at accept, at most 24 h after the request)
- [ ] R-1 Payments reconciliation sweep: intents stuck in an intermediate state converge with Stripe
- [ ] R-2 Reject an idempotency key reused with a different request body
- [ ] R-3 Full jitter in the relay poll, the sweeps and client retry backoff
- [ ] R-4 Public GETs: `s-maxage` plus `stale-while-revalidate` and `stale-if-error` at the edge (with T-07)
- [ ] R-5 Connection budget written down and asserted; replica-lag alarm; reader in promotion tier 1
- [ ] R-10 Kill switches (settings): stop new bookings, stop payouts, stop new listings, without a deploy
- [ ] R-11 Game-day runbook (Aurora failover, stop half the tasks) with AWS FIS
- [ ] R-13 Web deletion page for Google Play (`/account/delete`)

## Load

- [ ] L-1 `make load`: 50 concurrent browsers for 60 s plus contested bookings, with no errors and no double booking
- [ ] L-2 Spike: 10× the baseline arrival rate for 60 s; shedding keeps accepted requests fast
- [ ] L-3 Soak: an hour at normal load; connections, memory and queue ages stay flat
- [ ] L-4 Mixed journeys with an open arrival model (90% browse, 8% book, 2% accept/complete)
