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

### Batch S (stores and marketplace), backend shipped, web to build

Fields that are null are left out of answers, as everywhere in the API.

- **S-5 age.** `PUT /me` needs `adult: true` when the profile is first created (checkbox "I am 18 or
  older" at onboarding). Without it: `422 {error: {code: "invalid", message: "Cappy is for people aged
  18 or over: confirm your age to continue"}}`. Later edits need not send it. Existing profiles are
  grandfathered.
- **S-4 traders.** `PUT /me` with `kind: "business"` needs
  `business: {legalName (2–160), address (8–300), registerNumber? (≤60), vatId? (≤20)}`, else 422.
  The VAT ID is normalised (spaces, dots and dashes removed, upper case). A German one must be
  `DE` + 9 digits; other EU ones are checked loosely; a bad one gives 422. Every `Owner` answer
  (`/me`, `/owners/{id}`, listing and search answers) carries `owner.business` with the same four
  fields for businesses only. A person never has one, even if they send it. Show it on the listing and
  at checkout with "Your contract is with {legalName}; Cappy is not your contract partner".
- **S-18 reliability.** `Owner.cancellationRate` is 0–1: the share of accepted bookings in 12 months
  the owner cancelled or did not show up for. It is absent under 5 accepted bookings. Show it only
  when it is above 0 ("Cancelled 2 of 10 bookings"). Ranking multiplies trust by
  `1 − 0.5 × cancellationRate`, so the ranking page (`web/src/app/screens/Legal.tsx`, "How ranking
  works") must say that owners who cancel accepted bookings rank lower.
- **S-11 no-shows.** `POST /bookings/{id}/no-show` (no body), by either side about the other, only on
  an `accepted` booking.
  - The renter reports the owner from the booked start until start + 2 h. The owner reports the renter
    from start + 30 min until start + 2 h. Outside these times it gives 409 with a message.
  - Result `status: "cancelled"`, `noShow: "owner" | "renter"`, `refundAmount`: the full amount when the
    owner did not come, `0` when the renter did not. An owner no-show counts against the owner.
  - Suggested UI: on an accepted booking once the time has started and nobody marked the hand-over,
    "They didn't show up", with a confirm sheet that shows the refund.
- **S-13 reports and statements of reasons.**
  - `POST /reports` needs `goodFaith: true`, else 422 "confirm that what you report is accurate and
    complete…". Add a required checkbox: "I confirm this report is accurate and complete to the best of
    my knowledge."
  - The admin decide endpoints (`POST /admin/reports/{id}/decide`, `/admin/listings/{id}/take-down`,
    `/admin/owners/{id}/suspend`) accept, besides `statement` (the facts, ≥ 20 chars):
    - `ground: "law" | "terms"`, default `terms`;
    - `clause?` (≤ 200; default "Terms of use: rules for listings and conduct", or "the applicable law");
    - `automated?: bool`, default false.
  - `Report` answers carry `statementOfReasons: {restriction, facts, automated, ground, clause,
    redress}` after a take-down or suspension (never after a dismissal). The affected person's email
    spells all of it out in their language.
- **S-17 and S-18 staff queue.** `GET /admin/reports` now also lists notices from the system:
  `targetType: "owner"` with `reason: "reliability"` (3 or more owner cancellations or no-shows in 30
  days) or `reason: "linked_to_suspended"` (paid with a card a suspended account used). Their
  `details` say why. They are decided like any report. Give the two reasons readable labels in the
  admin console.
- **S-30 DSA numbers.** `GET /api/admin/dsa-stats?month=YYYY-MM` (staff) returns
  `{month, activeRecipients, notices: {byReason: {reason: n}, byDecision: {dismiss|take_down|suspend|open:
  n}}, medianHoursToDecision}`. `activeRecipients` is a lower bound (parties to bookings made in the
  month); `docs/analytics.md` has the exact Athena query.
- **S-26 feature flags.** `GET /api/app-config` → `{minVersion, latestVersion, flags: {name: bool},
  rollouts: {name: percent}}` (set with `FEATURE_FLAGS="name:percent,…"`).
  - A flag at 100 is `true`; at 0, or while rolling out, it is `false`. Rollouts are evaluated by the
    app for the signed-in user, so the answer stays cacheable: `bucket = fnv1a32(name + ":" + userId)
    % 100`, and the user is in when `bucket < percent`.
  - FNV-1a 32-bit starts with offset `0x811C9DC5` and uses prime `0x01000193` over the UTF-8 bytes.
  - Test vector: `bucket("newcheckout", "user-1") == 16`.
  - A deviation from the brief: the flags are not evaluated on the server per user, because the CDN
    caches this answer for everyone.
- **S-7 crash reports.** `POST /api/client-errors`, signed in or not, body ≤ 8 KB:
  `{message (≤2000), stack? (≤6000), route? (≤300), appVersion? (≤40), platform?: "web"|"ios"|"android"}`.
  - Returns 202, including when the per-address limit of 10 a minute drops a report. A body over the
    size limit gives 413; one that isn't a valid error report gives 422.
  - Send from the `ErrorBoundary`, `window.onerror` and `unhandledrejection`, at most once per distinct
    message per session. Never include device ids or user data.

### Batch V3 (verification round 3), backend shipped, web to build

- **Invoices (V3-2, V3-22):** each item of `GET /api/payments/invoices` also carries `description` ("Service fee · <listing> · <service day(s)>", German days), `title?`, `serviceStart?` and `serviceEnd?`. Show `description` on each row. The invoice page now has the issuer (settings `LEGAL_COMPANY`, `LEGAL_ADDRESS`, `LEGAL_VAT_ID` / `LEGAL_TAX_NUMBER`; payments refuses to start in a deployed env without real values; Terraform `legal` variable, required), the recipient (a trader's legal name, address and VAT ID; a person's name), `Leistungsdatum`, and dates in Europe/Berlin. Invoices issued before this keep the old fields. The issuer's time zone, tax rate and tax label are settings (`INVOICE_TIME_ZONE`, default Europe/Berlin; `INVOICE_TAX_RATE_BPS`, 1900; `INVOICE_TAX_LABEL`, USt), so another market's entity is configuration; the page template is still the German § 14 one.
- **Booking snapshot:** `booking.listing.ownerBusiness?` (`{legalName, address, registerNumber?, vatId?}`) when the owner is a trader: the renter's contract partner, for the "your contract is with…" line.
- **Masking (V3-6):** once a booking is accepted (accepted, active, completed, disputed), `GET /bookings/{id}/messages` returns earlier messages as written, contact details included, to both sides. Before that, and on bookings that were never accepted, they stay masked with `[shared once the booking is accepted]`.
- **Notification language (V3-13):** `GET /api/notifications` renders every item's `title` and `body` in the language of the `Accept-Language` request header (`de…` → German, else English). **Send `Accept-Language: <app language>`** on that call (the gateway now forwards it). A new request says the real deadline: "Answer by Sat 26 Sep, 14:00, or the request lapses" / "Bitte antworte bis Sa., 26.09., 14:00 Uhr, sonst verfällt die Anfrage.", in the event's `timeZone` when it carries one (listings have none yet), else Europe/Berlin.
- **Notification settings (V3-21):** `GET /api/notifications/settings` → `{categories: {bookings: {push, email}, messages: {push, email}, payouts: {push, email}, marketing: {push, email}}}`. Defaults: all true, marketing both false. `PUT` takes the same full shape (422 if any category is missing) and returns it. The bell always gets everything. Emailed whatever the setting: a booking confirmed (including instant book), declined, lapsed or cancelled, and every moderation email; say so under the switches ("Booking confirmations and changes always arrive by email."). Messages are never emailed, so their email switch changes nothing today. The settings are in the data export (`notifications.settings`) and deleted with the account. The data export's `notifications` is now `{items, settings}` instead of a list.
- **Sign out everywhere (V3-23):** not reproducible on the backend: the one request in the logs got 204 from notifications and from the gateway, and no 503 reached either in 4 h. A 503 the gateway never logged comes from the dev server's proxy (for example while containers restart). The web should keep reporting a non-2xx as a failure.

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
- [x] Store shells: Capacitor iOS and Android projects, push registration, refresh token in app storage (V1-28), deep links (apple-app-site-association, assetlinks.json), share-sheet export, `/account/delete` for Google Play (R-13). Building and signing needs Xcode and Android Studio with the store credentials
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
- [x] R-13 Web deletion page for Google Play (`/account/delete`)

## Launch gaps (G) — from docs/research/2026-09-launch-gaps.md

Engineering, before launch:
- [x] G-1 Admin console (web /admin and API: queue, decide, take down, suspend/reinstate, resolve disputes, audit; staff = Cognito group admin). The web console screens are next. Scope: moderation queue, take down or reinstate a listing, suspend a user with an Art. 17 statement of reasons, refund, pause payouts, resolve disputes; audited, role-gated
- [x] G-2 (API) DSA Art. 16 notice-and-action ("report this" on listings and profiles) with acknowledgement and outcome email; Art. 17 statements of reasons; Art. 11/12 contact points on the legal pages
- [x] G-3 Report (`POST /api/reports`, with G-2) and block users (`/api/me/blocks`): no messages or new bookings between them, either way. Reporting comes with G-2
- [x] G-4 In-app messaging per booking (`/api/bookings/{id}/messages`); phone numbers, emails, links and messenger handles masked until accepted; pushed to the other side (never emailed)
- [x] G-5 (API) Check-in and check-out photos on a booking (`/api/bookings/{id}/evidence`), the parties' own uploads, never swept
- [x] G-6 Checkout compliance: total price including the fee; "zahlungspflichtig buchen"; trader/private owner label; withdrawal information and the withdrawal button; review-verification statement; ranking parameters page
- [x] G-7 German localisation: every email and push by the recipient's Cognito `locale`; the whole web UI and legal pages (827 entries, `npm run check:i18n`), "Zahlungspflichtig buchen", Widerrufsbelehrung and Muster-Widerrufsformular
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

## App UX (U) — from docs/research/2026-09-app-ux.md

Signed-in only is a deliberate choice against Apple 5.1.1(v); U-1 carries the argument into App Review, U-2 keeps a fallback ready.

- [x] U-1 [all] App Store Connect review notes: the 5.1.1(v) justification for members-only access (verified private owners, location/availability of people's property, every feature account-bound) and demo accounts for renter and owner with email-code bypass — https://developer.apple.com/app-store/review/guidelines/#5.1.1 · https://developer.apple.com/distribute/app-review/
- [x] U-2 [all] Welcome screen (`Welcome.tsx`) for first-timers: one hero, 3 value lines, "Create account" / "I have an account", DE/EN switch, legal links; no live listing data — https://developer.apple.com/design/human-interface-guidelines/onboarding
- [x] U-3 [all] Welcome shown once: `welcomeSeen` flag; skipped for any device that has signed in before and for deep-link launches; "How Cappy works" reachable from Help — https://developer.apple.com/design/human-interface-guidelines/onboarding
- [x] U-4 [app] Move the push permission prompt out of `pushSignedIn()`: priming sheet after the first booking request or listing publish; ask only when `checkPermissions()` is `prompt` — https://developer.android.com/training/permissions/usage-notes
- [x] U-5 [app] Android back: `App.addListener('backButton')` closes the open sheet, else goes back, else minimises; predictive back enabled — https://capacitorjs.com/docs/apis/app
- [x] U-6 [backend] `Idempotency-Key` on `POST /bookings`, `/listings`, `/reviews`, `/messages`, and on booking payment confirmation; web sends one key per form mount — https://docs.stripe.com/api/idempotent_requests + (web sends one key per form for listings, messages, evidence and ratings; web, uncommitted)
- [x] U-7 [app] 3DS/SCA return into the shells: `return_url` on an associated domain, resume handler checks the PaymentIntent and shows the result; test with the 3DS2 test cards on iOS and Android — https://docs.stripe.com/payments/3d-secure/authentication-flow (web, uncommitted — return to /pay/return on the API domain (universal/app link); needs a device test)
- [x] U-8 [web] Times in the listing's time zone (`Intl.DateTimeFormat` with `timeZone`), label when it differs from the device; [backend] a DST-crossing booking test — https://developer.mozilla.org/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat
- [x] U-9 [backend] Account deletion refused with a reason and a date while bookings are open or a payout is pending; the retention list (invoices kept 10 years) shown before confirming — https://developer.apple.com/support/offering-account-deletion-in-your-app/ + (web shows the 409 reason and date and the 10-year retention line; web, uncommitted)
- [x] U-10 [web] Session expiry mid-flow keeps the draft (AddListing, messages, review) and returns to it after sign-in — https://baymard.com/research/checkout-usability
- [x] U-11 [web] Offline bar (`online`/`offline` events), cached reads, money actions disabled offline with the reason — https://web.dev/articles/offline-ux-design-guidelines
- [x] U-12 [backend] Message scanner: detect phone, email, IBAN, URLs and "pay outside" phrases; before a booking is confirmed mask contact details; log for moderation — https://www.airbnb.com/help/article/209
- [x] U-13 [web] Chat safety UI: inline warning to the sender, a banner to the receiver ("Payments outside Cappy aren't protected"), report on each message, block offered after reporting — https://www.airbnb.com/help/article/2020 · https://www.vinted.com/help/628-recognize-spoof-and-phishing-messages (sender warning and receiver banner; "block after reporting" not added) — also: block offered after reporting a message
- [ ] U-14 [backend]+[web] Email one-time-code sign-in through Cognito `USER_AUTH`/`EMAIL_OTP`, password kept as an option — https://docs.aws.amazon.com/cognito/latest/developerguide/authentication.html
- [x] U-15 [backend]+[web] Password policy: min 12, no composition rules, breached-password check; rules visible under the field; show/hide toggle; paste allowed — https://pages.nist.gov/800-63-4/sp800-63b.html · https://baymard.com/blog/password-requirements-and-password-reset + (web: 12+ characters, rule shown under the field, show/hide toggle; web, uncommitted)
- [x] U-16 [web] Code field: `inputmode="numeric"`, auto-submit at 6 digits, 30-second resend countdown — https://www.w3.org/TR/WCAG22/#accessible-authentication-minimum
- [ ] U-17 [app] Refresh token in Keychain/Keystore instead of Preferences (closes V1-28) — https://developer.apple.com/documentation/security/keychain-services
- [x] U-18 [web] Sign-in screen says why Cappy is members-only, with a "How we keep you safe" link — https://baymard.com/blog/password-requirements-and-password-reset
- [x] U-19 [web] Onboarding: optional "rent / earn / both" choice that picks the landing tab and the empty states — https://www.nngroup.com/articles/mobile-app-onboarding/
- [x] U-20 [web] Listing page: cancellation policy in plain words, owner response time, and a sticky bar with the total for the chosen slot, fee included — https://skift.com/2025/04/21/airbnb-makes-total-price-display-standard-on-listings-worldwide/ — sticky bar shows the total with "incl. {fee} service fee"; policy and response time were already there
- [ ] U-21 [web] Browse filters: applied-filter chips with ✕ and "Clear all"; "Show N results" in the filter sheet; [backend] result count — https://baymard.com/blog/how-to-design-applied-filters
- [x] U-22 [backend]+[web] Notification centre: `GET /notifications` (paginated, unread count), a bell, each item opens its screen; per-category push/email settings, marketing off by default — https://m3.material.io/foundations/content-design/notifications + (web: bell in the desktop header, unread badge on the You tab, /notifications list; web, uncommitted)
- [x] U-23 [web] Empty states for Bookings, Earn, inbox, reviews, saved and no-results, each with a reason and one action — https://www.nngroup.com/articles/empty-state-interface-design/
- [x] U-24 [web] Error messages: Stripe decline codes mapped to plain DE/EN; a generic error screen with "Try again" and the request id — https://www.nngroup.com/articles/error-message-guidelines/
- [x] U-25 [web] Photo uploads: per-photo progress and retry, client-side downscale to 2048 px, HEIC accepted or converted, the draft survives the app being killed — https://baymard.com/research/mcommerce-usability — XHR progress per photo, retry on failure, 2048 px canvas downscale, HEIC refused with a reason where the browser cannot decode it; evidence retries reuse already-uploaded photos
- [ ] U-26 [app] Keyboard: `@capacitor/keyboard`; focused inputs and the chat composer stay above the keyboard on iOS and Android 15 edge-to-edge (WCAG 2.4.11) — https://capacitorjs.com/docs/apis/keyboard — partly: no keyboard plugin: interactive-widget=resizes-content and scroll margins instead
- [x] U-27 [app] Dynamic Type in the iOS shell (`-apple-system-body` root, rem sizes); check dock, listing bar and sheets at the largest size — https://www.tpgi.com/text-resizing-web-pages-ios-using-dynamic-type/ — type sizes in rem (177 conversions); iOS shell sets the root from `-apple-system-body`; checked at 200 % in a 390 px frame: sticky bar wraps, weekday strip wraps, no page overflow. Native Dynamic Type itself untested (no Xcode)
- [x] U-28 [web] Pseudo-localisation switch (+40% string length) and one verifier pass on it per round, for German length — https://www.w3.org/International/articles/article-text-size — `?pseudo=1` in dev builds only; checked at 390 px
- [x] U-29 [web] Colour scheme: dark tokens with `prefers-color-scheme`, or pin `color-scheme: light` plus the status-bar style so native controls match — https://developer.apple.com/design/human-interface-guidelines/dark-mode
- [ ] U-30 [web] axe-core accessibility check over every route in CI; fix targets under 24 px, focus return from sheets, `role="status"` toasts, reduced motion — https://www.w3.org/TR/WCAG22/ — partly: `npm run check:a11y` is a static scan (img alt, targets ≥ 24 px); axe-core is not installable offline, so the full audit is manual (Chrome Lighthouse). Toasts already role=status, reduced motion already handled
- [x] U-31 [web] Accessibility statement (Barrierefreiheitserklärung) at `/legal/accessibility` in DE/EN with a feedback contact — https://www.bundesfachstelle-barrierefreiheit.de/DE/Fachwissen/Produkte-und-Dienstleistungen/Barrierefreiheitsstaerkungsgesetz/barrierefreiheitsstaerkungsgesetz_node.html
- [ ] U-32 [backend]+[web] ID verification badge (Stripe Identity / Connect KYC), required before the first booking above a threshold and for vans; the badge says what was checked — https://www.airbnb.com/help/article/1237
- [x] U-33 [web] Hand-over photos: a prompt at start and end, the upload time shown, the 24-hour damage-report window stated — https://help.turo.com/en_us/trip-photos-guide-or-guests-HytcE4g49 — prompts at hand-over and hand-back existed; the upload time and the report window (until marked complete, at most 48 h after the end) are shown
- [x] U-34 [web] Safety card on BookingDetail before the first hand-over; one line on payment protection under the pay button — https://help.turo.com/en_us/trip-photos-guide-or-hosts-BkKcBEeN5 — safety card while accepted; payment-protection line under "Book and pay"
- [x] U-35 [backend]+[web] Sessions: "sign out everywhere" in Profile; Cognito `GlobalSignOut` on password reset; push devices removed with it — https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GlobalSignOut.html + (web: Profile → Sign out everywhere; plain sign-out now revokes only this device's refresh token; web, uncommitted)
- [x] U-36 [app] Push-denied state: a Profile row "Notifications are off — Turn on" that opens the OS settings — https://developer.android.com/training/permissions/usage-notes
- [x] U-37 [web] Bookings: a "next up" card at the top with the one action that matters now; statuses in text as well as colour (WCAG 1.4.1) — https://www.w3.org/TR/WCAG22/#use-of-color
- [x] U-38 [web] Earn: "needs you" section first, with a countdown to each request's expiry (Airbnb Today tab pattern) — https://www.nngroup.com/articles/dashboards-preattentive/
- [x] U-39 [web] `/help` with 10–15 DE/EN articles and "Get help with this booking" (booking id attached) on BookingDetail — https://help.turo.com/
- [ ] U-40 [backend]+[web] Responsive images: 400/800/1600 widths from the media service, `srcset` with `width`/`height` set, placeholders — https://web.dev/articles/cls

## Stores and marketplace (S) — from docs/research/2026-09-store-and-marketplace.md

- [x] S-1 [app] Add `PrivacyInfo.xcprivacy` to the App target: UserDefaults `CA92.1`, file timestamp `C617.1`, disk space `E174.1` if filesystem uses it, `NSPrivacyTracking=false`, the collected data types. Check with an Xcode privacy report — https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api (63e6c1c; UserDefaults CA92.1 and file timestamps C617.1 for @capacitor/filesystem; no disk-space API used; Xcode privacy report still to run)
- [ ] S-2 [app] `NSCameraUsageDescription` (and `NSPhotoLibraryAddUsageDescription` if saving) in `Info.plist`, DE/EN via `InfoPlist.strings`. Test evidence "Take Photo" on a device — https://developer.apple.com/forums/thread/772332 — English strings done (63e6c1c); German InfoPlist.strings and a device test left
- [ ] S-3 [legal/business] Data inventory → Apple app privacy label + Play Data safety form (Stripe.js/Identity signals, payment, ID images, photos, messages, location district, crash data), matching the privacy policy — https://developer.apple.com/app-store/app-privacy-details/ · https://support.google.com/googleplay/android-developer/answer/10787469
- [x] S-4 [backend]+[web] Business owners: collect legal name, address, register number and VAT ID. Show them on the listing and at checkout, with "Cappy is not your contract partner" (§ 5b UWG, § 312l BGB). This is also the base for KYBC later — https://www.gesetze-im-internet.de/uwg_2004/__5b.html — **backend done (uncommitted)**, web and the rest open
- [ ] S-5 [legal/business] Minimum age 18 in the terms, an "I am 18+" confirmation at sign-up, and 18+ in both store questionnaires, including Apple's September 2026 social-media question — https://developer.apple.com/news/?id=tlur8uvi — **backend: adult at sign-up done (uncommitted)**, web and the rest open — web: "I am 18 or older" at onboarding done; terms text and store questionnaires still open
- [ ] S-6 [legal/business] App Store Connect DSA trader status (address, phone and email published) and a Play organisation account with a D-U-N-S number (avoids the 12-tester/14-day gate) — https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements/ · https://support.google.com/googleplay/android-developer/answer/14151465
- [x] S-7 [web] Crash and error reporting: `@sentry/capacitor` (or a self-hosted `/api/client-errors` endpoint) from `ErrorBoundary`, `window.onerror` and `unhandledrejection`. Upload source maps per release. No replay or device id without consent (§ 25 TDDDG) — https://docs.sentry.io/platforms/javascript/guides/capacitor/ — **backend endpoint done (uncommitted)**, web and the rest open
- [ ] S-8 [backend]+[web] Owner damage claim: owners report within 24 h of the end with evidence. The payout is held while a claim is open, the renter has 72 h to answer, then staff decide with reasons — https://www.airbnb.com/help/article/1415 · https://faq.fatllama.com/en/articles/10391171-what-are-the-criteria-for-the-lender-guarantee — **blocked on S-9/G-B1**: without a saved card or deposit an upheld claim cannot collect
- [ ] S-9 [backend]+[legal/business] Collecting on a claim: save the card for off-session use at booking (`setup_future_usage`), or a separate deposit hold per category (vans). The amount is shown in the total and the terms. Depends on G-B1 — https://docs.stripe.com/payments/save-during-payment
- [x] S-10 [app] `android:allowBackup="false"` (or `dataExtractionRules` excluding the token prefs), and `arm64` instead of `armv7` in `UIRequiredDeviceCapabilities` — https://developer.android.com/identity/data/autobackup (63e6c1c)
- [x] S-11 [backend]+[web] No-show reports: either side within 2 h of the start. A renter no-show counts as a late cancellation under the policy. An owner no-show means a full refund and counts against the owner — https://www.airbnb.com/help/article/3591 — **backend done (uncommitted)**, web and the rest open (no-show button built; not exercised in the browser: needs a booking whose start has passed)
- [ ] S-12 [backend]+[web] Late return: "extend booking" when the next window is free. Otherwise, after 30 min grace, the normal rate for the extra time plus a capped late fee, reported by the owner within 24 h — https://getaround.com/help/articles/b075d5c22795
- [x] S-13 [backend]+[web] Structured Art. 17 statement: restriction, facts, automated yes/no, legal ground or T&C clause, redress text (reply to contest, courts). A good-faith checkbox in the report form (Art. 16(2)(d)) — https://dsa-library.com/article/17/ · https://dsa-library.com/article/16/ — **backend done (uncommitted)**, web and the rest open
- [ ] S-14 [app] Android 16 edge-to-edge check at targetSdk 36: Capacitor SystemBars / insets for the dock, sheets and toasts, with gesture and 3-button navigation on API 35 and 36 (with U-26) — https://developer.android.com/about/versions/16/behavior-changes-16 — partly: side safe-area insets for body, sticky bar, sheets and toasts (landscape notch); needs a check on a real Android 15/16 device
- [x] S-15 [web] Route-level code splitting (`React.lazy` for Admin, AddListing, Earn, Profile, Legal). A CI budget of ≤170 KB gz for the entry chunk — https://web.dev/articles/performance-budgets-101 — entry chunk 217.8 → 144.5 kB gz; screens, PayStep and the DE/FR catalogues are lazy; `npm run check:size` budget 170 kB
- [x] S-16 [all] Review notes for 3.1.3(e) (physical services, card/Apple Pay, no IAP) and 4.2 (the native features list), added to U-1 — https://developer.apple.com/app-store/review/guidelines/ (073ccf1, docs/app-review.md)
- [x] S-17 [backend] Ban-evasion linkage: store the Stripe card fingerprint and the Connect bank fingerprint. A new account sharing one with a suspended account is held for review — https://docs.stripe.com/api/cards/object#card_object-fingerprint — cards only: the Connect bank-account fingerprint is left for when payouts read the external account
- [x] S-18 [backend] Owner cancellation consequences: counted per owner, shown as a rate on the profile, a ranking signal (and the ranking page updated), repeat cancellations queued for staff. A fee **(counsel)** — https://www.airbnb.com/help/article/990 — the fee waits for counsel; the ranking-page text is for web — web: rate on the listing, ranking page updated
- [ ] S-19 [legal/business] Withdrawal right by category: vehicle rental and fixed-date leisure services are exempt (§ 312g(2) Nr. 9 BGB). The checkout text and button follow the category **(counsel, G-B2)** — https://www.gesetze-im-internet.de/bgb/__312g.html
- [ ] S-20 [backend] Duplicate-listing detection: a perceptual hash (pHash) per photo. Matches across different owners go to the held queue (G-9) — https://github.com/JohannesBuchner/imagehash
- [ ] S-21 [backend]+[web] Dispute flow between the parties: a 72 h response window, an offer or counter-offer for a partial refund, auto-escalation to staff after the deadline — https://www.airbnb.com/help/article/767
- [ ] S-22 [legal/business] P2B for business owners: 30 days' notice before termination, two named mediators in the terms, the 15-day notice for terms changes as a process — https://eur-lex.europa.eu/eli/reg/2019/1150/oj/eng
- [ ] S-23 [web] Core Web Vitals field data (`web-vitals` → the analytics event pipeline). Targets: LCP 2.5 s, INP 200 ms, CLS 0.1 at p75 — https://web.dev/articles/vitals
- [ ] S-24 [app] Cold-start measurement on a mid-range Android (TTID in Play vitals, Xcode Organizer launch time). Budget 2 s; the splash screen hides on the first render — https://developer.android.com/topic/performance/vitals/launch-time
- [ ] S-25 [infra]+[docs] Release runbook: Play staged rollout 5→20→50→100% and App Store phased release, with a gate on crash-free sessions ≥99.5% and Android vitals below 1.09%/0.47%, and a halt procedure — https://support.google.com/googleplay/android-developer/answer/6346149 · https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases
- [x] S-26 [backend]+[web] Percentage and per-user feature flags (on top of R-10 kill switches), read at app start from `/api/app-config` — https://martinfowler.com/articles/feature-toggles.html — **backend done (uncommitted)**, web and the rest open (bucket self-check: `npm run check:flags`)
- [ ] S-27 [app] In-app review prompt (`@capacitor-community/in-app-review` or similar) after a completed booking the user rated 4★ or more, at most once per 120 days — https://developer.apple.com/documentation/storekit/requesting-app-store-reviews · https://developer.android.com/guide/playcore/in-app-review
- [ ] S-28 [backend] Review-collusion signals: reciprocal 5★ pairs, reviews between accounts that share a payment fingerprint, bursts from new accounts. Flag for staff, never auto-delete (Omnibus) — https://www.gesetze-im-internet.de/uwg_2004/anlage.html
- [ ] S-29 [app] 16 KB alignment check of the release AAB (`zipalign -c -P 16`, Play bundle explorer) once per plugin upgrade — https://developer.android.com/guide/practices/page-sizes
- [x] S-30 [backend] DSA counts derivable on request: monthly active recipients (Art. 24(3)), notices by reason and decision, median time to decision — https://prighter.com/resources/dsa-reporting-obligations/
- [ ] S-31 [legal/business] DAC7: switch on Stripe payout withholding for sellers who don't provide their TIN, and document the two-reminder rule (with G-10) — https://docs.stripe.com/connect/platform-tax-reporting
- [x] S-32 [docs] Tick R-13 in TASKS: `/account/delete` already works signed-out (`web/src/app/App.tsx:55`) — https://support.google.com/googleplay/android-developer/answer/13327111 (R-13 ticked)

## Verification round 3 (V3)

Run by a separate verifier on the local stack, 2026-09-26 (00:25–00:50 CEST), with the demo buyer, host and staff. The web version was checked at 1400 px. The app version was checked at 606 px and in a 390×844 same-origin iframe; the Capacitor shells can't run here. Checked in EN and DE. Severity order, most severe first.

- [x] V3-1 [web] Stripe.js loads on every page, including the signed-out Welcome and Login screens: `js.stripe.com/dahlia/stripe.js` plus the `m-outer` fraud-signal iframe. Cause: `PayStep.tsx` does a top-level `import { loadStripe } from '@stripe/stripe-js'`, which injects the script as a side effect, and `Listing`/`BookingDetail` import `PayStep` statically. Repro: clear storage, open `/login`, list the page's scripts and iframes. Expected: no third-party script before sign-in, and none before the pay step (`@stripe/stripe-js/pure` + load on demand). This is § 25 TDDDG and GOAL 13
- [x] V3-2 [backend] The fee invoice (`GET /payments/invoices/CAP-2026-0000004`) has no issuer name, address or tax number ("siehe Impressum"), no recipient, and no service date. § 14 (4) UStG requires all of these. Its "Rechnungsdatum" is also the UTC day (25.09.2026) while the Earn list shows 26.9.2026 for the same invoice, issued 00:4x CEST. Expected: the mandatory § 14 fields, and a date in Europe/Berlin (backend, uncommitted; see "Batch V3" contracts)
- [x] V3-3 [web] An instant-book listing reads as request-to-book everywhere except its badge. Repro: buyer opens l9 (instant book on). The sticky bar and desktop card say "Request"/"Anfragen", with "Instant book: confirmed…" directly under that button on desktop. The price box says "Paid by card when Nadia accepts; if they decline, the hold is released". The confirm sheet is titled "Confirm request". On the booking the first step reads "Requested — Waiting for the owner to accept". On phone width the instant-book line under the button is `hidden md:block`. Expected: "Book"/"Buchen", and copy that says it is confirmed at once
- [x] V3-4 [web] Buyers are shown cancellation terms that are not applied. l9 shows "Strict: full refund until 7 days before, half until 24 hours before, then nothing" on the listing and in the confirm sheet. The backend has `paid_cancellation_policies=false`: withdrawing 4 days before gave a full €28.80 refund, which is what the refund preview said. The host form discloses this ("gelten, sobald Cappy sie freischaltet"); the buyer side doesn't. Expected: buyers see the rule that actually applies (flexible) until the switch is on
- [x] V3-5 [web] Messages flagged by the scanner get no UI. Repro: buyer sends "call me on 0151 23456789, I can pay via PayPal". The API returns `flagged: true`, but the sender sees no warning and the host sees no "payments outside Cappy aren't protected" banner (`flagged` is not read anywhere in `web/src`). This is U-13, still open; the backend half is live
- [x] V3-6 [backend] Contact masking is permanent and its text becomes wrong. A number/email sent before acceptance is stored as "[shared once the booking is accepted]". After the host accepts, and even after completion, both sides still see "Kontakt verborgen bis zur Annahme". Expected: reveal after acceptance, or placeholder text that stays true ("removed: share contact details after booking") (backend, uncommitted; see "Batch V3" contracts)
- [x] V3-7 [web] Signing out in one tab leaves other tabs signed in, with product data on screen and API calls working on the in-memory access token. Repro: tab A and tab B signed in; sign out in A; in B, navigate to Bookings — it still loads. Worse: after A signs in as another account, a reload of B silently becomes that account. Expected: listen for the `storage` event on `cappy.refresh.v1` and sign out or reload the other tabs
- [x] V3-8 [web] Rating the renter posts on the first tap of a star, with no confirm and no undo (`BookingDetail.tsx`, the `rateTheRenter(n)` onClick). One mis-tap leaves a permanent 1★. Hover also fills only the hovered star, not the ones before it, and the stars expose no selected state. Expected: pick, then "Submit", as the buyer's review sheet already does
- [x] V3-9 [app] The offline bar covers the listing's sticky booking bar at phone width, hiding the price, date and CTA label. Repro: `/listing/l9` at <768 px, dispatch `offline`. Expected: the bar sits above the sticky bar or pushes it up
- [x] V3-10 [web] Listing drafts: an edit of an existing listing is lost on reload, with no leave warning. Repro: `/earn/edit/l9`, untick Instant book, reload — it is ticked again. A new listing (`/earn/new`) keeps only category, title, blurb, district and address. Price (7,50 → 4,00), extras, discounts, policy, instant book and slots reset. Expected: the whole form survives (U-10/U-25)
- [x] V3-11 [web] Bookings → I booked → Upcoming shows a "Next up" card for a completed booking ("Rate how it went"). Directly under it is the empty state "Nothing upcoming — your past bookings are under Past". Expected: the rate prompt lives under Past (or its own card) without a contradicting empty state. The next-up card also has no date or photo
- [x] V3-12 [web] The hand-over photo sheet uses the unstyled native file input: "Choose Files / No file chosen" in English inside the German UI (host → "Ich habe es übergeben"). Expected: a styled, translated picker button with thumbnails
- [x] V3-13 [backend] Notifications are stored as text in the language of the moment, so the list is mixed: "Cancelled: …", "New message: …" and "New booking: …" sit next to "Neue Anfrage: …" for the host in DE. The new-request notification says "Bitte antworte innerhalb eines Tages" while the Earn countdown for the same request says 16 h (it expires at the start). Expected: render title/body per the viewer's language from kind + params, and state the real deadline (backend, uncommitted; see "Batch V3" contracts)
- [x] V3-14 [web] Untranslated strings in DE: the eyebrow "New listing" on `/earn/new`; the admin report card "spam · listing l9" (raw reason code and "listing")
- [x] V3-15 [web] DE double full stop on a pending booking: "Antwortet in ~12 Min.. Deine Karte ist reserviert…". `BookingDetail.tsx:391` appends ". " after `responseTime()`, and the German string already ends in "Min."
- [x] V3-16 [web] Day labels are a single letter + date: "S26 S27 M28 T29 W30 T1 F2" (DE "S26 S27 M28 D29 M30 D1 F2"). Sat/Sun, Tue/Thu (EN) and Mon/Wed, Di/Do (DE) can't be told apart, on the Earn chart and on the listing's idle-time strip. Expected: "Sa 26", "So 27" (two-letter weekday)
- [x] V3-17 [app] The Explore "Free in the next 24 hours" cards at phone width cut the distance to "5.3 …" / "1…" next to "Host ★ 4.5". Expected: distance readable, or drop the "Host" label
- [x] V3-18 [web] After the buyer withdraws from an accepted booking, the chat shows "Phone numbers… are hidden until the booking is accepted" (it had been accepted) and the composer stays open on the cancelled booking. The "Cancelled" toast is drawn on top of the sticky action bar and hides its button
- [x] V3-19 [web] The "Wednesday, 09:00 – 17:00" weekday-only format in the confirm sheet, booking detail and "What you agreed" gives no date for bookings 2–7 days out. Expected: "Wed 30 Sep, 09:00 – 17:00"
- [x] V3-20 [web] Closing the Filters sheet (Escape or ✕) sends focus to `<body>` instead of back to the "2 hours · 75 km" trigger. The focus trap inside works (U-30)
- [x] V3-21 [web] The Profile → Notifications section has no per-category push/email settings, only "Everything also arrives by email". U-22 is ticked with that scope. There is also no "mark all as read" on `/notifications`; items are marked read on open — backend done (settings API, uncommitted); web to build
- [x] V3-22 [web] Earn → Invoices rows show only number, date and amount, not what the invoice is for (fee for which booking). The section is hidden when empty, with no empty state. `openInvoice` opens a blob URL via `window.open('')` (unconfirmed in the iOS/Android shells) — backend done (`description` on invoice rows, uncommitted); web to build
- [x] V3-23 [web] "Sign out everywhere": the browser logged the request `POST /api/me/sign-out-everywhere` as 503 while the gateway logged 204 (unconfirmed). cognito-local's GlobalSignOut returned 500, a known local gap. Either way the web ignores both results and reports success. Expected: tell the user when revoking other sessions failed — backend: no 503 reached the gateway (one request, 204); web to report failures

## Security (P) — from docs/research/2026-09-security-review.md

- [x] P-1 [backend] H-1: zero or negative `unitsPerHour` (and other numeric listing fields) are accepted, and one such listing makes `/matches` return 500 for the whole category nearby — bound every listing number with `Field(gt/ge/le)` plus `min_hours <= max_hours`; skip candidates whose quote raises; add a regression test (9d28a0e)
- [x] P-2 [infra] H-2: the deploy job runs `npm ci` while holding AdministratorAccess credentials — build the web app in a job without AWS credentials (use `--ignore-scripts` where possible), and give the deploy role least privilege (a separate S3 and invalidation role for the web upload) (ffb2990)
- [x] P-3 [backend] H-3: staff powers need only a password (no MFA) — a staff pool or client with `mfa_configuration = "ON"`; `require_admin` checks the staff client id (backend, uncommitted: 403 mfa_required; web sign-in with TOTP is P-4)
- [x] P-4 [web] H-3: the sign-in flow cannot answer `SOFTWARE_TOKEN_MFA` — handle the challenge (`RespondToAuthChallenge`) and TOTP setup — code step for SOFTWARE_TOKEN_MFA; /admin runs TOTP setup on `mfa_required` (otpauth link + key, no QR library). Not verifiable against cognito-local
- [ ] P-5 [app] M-1: the Capacitor shells run without a CSP while holding the refresh token — emit the CSP as a meta tag in native builds; finish U-17; write an ADR that corrects ADR 0012
- [x] P-6 [backend] M-2: `reporterEmail`, `ownerName` and `ownerBusiness` travel in events into the two-year analytics lake — take personal data out of event payloads (consumers fetch it by id) or filter it in Firehose; correct `docs/analytics.md` (backend, uncommitted: Firehose allowlist transform; events between services keep what they need)
- [x] P-7 [backend] M-3: anonymous reports can hit the 20-per-target cap and turn genuine reports away, and send mail to unverified addresses — stop rejecting reports on the per-target cap (merge duplicates); confirm the email or require a CAPTCHA before any anonymous report or mail (backend, uncommitted: separate anonymous and member caps; receipt mail kept (Art. 16(4)), bounded)
- [x] P-8 [infra] M-4: prod has no protection against credential stuffing or breached passwords (threat protection off, no WAF on Cognito) — turn on threat protection (ENFORCED, block compromised credentials) and add a WAF association on the user pool; un-tick U-15's breached-password claim (40fbc5f)
- [ ] P-9 [infra] M-5: the notifications role has `sns:Publish` on `*`, so it can forge domain events — scope it to platform endpoints and add a publisher allow-list policy on the events topic
- [x] P-10 [backend] M-5: one `INTERNAL_TOKEN` is shared by all services — use per-caller credentials (a token per pair, or SigV4/mTLS) and check the caller on each `/internal` route
- [ ] P-11 [infra] M-6: service-to-service and ALB-to-gateway traffic is plain HTTP, and the database uses `ssl=require` — Service Connect TLS or an HTTPS target group; `ssl=verify-full` with the RDS CA bundle
- [x] P-12 [backend] M-7: no per-user limits on messages (push flooding), exports or sign-out-everywhere — per-`sub` limits (Postgres or DynamoDB counters); messages only in live booking states (backend, uncommitted: messages 30/10 min per booking, exports 5/day, sign-out-everywhere 5/h)
- [ ] P-13 [legal] G-3: no breach-response procedure (GDPR 72 h, PIPEDA record and report, Law 25 incident register, US state deadlines) — a runbook section with the notification matrix, templates and an incident register
- [ ] P-14 [infra] G-3: no CloudTrail, GuardDuty or Security Hub in Terraform — an organisation CloudTrail with log validation, GuardDuty, Security Hub, and alarms on secret and snapshot access
- [ ] P-15 [legal] G-1: the English privacy policy omits messages, photos, reports, identity checks and push, and has no CCPA/CPRA, PIPEDA/Law 25 or UK sections — match the German policy; add per-market sections; notice at collection; "we do not sell or share"
- [ ] P-16 [web] G-1: the two languages of the policy drift apart — render both from one list of categories and recipients, with a test that fails on a mismatch
- [ ] P-17 [legal] G-2: identity checks are biometric and government-ID data (GDPR Art. 9, CPRA sensitive data, BIPA, CUBI, Québec's CAI declaration) — explicit consent, a published retention schedule, the CAI declaration, and Stripe's role confirmed in the DPA
- [x] P-18 [web] G-2: nothing records consent before `verifyIdentity` — a consent screen, with the consent stored against the verification session — web: explicit consent checkbox before the check; storing the consent against the verification is backend work, open (backend part, uncommitted: consent: true required, time and version stored) (f303350 server, f22f143 web)
- [ ] P-19 [legal] G-5: US and Canadian data sits in Frankfurt, and EU data goes to the US (CloudFront and WAF, APNs and FCM, Stripe) with no documented safeguards — an ADR on where each market's data lives; a Law 25 s. 17 transfer PIA; transfer impact assessments; name the DPF or SCCs in the policy
- [ ] P-20 [infra] G-5: WAF sampled requests keep request headers, including bearer tokens, in us-east-1 — turn off `sampled_requests_enabled` on rules that see authenticated traffic, or accept this in writing
- [ ] P-21 [legal] G-4: no Law 25 or PIPEDA privacy officer, no UK or Swiss representative, no DPO assessment — appoint them and publish them (`VITE_LEGAL_PRIVACY_OFFICER`)
- [x] P-22 [backend] L-1: tampered cursors and NaN/Infinity numbers give 500s — a typed or HMAC-signed cursor; `allow_inf_nan=False` on `CamelModel`
- [x] P-23 [backend] G-6: deleting an account leaves the Cognito user (and its email) behind when the app does not call `DeleteUser` — `AdminDeleteUser` on `PROFILE_DELETED`; drop names from booking snapshots or say why they are kept
- [x] P-24 [backend] L-2: access tokens work for up to 60 minutes after sign-out-everywhere or deletion — 15-minute access tokens, or a per-`sub` "not before" or `origin_jti` revocation check (backend, uncommitted: 15-min tokens, per-service revoked_sessions; matching and gateway rely on the 15 min)
- [x] P-25 [infra] L-3: the Cognito client lets users write any attribute and change their email without verification — `write_attributes = ["locale"]`; `attributes_require_verification_before_update = ["email"]` (40fbc5f)
- [ ] P-26 [web] L-4: Google Fonts load before sign-in, the CSP has `'unsafe-inline'` and Unsplash, and API and media responses have no CSP — self-host fonts; tighten the CSP; add Permissions-Policy and COOP; add `default-src 'none'` to API answers — fonts self-hosted; CSP still lists fonts.googleapis.com/gstatic.com in `infra/platform/edge.tf` and has `unsafe-inline`: open
- [x] P-27 [backend] L-5: evidence photos are public CloudFront URLs — a private prefix served through an authorized booking route, or signed URLs (backend, uncommitted: web must upload with ?purpose=evidence)
- [x] P-28 [backend] L-6: the Identity webhook does not match `session_id`, and nothing checks the verified name against the profile — require the session id to match; store and compare the verified name (backend, uncommitted: session id must match; verified-name comparison not done)
- [ ] P-29 [legal] G-7: no CCPA/CPRA request process (authorised agents, verification, 45 days, 24-month records); which state laws apply is unknown — a privacy-request workflow and register; counsel to confirm which state laws apply; recheck GPC if an ad or analytics SDK is ever added
- [ ] P-30 [legal] G-8: G-B3 does not cover the Law 25 PIAs, the CPRA risk assessments or audits, or ICO registration — extend G-B3
- [ ] P-31 [app] L-7: the FileProvider exposes external storage root, release builds are unminified, `access origin="*"` remains, and the associated domain is a placeholder — keep only `cache-path`; enable R8; remove the wildcard; set the real `applinks:` domain
- [ ] P-32 [infra] L-8: no dependency or image scanning, actions pinned by tag, ECS Exec without an audit log — `pip-audit`/`npm audit`/ECR scanning in CI; SHA pins; ECS Exec logging, or Exec off in prod
- [x] P-33 [backend] L-9: re-registering a push token takes it from another user — rebind only with proof of the previous install (backend, uncommitted: installId required to move a token)
- [x] P-34 [backend] L-10: `/api/client-errors` has a forgeable limit key and logs free text — key on CloudFront's viewer address; remove personal data before logging (backend, uncommitted: X-Forwarded-For hop counting (CloudFront-Viewer-Address is not forwarded by the managed origin policy))

## Markets (M) — GOAL 16, from docs/research/2026-09-multi-market.md and ADR 0013

- [ ] M-1 [legal/business] Entity plan: Cappy GmbH serves the EEA, CH and UK. Decide whether and when a US corporation (and later a Canadian subsidiary) with its own Stripe platform serves North America, or whether North America starts on the DE platform via cross-border payouts — https://docs.stripe.com/connect/cross-border-payouts
- [ ] M-2 [backend] `markets.json` in `cappy_common` (currency, cell, entity, stripePlatform, languages, units, tax regime, reporting, consumer law, fee, min age, status), with a loader, a test that every market is complete, and a copy in the web build — ADR 0013
- [x] M-3 [backend] `Money(amount_minor, currency)` in models, quotes, offers and events; no `currency="eur"` (`booking/routes.py:180`) and no `"eur"` column default (`booking/tables.py:50`); minor-unit exponent from ISO 4217 — https://www.iso.org/iso-4217-currency-codes.html
- [x] M-4 [web] `formatMoney(amount, currency)` replaces `formatEur`; the money input takes symbol and separators from `Intl.NumberFormat.formatToParts`; no hard-coded € (`ui.tsx:386`) — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts — `formatMoney(minor, currency, locale)` with the currency from the data (EUR fallback until M-3), money input symbol from Intl, `formatDistance`/`formatRadius` in mi for US/GB, km elsewhere; locale keeps the device region (en-US, en-CA, fr-CA…)
- [ ] M-5 [backend] Listings get `country`, `subdivision`, `postal_code`, `time_zone` and a PostGIS `geography(Point)` with a GiST index; search by `ST_DWithin`; districts become labels; migration from districts to points — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html
- [ ] M-6 [backend] Public coordinates snapped to about 500 m; the exact point only in the handover after acceptance (as the address is today) — https://www.airbnb.com/help/article/2874
- [ ] M-7 [backend]+[infra] Geocoding and autocomplete through Amazon Location Service in each cell; store only `IntendedUse=Storage` results, never autocomplete results — https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html
- [ ] M-8 [web] Structured address form per country from the libaddressinput metadata, replacing the free-text field and the Berlin placeholder (`AddListing.tsx:768`) — https://github.com/google/libaddressinput
- [x] M-9 [backend] Stripe accounts created with the owner's `country` on the market's platform (`payments/provider.py:171`); full service agreement; separate charges and transfers stay without `on_behalf_of` — https://docs.stripe.com/connect/service-agreement-types
- [ ] M-10 [backend] A Stripe client per `stripePlatform`; secrets per cell; webhooks per platform — https://docs.stripe.com/connect/charges
- [ ] M-11 [legal/business] VAT on the fee per owner: domestic, reverse charge (EU B2B), OSS (EU B2C), UK VAT (no threshold for non-established), Swiss MWST (CHF 100k worldwide), GST/HST and QST — https://europa.eu/youreurope/business/taxation/vat/one-stop-shop/index_en.htm
- [ ] M-12 [backend] The fee's tax becomes a decision per invoice line (rate, scheme, legal note), from Stripe Tax or a rules table; `VAT_BPS = 1900` goes (`payments/invoices.py:30`) — https://docs.stripe.com/tax/tax-for-marketplaces
- [ ] M-13 [backend] Invoice template and number series per issuing entity and language; issuer details per entity instead of one `LEGAL_*` set; dates in the entity's zone — https://taxation-customs.ec.europa.eu/taxation/vat/vat-directive/vat-invoicing-rules_en
- [ ] M-14 [backend] Seller tax data for reporting in every market: TIN, date of birth, address, and the OECD activity per category (rename `dac7`); reports via Stripe platform tax reporting (preview; not for PL) — https://docs.stripe.com/connect/platform-tax-reporting
- [ ] M-15 [web]+[backend] Times in the listing's time zone everywhere (web `timeZone` option, emails via Babel); show the zone when it differs from the device; no Europe/Berlin constants (`notifications/texts.py:128`, `invoices.py:33`, `fixtures.py:59`) — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat/DateTimeFormat
- [ ] M-16 [web] i18n: languages from a list, locale = language + region, ICU MessageFormat plurals, lazily loaded catalogues; remove every `lang() === 'de'` ternary — https://unicode-org.github.io/icu/userguide/format_parse/messages/
- [ ] M-17 [web]+[backend] French (fr-FR and fr-CA) catalogues for the app, emails, legal pages and invoices; a launch blocker for Québec (Charter s. 52.1, terms in French first) — https://www.legisquebec.gouv.qc.ca/fr/version/lc/c-11?code=se%3A52_1
- [ ] M-18 [web] Miles for US and GB users (radius presets and labels), km elsewhere; km stays on the wire — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/NumberFormat
- [ ] M-19 [web] Legal pages per regime: Impressum for DE/AT (and CH), a company page elsewhere; withdrawal right and button only where EU consumer law applies; UK CCR text; Québec CPA; US/CA cancellation-policy wording (`Legal.tsx`, `BookingDetail.tsx:679-694`) — https://www.legislation.gov.uk/uksi/2013/3134
- [ ] M-20 [legal/business] Terms per contracting entity: governing law, forum, US arbitration and class-action waiver, the Québec French version — https://www.legisquebec.gouv.qc.ca/en/document/cs/P-40.1
- [ ] M-21 [infra] The North America cell: `infra/envs/prod-na` in ca-central-1 using the same `infra/platform` module; `region` stops defaulting to eu-central-1; validated and applied to LocalStack only (GOAL 12) — https://docs.aws.amazon.com/general/latest/gr/location.html
- [ ] M-22 [web]+[app] The welcome screen asks for the country (pre-selected from the device locale); the app stores the cell and uses its API host and Cognito pool; sign-in can switch region — https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-multi-region.html
- [ ] M-23 [backend] Bookings carry `market` and `entity`; a booking whose listing is in another cell is refused with a clear error; cross-market bookings inside a cell work in the listing's currency — ADR 0013
- [ ] M-24 [legal/business] US sales tax: a nexus study per state and taxability by category (equipment rental, storage and space, vans and car-sharing); Stripe Tax or Avalara registration — https://www.streamlinedsalestax.org/for-businesses/marketplace-facilitator
- [ ] M-25 [backend]+[web] US/CA checkout shows prices before tax and adds tax by the listing's address at checkout; EU/UK/CH prices stay tax-inclusive (PAngV and EU price rules) — https://docs.stripe.com/tax/tax-for-marketplaces
- [ ] M-26 [backend] 1099-K: collect a TIN (W-9) from US owners through Stripe and decide who files (`controller.fees.payer`); thresholds > $20,000 and > 200 transactions — https://docs.stripe.com/connect/tax-reporting
- [ ] M-27 [legal/business] Canada: GST/HST and QST registration for Cappy's fee; whether the distribution-platform rules catch rentals; Part XX reporting (vans, space) — https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/digital-economy.html
- [ ] M-28 [web]+[backend] US privacy: a notice at collection, CCPA/state rights in the privacy policy, GPC honoured (analytics off, recorded), and a "Do Not Sell or Share" link only if anything is ever sold or shared — https://cppa.ca.gov/regulations/pdf/ccpa_statute_eff_20260101.pdf
- [ ] M-29 [legal/business] Québec Law 25: name the person in charge of personal information and publish the contact; PIAs for processors outside Québec (Stripe, SES if used from the US); an incident register — https://www.cai.gouv.qc.ca/protection-renseignements-personnels/sujets-et-domaines-dinteret/principaux-changements-loi-25
- [ ] M-30 [backend] Marketing consent records (when, which text, which channel) per CASL and CAN-SPAM; `List-Unsubscribe` plus one-click unsubscribe honoured at once; a postal address in marketing mail — https://crtc.gc.ca/eng/com500/faq500.htm
- [ ] M-31 [backend] SMS, if added: transactional only by default; marketing SMS needs separate written consent; STOP handled (TCPA) — https://law.justia.com/cases/federal/appellate-courts/ca11/24-10277/24-10277-2025-01-24.html
- [ ] M-32 [backend] Phone numbers stored as E.164 with `phonenumbers`; the chat masker uses `PhoneNumberMatcher` with the market as the default region, so NANP numbers are caught (`booking/messages.py:47`) — https://github.com/daviddrysdale/python-phonenumbers
- [ ] M-33 [backend] Business identity per country: VAT ID validation for EU (VIES), GB, CH (UID), CA (BN) and US (EIN format); error text per country (`catalog/routes.py:99-115`) — https://ec.europa.eu/taxation_customs/vies/
- [ ] M-34 [backend] Notifications: Babel for money and dates in the listing's zone and the reader's locale; catalogues for every supported language (`notifications/texts.py:104-150`) — https://babel.pocoo.org/en/latest/api/numbers.html
- [ ] M-35 [backend] Seed data for every launch cell (Berlin, Vienna, Zürich, Paris, London, New York, Toronto, Montréal) in local currency, units and time zone; tests run per market — ADR 0010
- [ ] M-36 [web] Accessibility to WCAG 2.2 AA (covers EAA, ADA practice and AODA), axe in CI, an accessibility statement per region — https://www.ada.gov/resources/web-guidance/
- [ ] M-37 [legal/business] Insurance or a damage guarantee per market (van cover differs by country and US state); what the app promises changes per market — https://help.turo.com/en_us/protection-plans-in-detail-france-guests-ry6y3o962
- [ ] M-38 [backend] Minimum age per market and category (21+ for vans where rental law or the insurer requires it) — ADR 0013
- [ ] M-39 [backend] Payout and settlement currencies: platform settlement accounts in GBP, CHF, USD and CAD; transfers in the booking currency; FX shown to owners — https://docs.stripe.com/connect/currencies
- [ ] M-40 [web] Show an approximate conversion into the reader's currency, clearly labelled, when a listing's currency differs; always charge in the listing's currency — https://www.vinted.com/help/1555-us-uk-international-sales
- [ ] M-41 [app] Store listings per language (fr-CA separate in App Store Connect), availability per launch country, and a privacy label per region — https://developer.apple.com/help/app-store-connect/reference/app-information/app-store-localizations/
- [ ] M-42 [legal/business] UK: VAT registration, UK platform reporting, a UK GDPR representative (Art. 27) if Cappy has no UK establishment, and the DUAA complaints procedure — https://www.gov.uk/government/publications/reporting-rules-for-digital-platforms/reporting-rules-for-digital-platforms
- [ ] M-43 [legal/business] Switzerland: MWST registration once CHF 100k worldwide turnover is crossed and there are Swiss supplies; a Swiss representative under the FADP if required — https://www.estv.admin.ch/de/mwst-anmeldung-plattformbesteuerung
- [ ] M-44 [backend] ViDA readiness: a "deemed supplier" flag per category × market, so accommodation-like categories can be taxed as the platform's own supply from 1 Jul 2028 if they are ever added — https://eur-lex.europa.eu/legal-content/EN/TXT/PDF/?uri=OJ%3AL_202500518
- [ ] M-45 [infra] Per-cell observability and CD: the same images deployed to both cells in turn, dashboards per cell, and a cell label on every log line — ADR 0008

## Data rights (D) — from docs/DATA.md §5.5

Deletion (GDPR Art. 17, CPRA, PIPEDA/Law 25), except what law requires kept:
- [x] D-1 [backend] Deleting an account removes the person's photos: S3 objects and `media` rows (`catalog/repository.py` `forget`)
- [x] D-2 [backend] Deleted listings lose title, blurb, instructions (door codes), photos and spec, not only the address
- [x] D-3 [backend] Reports: reporter id, email and details redacted on deletion and after a retention period (DSA records: keep the decision, not the reporter); included in the reporter's export
- [x] D-4 [backend] Idempotency responses expire (24 h) and are deleted with the account (`cappy_common/idempotency.py`)
- [x] D-5 [backend] Booking snapshots: owner name and business, hand-over address and instructions, outcome notes, decline reasons, evidence photos and notes redacted on deletion (the booking row itself stays for accounting)
- [x] D-6 [backend] Stripe Identity: redact the verification session (`POST /v1/identity/verification_sessions/{id}/redact`) on deletion
- [x] D-7 [backend] Push: delete the SNS platform endpoint on unregister, sign-out-everywhere and deletion
- [x] D-8 [backend] Analytics lake: add `outcome.note`, moderation `statement` and `person_flagged.details` to P-6's list; a purge path for a person's events or keep only pseudonymous ids
- [x] D-9 [infra]+[docs] SES suppression list and invoice retention: document the legal basis; a job that purges invoices after the 10-year period
- [x] D-10 [backend] Export completeness: Cognito email and locale; reports filed; moderation decisions about the person; reviews about them; photo files (links); evidence notes; blocks; verified/suspended flags; card fingerprint; invoice recipient fields; refunds and charges; push devices
- [x] D-11 [backend] A test that walks every table with a person-id column and fails if deletion or export ignores it (catches the next gap)

Found alongside:
- [x] D-12 [backend] Dead code: events `booking.requested`, `booking.created` never produced; `/internal/people/{p}/bookings` and catalog `/internal/owners/{id}` have no caller — remove or use
- [x] D-13 [backend] A test that Terraform subscriptions (`data.tf`), `local/bootstrap.py` and each service's handlers agree
- [x] D-14 [infra] An alarm on outbox rows set aside after 20 attempts (today only a log line)
- [x] D-15 [docs] ADR 0003 and `events.py` docstring: 12 receives before the DLQ, not 5
- [ ] T-35c [infra] Per-journey burn-rate alarms (slo.md), queue-age thresholds matching the SLIs
- [ ] M-46 [infra] Second cell in one account: names include the cell (`cappy-<cell>-<env>`), `var.env` allows it; deploy.yml region and ECR per cell; CSP `connect-src` per cell's Cognito

## Provider seams (F) — from docs/FEATURES.md "No seam today"

So that a feature can move to another third party by adding an adapter, not by editing callers:
- [x] F-1 [backend]+[web] Identity verification: an `IdentityProvider` separate from the payment `Provider` (start session, parse webhook → neutral `verified|failed|needs_input`, redact), the web modal chosen by `/payments/config` (today Stripe Identity inside the payment provider, `Listing.tsx` calls Stripe.js)
- [x] F-2 [web] Auth: an `AuthProvider` object behind `web/src/data/auth.ts`'s exports (today all Cognito) (web, uncommitted — web/src/data/cognito.ts)
- [x] F-3 [backend]+[web] Staff role claim from settings (`STAFF_CLAIM`, `STAFF_VALUE`), not `cognito:groups` hard-coded
- [x] F-4 [backend] `Cdn.purge` interface for take-downs (today CloudFront called directly in `catalog/moderation.py`)
- [ ] F-5 [backend] `SearchIndex` protocol fed by `listing.changed` (today the query sits in `catalog/repository.py`)
- [ ] F-6 [backend] `Geocoder` interface (with M-5, M-7)
- [ ] F-7 [backend] `tax_for(owner, market, fee)` per invoice line (with M-12)
- [ ] F-8 [backend] Payment webhooks parsed into neutral events inside the provider (today `payments/routes.py` handles Stripe-shaped events)
- [ ] F-9 [web] The card form chosen by `/payments/config.provider` (today Stripe's Payment Element only)
- [x] F-10 [backend] Profile `verified` set from a successful ID check (today only seed data sets it; U-32)

## Flow bugs (FL) — from docs/FLOWS.md §23

- [x] FL-1 [web] A retry after a 503 from booking creation must reuse the Idempotency-Key (`Listing.tsx:209` makes a new one after any error; the retry then collides with the person's own `awaiting_payment` booking for 30 min). New key only after a definite 4xx — `useAttemptKey` (domain/attempt.ts, `npm run check:attempt`): key kept on 5xx/timeout/offline, new after success, a 4xx or a changed body; used by bookings, listings, messages, ratings, evidence, reports
- [x] FL-2 [backend] Notify both sides of `payment_failed`, `disputed` (owner learns of a dispute), and `active` where useful (`notifications/handlers.py`)
- [x] FL-3 [web]+[backend] Messages email toggle: either email messages (digest) or remove the toggle and the "everything also arrives by email" line
- [x] FL-4 [web] A held listing is announced as waiting for review, not "live"; an edit that re-holds says so
- [x] FL-5 [web] Admin console: approve held listings (`POST /admin/listings/{id}/approve`)
- [x] FL-6 [backend] The owner can open their own held listing (`catalog/routes.py` listing detail)
- [x] FL-7 [backend]+[web] Message and review reports: "remove the message/review" as an action; "suspend" resolves the author, not the listing owner (`moderation.py _affected_owner`) (web, uncommitted — web part; `remove_content` needs the backend)
- [x] FL-8 [backend]+[web] A request cancelled before capture shows "the hold is released", not "refunded" (`cancellation.py` refund amount 0 when nothing was charged) (web, uncommitted — web part; relies on the backend leaving refundAmount out when nothing was captured)
- [x] FL-9 [backend] Decline reason distinguishes a staff take-down from the owner removing the listing
- [x] FL-10 [web] The report form reachable signed out (`/legal/report`, DSA Art. 16) with a target reference, matching `Legal.tsx`
- [x] FL-11 [backend]+[web] Deletion that fails half-way: `upsert_profile` must not resurrect a deleted profile; the web retries Cognito `DeleteUser` and never lands in onboarding (web, uncommitted — web part)
- [x] FL-12 [web] Account deletion copy matches what is deleted (photos: D-1) (web, uncommitted — copy no longer promises photo deletion (D-1))
- [x] FL-13 [app] Push re-registers for the new account after sign-out/sign-in without restart (`native.ts:91`)
- [x] FL-14 [web] Starting offline with a stored session shows the app (cached) and refreshes when the network returns, not the sign-in screen
- [x] FL-15 [backend] The owner never sees `awaiting_payment` or `payment_failed` bookings
- [x] FL-16 [web] `payNow` does not show the card form again between Stripe's confirmation and the webhook (poll the booking)
- [x] FL-17 [web] PushPrime states the real answer deadline (min(24 h, window start)) — says "before the request lapses" (24 h at most, sooner if the booked time starts first)
- [x] FL-18 [backend] Messages refused on closed bookings (cancelled, declined, expired, payment_failed; completed after the review window)
- [x] FL-19 [app] Payment `return_url` for redirect methods in the shells is a universal/app link on Cappy's domain (with U-7)
- [x] FL-20 [docs] ADR 0012: refresh token in Capacitor Preferences (Keychain is U-17), push built — a dated correction
- [x] FL-21 [app] Release entitlements: real associated domain, `aps-environment` production in the release configuration (web, uncommitted — Release signs with App.release.entitlements (production); domain from CAPPY_DOMAIN)
