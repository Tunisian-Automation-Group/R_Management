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

### Batch M-2 (markets) and the day-2 leftovers, backend shipped, web to build

- `GET /api/app-config` gains `markets: {CC: {currency, languages, units ("metric"|"imperial"),
  emergencyNumber, status ("live"|"planned"), minimumAge}}` for every country Cappy serves
  (EEA, CH, GB, US, CA). Live today: DE, AT, CH. Nothing about entities, Stripe or tax.
- `PUT /me` with a `country` whose market is not live: 422 `market_not_live`; unknown: 422
  `market_unknown`. The age message names the market's minimum age (19 in CA once live).
- `POST /listings` / `PUT /listings/{id}`: `currency` may be left out and becomes the owner's
  market currency (a Swiss owner gets CHF); any other currency is 422 `currency_not_in_market`.
  The price cap and the held-listing and ID-check thresholds are per market, in its currency.
- `POST /payments/connect/onboarding` `{country}`: only live markets (else 422 `country_unsupported`).
- Currency is ISO 4217 **uppercase everywhere**: listings, quotes, bookings, payments,
  cancellation quotes, invoices (only the Stripe adapter lowercases). Stored rows migrated.
- After a staff "Refund the buyer" the booking carries `refundAmount` = the full amount.
- Data export: payments `identity.consentAt` / `consentVersion`; booking `evidence[].photos` are
  links signed for 24 h (`/api/bookings/{b}/evidence/{e}/{i}?exp&sig`), not `evidence:` refs;
  catalog `moderationDecisionsAboutMe` also covers decisions on the person's messages and reviews.

### Batch H (response metrics, schedules, ranking, places), backend shipped, web to build

- Owner answers: `responseMins` (median minutes to accept or decline) and `responseRate` (0–1, answered before
  lapsing) are measured over 90 days and `null` under 3 requests (H-1). The invented default of 60 is gone:
  never show a response time that is `null`.
- `GET /api/ranking` (public, cached 5 min): `{signals: [{key, weight, description}], textSearch: "newest first"}`,
  heaviest first; the ranking page renders it (H-2).
- A listing may carry `availability: {weekly: [{day: 1..7 (ISO, Mon=1), start: "HH:MM", end: "HH:MM"|"24:00"}],
  timeZone}` on `POST /listings` and `PUT /listings/{id}` (H-4). The server keeps windows 8 weeks ahead in that
  time zone; `created.slots` already holds them. An edit without the key keeps the schedule; `availability: null`
  removes it (and the future windows it made). Hand-made windows (`POST /listings/{id}/slots`) still work and are
  never overlapped. 422 for a schedule ending before it starts or an unknown time zone.
- New notice `listing_idle` (bell, push, email; category bookings): a live listing with no free window in the
  next 7 days, at most weekly; it links to `/earn/edit/{id}`.
- Places (M-5, M-6): listings may carry `location: {lat, lng}`, `country` (ISO 3166-1) and `postalCode`. Public
  answers give `location` snapped to a ~500 m grid and no `postalCode`; the owner's own views and the hand-over
  (after acceptance: `booking.handover.location`, `.postalCode`) give the exact ones. The point must be within
  30 km of the listing's `district` (422 `location_outside_district`); districts stay the name shown and the
  search bucket. Distances (`distanceKm`, reasons) are measured from the snapped point.
- Local only: `MIN_LEAD_MINUTES=5` (a booking can start 5 minutes out), `make confirm EMAIL=… [ADMIN=1]`,
  `make codes` prints address and code, and a second demo host `host2@demo.cappy.local` (three listings: instant
  book, a van run, a studio held for review).

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
- [ ] S-12 [backend]+[web] Late return: "extend booking" when the next window is free. Otherwise, after 30 min grace, the normal rate for the extra time plus a capped late fee, reported by the owner within 24 h — https://getaround.com/help/articles/b075d5c22795 — backend done (uncommitted): late-return claims, staff confirm, extend; web open — web UI built (case view, resolve with reason and four eyes, audit paged, offers, late return, extend)
- [x] S-13 [backend]+[web] Structured Art. 17 statement: restriction, facts, automated yes/no, legal ground or T&C clause, redress text (reply to contest, courts). A good-faith checkbox in the report form (Art. 16(2)(d)) — https://dsa-library.com/article/17/ · https://dsa-library.com/article/16/ — **backend done (uncommitted)**, web and the rest open
- [ ] S-14 [app] Android 16 edge-to-edge check at targetSdk 36: Capacitor SystemBars / insets for the dock, sheets and toasts, with gesture and 3-button navigation on API 35 and 36 (with U-26) — https://developer.android.com/about/versions/16/behavior-changes-16 — partly: side safe-area insets for body, sticky bar, sheets and toasts (landscape notch); needs a check on a real Android 15/16 device
- [x] S-15 [web] Route-level code splitting (`React.lazy` for Admin, AddListing, Earn, Profile, Legal). A CI budget of ≤170 KB gz for the entry chunk — https://web.dev/articles/performance-budgets-101 — entry chunk 217.8 → 144.5 kB gz; screens, PayStep and the DE/FR catalogues are lazy; `npm run check:size` budget 170 kB
- [x] S-16 [all] Review notes for 3.1.3(e) (physical services, card/Apple Pay, no IAP) and 4.2 (the native features list), added to U-1 — https://developer.apple.com/app-store/review/guidelines/ (073ccf1, docs/app-review.md)
- [x] S-17 [backend] Ban-evasion linkage: store the Stripe card fingerprint and the Connect bank fingerprint. A new account sharing one with a suspended account is held for review — https://docs.stripe.com/api/cards/object#card_object-fingerprint — cards only: the Connect bank-account fingerprint is left for when payouts read the external account
- [x] S-18 [backend] Owner cancellation consequences: counted per owner, shown as a rate on the profile, a ranking signal (and the ranking page updated), repeat cancellations queued for staff. A fee **(counsel)** — https://www.airbnb.com/help/article/990 — the fee waits for counsel; the ranking-page text is for web — web: rate on the listing, ranking page updated
- [ ] S-19 [legal/business] Withdrawal right by category: vehicle rental and fixed-date leisure services are exempt (§ 312g(2) Nr. 9 BGB). The checkout text and button follow the category **(counsel, G-B2)** — https://www.gesetze-im-internet.de/bgb/__312g.html
- [ ] S-20 [backend] Duplicate-listing detection: a perceptual hash (pHash) per photo. Matches across different owners go to the held queue (G-9) — https://github.com/JohannesBuchner/imagehash
- [ ] S-21 [backend]+[web] Dispute flow between the parties: a 72 h response window, an offer or counter-offer for a partial refund, auto-escalation to staff after the deadline — https://www.airbnb.com/help/article/767 — backend done (uncommitted): offers, accept, 72 h escalation; web open — web UI built (case view, resolve with reason and four eyes, audit paged, offers, late return, extend)
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
- [x] P-11 [infra] M-6: service-to-service and ALB-to-gateway traffic is plain HTTP, and the database uses `ssl=require` — Service Connect TLS or an HTTPS target group; `ssl=verify-full` with the RDS CA bundle (backend, uncommitted): Service Connect TLS with a private CA, HTTPS ALB→gateway, DB verify-full; validated only
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
- [x] P-32 [infra] L-8: no dependency or image scanning, actions pinned by tag, ECS Exec without an audit log — `pip-audit`/`npm audit`/ECR scanning in CI; SHA pins; ECS Exec logging, or Exec off in prod (backend, uncommitted): pip-audit and npm audit in CI, ECR scan on push, Dependabot for actions/uv/npm/docker (SHAs not resolvable offline), ECS Exec audit log
- [x] P-33 [backend] L-9: re-registering a push token takes it from another user — rebind only with proof of the previous install (backend, uncommitted: installId required to move a token)
- [x] P-34 [backend] L-10: `/api/client-errors` has a forgeable limit key and logs free text — key on CloudFront's viewer address; remove personal data before logging (backend, uncommitted: X-Forwarded-For hop counting (CloudFront-Viewer-Address is not forwarded by the managed origin policy))

## Markets (M) — GOAL 16, from docs/research/2026-09-multi-market.md and ADR 0013

- [ ] M-1 [legal/business] Entity plan: Cappy GmbH serves the EEA, CH and UK. Decide whether and when a US corporation (and later a Canadian subsidiary) with its own Stripe platform serves North America, or whether North America starts on the DE platform via cross-border payouts — https://docs.stripe.com/connect/cross-border-payouts
- [x] M-2 [backend] `markets.json` in `cappy_common` (currency, cell, entity, stripePlatform, languages, units, tax regime, reporting, consumer law, fee, min age, status), with a loader, a test that every market is complete, and a copy in the web build — ADR 0013 (backend: markets.json + loader + test; the web reads the public part from app-config instead of a copy)
- [x] M-3 [backend] `Money(amount_minor, currency)` in models, quotes, offers and events; no `currency="eur"` (`booking/routes.py:180`) and no `"eur"` column default (`booking/tables.py:50`); minor-unit exponent from ISO 4217 — https://www.iso.org/iso-4217-currency-codes.html
- [x] M-4 [web] `formatMoney(amount, currency)` replaces `formatEur`; the money input takes symbol and separators from `Intl.NumberFormat.formatToParts`; no hard-coded € (`ui.tsx:386`) — https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat/formatToParts — `formatMoney(minor, currency, locale)` with the currency from the data (EUR fallback until M-3), money input symbol from Intl, `formatDistance`/`formatRadius` in mi for US/GB, km elsewhere; locale keeps the device region (en-US, en-CA, fr-CA…)
- [ ] M-5 [backend] Listings get `country`, `subdivision`, `postal_code`, `time_zone` and a PostGIS `geography(Point)` with a GiST index; search by `ST_DWithin`; districts become labels; migration from districts to points — https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Appendix.PostgreSQL.CommonDBATasks.PostGIS.html — first step: exact point, country, postal code; districts as buckets and labels (no PostGIS locally; point index when a market has no districts) — web part (uncommitted): the form sends location (district centre), country, postal code
- [x] M-6 [backend] Public coordinates snapped to about 500 m; the exact point only in the handover after acceptance (as the address is today) — https://www.airbnb.com/help/article/2874 — done: 500 m grid in public answers and distances; exact point in the hand-over
- [ ] M-7 [backend]+[infra] Geocoding and autocomplete through Amazon Location Service in each cell; store only `IntendedUse=Storage` results, never autocomplete results — https://docs.aws.amazon.com/location/latest/developerguide/places-intended-use.html
- [ ] M-8 [web] Structured address form per country from the libaddressinput metadata, replacing the free-text field and the Berlin placeholder (`AddListing.tsx:768`) — https://github.com/google/libaddressinput — not yet: the address is still one free-text line
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
- [x] T-35c [infra] Per-journey burn-rate alarms (slo.md), queue-age thresholds matching the SLIs (backend, uncommitted): per-journey burn alarms from gateway access lines; queue-age alarms at the SLIs
- [x] M-46 [infra] Second cell in one account: names include the cell (`cappy-<cell>-<env>`), `var.env` allows it; deploy.yml region and ECR per cell; CSP `connect-src` per cell's Cognito (backend, uncommitted): names cappy-<cell>-<env>, var.cell, region and state key per cell in deploy.yml; CSP connect-src already per region

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

## Hosts, search, support, fees (H) — from docs/research/2026-09-hosts-search-support-fees.md

- [x] H-1 [backend]+[web] Measure the owner's response time and rate from real requests (median minutes from `requested` to accept/decline over 90 days, share answered before expiry); hide "Usually answers in…" until an owner has 3 answered requests; stop writing the constant 60 — https://support.peerspace.com/en/articles/11380453-host-performance-guide — backend done: measured over 90 days, null under 3 requests; web to show only non-null — web: hidden while null (web, uncommitted)
- [x] H-2 [web]+[legal/business] Rewrite the ranking page from `match.py:54`: each parameter with its weight, the trust formula, free-text order, the Spotlight rail, the hold and payability filters; a test that fails when `W` changes without the page — https://eur-lex.europa.eu/eli/reg/2019/1150/oj/eng — backend half done: GET /api/ranking from W, a test pins it; the page is the web half — web: rendered from GET /api/ranking in EN/DE/FR (web, uncommitted)
- [x] H-3 [web] A "How results are ordered" link on the Browse and search results themselves (phone and desktop), not only in the desktop footer — https://www.gesetze-im-internet.de/uwg_2004/__5b.html — (web, uncommitted)
- [x] H-4 [backend]+[web] Recurring availability (weekly hours plus exceptions) stored on the listing; the server generates bookable windows ahead; owners warned by email when a listing has no free window in the next 7 days — https://getaround.com/help/articles/0dd5b5d9ef5a — backend done: weekly schedule, 8 weeks rolled daily, DST-tested, idle notice weekly (EN/DE/FR); exceptions (holidays) not yet — web: presets and a weekly editor send `availability`; stop repeating (web, uncommitted)
- [ ] H-5 [web] Help centre per market: emergency number from the market (112, 999, 911), French catalogue, owner and renter sections — https://help.turo.com/
- [ ] H-6 [backend]+[web] Staff refunds: `refund_amount` (partial), reason code, free note, an approval limit per staff role; the owner's share adjusted and invoiced accordingly — https://www.airbnb.com/help/article/767 — backend done (uncommitted): partial refunds, reason codes, per-market role limits, four eyes; web open — web UI built (case view, resolve with reason and four eyes, audit paged, offers, late return, extend)
- [x] H-7 [backend] One staff audit log across services: dispute resolutions (with reason), refunds, approvals, suspensions, and staff reads of evidence and messages; filters by actor and target, cursor pagination — https://www.iso.org/standard/27001 (backend, uncommitted): one log in catalog fed by staff.action; GET /admin/audit?target&actor&cursor — web UI built (case view, resolve with reason and four eyes, audit paged, offers, late return, extend)
- [ ] H-8 [backend] Search events (`search.performed`: query or requirement, filters, result count, sort; `search.clicked`, linked to a booking) into the analytics lake without personal data; a weekly zero-result query in `docs/analytics.md` — https://www.algolia.com/doc/guides/search-analytics/concepts/metrics/
- [ ] H-9 [backend]+[web] Staff case view: disputed bookings list with age, booking lookup by id or member, one screen with timeline, messages, evidence and payment state — https://support.zendesk.com/hc/en-us/articles/4408844187034 — backend done (uncommitted): case list and lookup, case view; web open — web UI built (case view, resolve with reason and four eyes, audit paged, offers, late return, extend)
- [ ] H-10 [web]+[backend] Contact support form (category, booking or listing attached) that creates a case with an id and confirms by email; `mailto:` only as fallback — https://help.turo.com/
- [ ] H-11 [web] Photo rules: at least 3 photos to publish (1 for batch services **(decide)**), a shot list per category, aspect guidance, and a warning on screenshots or very small images — https://support.peerspace.com/en/articles/10119356-photo-tips-and-requirements-for-listings
- [ ] H-12 [backend]+[web] Listing-completeness checklist on Earn (photos, description length, rules, instructions, availability ahead, instant book) with a score the ranking can use later — https://support.peerspace.com/en/articles/10119526-how-sort-order-works-on-peerspace-and-how-to-make-your-space-stand-out
- [ ] H-13 [backend]+[web] iCal: an `.ics` export per listing (secret URL, rotatable) and an import that blocks windows from other calendars, polled every 30 min — https://www.airbnb.com/help/article/99
- [ ] H-14 [backend]+[web] Saved searches with alerts: save a requirement (category, district, radius, hours), push/email when a new window matches, one-tap stop, capped per day — https://www.vinted.com/help
- [ ] H-15 [backend] Ranking inputs: response speed and acceptance rate (from H-1) into trust; requests that lapse unanswered count against the owner; the page updated in the same change (H-2) — https://getaround.com/help/articles/0dd5b5d9ef5a
- [ ] H-16 [web]+[legal/business] VAT-registered business owners: the form says the price must include VAT for consumers, and the listing says "incl. VAT" for them **(counsel)** — https://www.gesetze-im-internet.de/pangv_2022/__3.html
- [ ] H-17 [backend]+[web] Renter receipt per booking (supplier = owner, with trader details when a business; base, extras, discount, fee, tax, total), downloadable and linked from the confirmation email — https://www.gesetze-im-internet.de/uwg_2004/__5b.html
- [ ] H-18 [backend] Booking emails carry the same breakdown as the confirm sheet (total, fee, owner receives, refund if any) — https://skift.com/2025/04/21/airbnb-makes-total-price-display-standard
- [ ] H-19 [web] Deposits (with S-9): a separate line "Refundable hold" outside the price, the release rule and date, on the listing, confirm sheet and booking — https://docs.stripe.com/payments/place-a-hold-on-a-payment-method
- [ ] H-20 [web] Currency shown unambiguously across borders (`currencyDisplay: 'symbol'` with a region-aware fallback to "US$"/"CA$"/"CHF"), with a test per market pair — https://www.airbnb.com/help/article/1857
- [ ] H-21 [legal/business] US fee-law map: whether the FTC rule (lodging) touches storage or studio space; state all-in laws beyond California; Québec price display; deposits under each **(counsel)** — https://www.ftc.gov/business-guidance/resources/rule-unfair-or-deceptive-fees-frequently-asked-questions
- [ ] H-22 [infra] Status page outside AWS (Statuspage or Instatus), linked from the "not reachable" state, the help centre and the runbook's incident steps — https://www.atlassian.com/software/statuspage
- [ ] H-23 [legal/business] Support SLAs: first response 24 h, safety 1 h, dispute decision 5 working days; an ageing view in the console; the numbers in the help centre — https://www.airbnb.com/help/article/767
- [ ] H-24 [backend]+[web] Staff macros: saved statements per DSA ground and clause, and reply templates for common cases, editable by admins — https://support.zendesk.com/hc/en-us/articles/4408844187034
- [ ] H-25 [backend]+[web] Pricing hint on the form: the median and 25–75 % band of live listings in the same category and metro, shown only with ≥5 comparables, in the listing's currency — https://www.airbnb.com/help/article/474
- [ ] H-26 [backend] Free-text relevance: Postgres full-text search with per-language configs (`german`, `english`, `french`) plus trigram fallback, ranked by `ts_rank` then distance; the `SearchIndex` seam from FEATURES §4.2 — https://www.etsy.com/seller-handbook/article/how-etsy-search-works/375461474487
- [ ] H-27 [web]+[backend] Empty-result recovery computed from data: say which filter removed the most results and offer the nearest relaxation ("3 free 12 km further", "free from Thursday"); free text falls back to category suggestions — https://www.algolia.com/doc/guides/search-analytics/concepts/metrics/
- [ ] H-28 [web]+[backend] Flexible time search: "any weekday", "mornings", "± 2 days around" as requirement options in matching — https://www.airbnb.com/help/article/39
- [ ] H-29 [web] Owner's first-booking guide: what happens on the first request, the answer deadline, hand-over tips, shown once after publish and on the first request — https://www.airbnb.com/e/new-listing-promotion?locale=en
- [ ] H-30 [web] Owner performance card on Earn: response time, acceptance, cancellation rate, rating, each with the target and what it changes in ranking — https://support.peerspace.com/en/articles/11380453-host-performance-guide
- [ ] H-31 [backend]+[web] Host tier (after H-1, H-15): criteria like Superhost (rating, response, cancellations, completed bookings), checked quarterly over 12 months, a badge and a filter; criteria on the ranking page — https://www.airbnb.com/help/article/829
- [ ] H-32 [web] Quick replies for owners in the conversation (saved texts for access, parking, rules) — https://support.peerspace.com/en/articles/11380453-host-performance-guide
- [ ] H-33 [backend] A test that ranking and price are the same for any two members given the same request (no personalisation), and a line on the ranking page saying so — https://dsa-library.com/article/27/
- [ ] H-34 [web] Map search with pan-to-search and total-price pins, once listings have points (M-5, M-7) — https://www.airbnb.com/help/article/39
- [ ] H-35 [backend] Cold start: new listings get a bounded exploration slot in "best" results for their first 30 days, stated on the ranking page — https://arxiv.org/abs/1810.09591

## Guide findings (GD) — from writing docs/GUIDE.md

- [x] GD-1 [web] Rewrite `web/README.md`: signed-in only, the real scripts (`check:*`), `make up` from the root, what is stored on the device, EN/DE/FR, `applinks:$(CAPPY_DOMAIN)`, `/pay/*`; drop `VITE_CAPPY_USER` from `web/.env.example` (unused); the Login.tsx comment says local builds only — (web, uncommitted)
- [x] GD-2 [local] Fresh local accounts get no email: cognito-local leaves `email_verified` false on confirmation. A `make confirm EMAIL=…` target (verify the email, optionally `ADMIN=1` for the admin group), and `make codes` shows which email each code is for — done: make confirm, make codes with addresses
- [x] GD-3 [local] Testers wait two hours for no-show and dispute steps: local compose sets a short `MIN_LEAD_MINUTES` (and the other windows) so every flow can be walked in minutes, documented in GUIDE §A — done: MIN_LEAD_MINUTES=5 locally; deployed settings refuse <60, START_EARLY_MINUTES>60, AUTO_COMPLETE_AFTER_HOURS<24
- [x] GD-4 [local] Sign out everywhere cannot sign other devices out on cognito-local (no global sign-out; revocation compares `iat`): make local revocation also reject refreshes (a local-only refresh deny list), or say so in the guide — not fixable locally: cognito-local has no global sign-out and the web refreshes against it directly; documented — documented as a local-only limit in docs/runbook.md ("Local stack only")
- [x] GD-5 [local] The demo host owns one listing (l9) and the other ~70 seeded owners cannot sign in: a second demo host with a few listings (instant book on one, a held one, a van), so every host flow and the admin approval can be tested — done: host2@demo.cappy.local (DE: no Swiss place in the seed, so no CHF listing)

### Batch H-staff (disputes, staff tools, late returns), backend shipped, web to build

- **Resolve** (H-6): `POST /api/admin/bookings/{id}/resolve` `{outcome: "pay_owner"|"refund_buyer"|"partial", refundAmount? (partial: 0 < x < amount), reasonCode: damage|no_show|not_as_described|late_return|cleanliness|safety|goodwill|other, note}`, `Idempotency-Key` → **`{resolution, booking}`** (was a Booking). `resolution`: `{id, bookingId, outcome, refundAmount, currency, reasonCode, note, by, role: support|lead|parties, status: done|pending_approval|rejected, approvedBy?, createdAt, decidedAt?}`. Above the staff member's limit (markets.json `refund_limit_support`/`refund_limit_lead`, per market, minor units) → `pending_approval`, booking stays `disputed`. Errors: 409 `approval_pending`, 422 `invalid_refund`.
- **Approvals**: `GET /api/admin/resolutions?status=pending_approval` → `Resolution[]`; `POST /api/admin/resolutions/{id}/approve` `{note}` (Idempotency-Key) → `{resolution, booking}`; `/reject` `{note}` → `Resolution`. 403 `four_eyes` (your own), 403 `needs_lead`. Leads: Cognito group `admin-lead` (setting `STAFF_LEAD_VALUE`) on top of `admin`.
- **Money**: refund all → booking `cancelled`, `refundAmount` = amount; partial → booking **`completed` with `refundAmount`** set (payments refunds it and pays the owner their share of the rest); pay owner → `completed`, no `refundAmount`.
- **Case list** (H-9): `GET /api/admin/bookings?status=&member=<id or email>&booking=&claims=open&cursor=&limit=` → `Page<{id, status, title, requesterId, ownerId, amount, currency, windowStart, windowEnd, updatedAt, dispute?, pendingApproval, openClaims}>`, most recently changed first; `status=disputed` puts escalated ones first within a page.
- **Case view**: `GET /api/admin/bookings/{id}/case` → `{booking, requesterId, ownerId, timeline: [{fromStatus?, toStatus, by, at}], messages: [{id, senderId, body (as written), at, flagged}], evidence: Evidence[] (signed links), payment?: {bookingId, status, amount, ownerNet, currency, captured, refunded, paidOut, chargebackAt?, updatedAt}, dispute?, resolutions: Resolution[], claims: Claim[]}`. Reading it (and staff reading `/bookings/{id}/evidence`) is logged.
- **Audit log** (H-7): `GET /api/admin/audit?target=&actor=&cursor=&limit=` → **`Page<AuditEntry>`** (was a list): `{id, actorId, action, targetType, targetId, reportId?, statement, at, personId?, requestId?}`. Actions from booking: `resolve_dispute`, `propose_resolution`, `approve_resolution`, `reject_resolution`, `confirm_claim`, `reject_claim`, `read_case`, `read_evidence`.
- **Disputes between the parties** (S-21): `GET /api/bookings/{id}/dispute` → `{bookingId, openedBy, reason, openedAt, respondBy, escalatedAt?, offer?: {refundAmount, by, at}, currency, amount}` (404 when none); `POST /bookings/{id}/dispute/offer` `{refundAmount}` (0..amount) → `Dispute` (replaces the offer, `respondBy` = now + 72 h; the other side is notified, `dispute_offer`); `POST /bookings/{id}/dispute/accept` `{refundAmount}` (the amount on the table; Idempotency-Key) → `{resolution, booking}`. Errors: 403 `own_offer`, 409 `offer_changed`, 409 no offer. After `respondBy` with no agreement the dispute gets `escalatedAt` (staff).
- **Late return** (S-12): `POST /bookings/{id}/late-return` `{minutesLate, note?}` by the owner, status active/completed/disputed, within 24 h after the end → 201 `Claim` `{id, bookingId, kind: "late_return", by, minutesLate, amount, currency, note?, status: open|confirmed|rejected, createdAt, decidedBy?, decidedAt?, decisionNote?}`. Amount: extra time after 30 min grace at the listing's hourly rate (to the quarter hour) + one hour's rate as a fee, capped per market (`late_fee_cap`). Errors: 422 `within_grace`, 409 `claim_window`, 409 `claim_exists`. `GET /bookings/{id}/claims` for both parties; `POST /api/admin/claims/{id}/decide` `{decision: confirm|reject, note}`. Nothing is charged (S-9).
- **Extend** (S-12): `POST /bookings/{id}/extend` `{hours}` (≤ 24) by the renter while accepted/active and before the end, time bookings only, Idempotency-Key → 201 `{booking, payment?}` like `POST /bookings`: a new booking straight after, instant if the listing is instant book. Errors: 409 `not_extendable` (not on, or the time after is not open).
- **Listing time zone**: the booking snapshot has `listing.timeZone` (the listing's weekly-hours zone, else the market's main zone, markets.json `time_zone`); `booking.status_changed` carries `timeZone`.
- **Districts per country**: `PUT /me` and listings refuse a district outside the profile's / owner's country: 422 `district_not_in_country` with a `fields` entry for `district` (or `country`). The seed has AT (Wien, Graz, Linz, Salzburg, Innsbruck) and CH (Zürich, Genève, Basel, Bern, Lausanne) districts, and one CHF listing in Zürich (`ch-l1`, seeded owner `ch1`).

### Batch V4 (backend) — for the web

- **Field errors (V4-20):** every 422 from request validation, and some from
  the code, carry `error.fields: [{field, message}]`, where `field` is the
  camelCase path in the body (for example `business.vatId`,
  `business.legalName`, `district`). `error.message` is still one line for
  older clients: the first field's problem, or the code's sentence. A
  business profile without trader details gets one field, `business`.
- **An early hand-over (V4-3):** once a booking is `active`, the renter may
  open a dispute at once, whatever the clock says. Cancelling from `active`
  is refused (409): offer "Report a problem" instead of cancel on an active
  booking.
- **Invoice recipient (V4-7):** the invoice page names the recipient with an
  address: the trader's business address, else the one the payout provider
  verified. The list rows are unchanged (`description`, `title`,
  `serviceStart`, `serviceEnd`); format the dates from `serviceStart` and
  `serviceEnd` in the reader's locale, not from `description` (V4-8).
- **Hand-over (V4-9):** `booking.handover` is current while the booking is
  accepted or active: an address the owner adds later shows on the next read.
- **Notification times (V4-19):** 24 h in de, fr and European English; 12 h
  without a leading zero for en-US and en-CA. The server knows the region only
  if the app sends it: send the BCP 47 locale (`locale()`, for example
  `en-US`) as the Cognito `locale` attribute and first in `Accept-Language`.
- **Revocation (V4-24):** a token issued in the same second as a sign-out
  everywhere, or earlier, gets 401 `token_expired`. A sign-in within that
  same second is refused too; the next second works. Treat it like any other
  `token_expired`.

## Verification round 4 (V4)

Run by a separate verifier on the local stack, 2026-09-26 (09:20–10:10 CEST), with the demo buyer, host and staff, signed in only through the demo buttons. The web version was checked at 1400 px. The app version was checked in a 390×844 same-origin iframe (`resize_window` did not change the viewport); the Capacitor shells can't run here. Checked in EN (browser locale en-US), DE and FR. Severity order, most severe first.

- [x] V4-1 [web] French readers get the help centre and the legal pages in English. Repro: pick Français, open `/help` (every topic title: "Booking and paying", "Cancelling and refunds", … "Notifications"), `/help/paying`, `/help/safety`, `/legal/privacy`, `/legal/terms`, `/legal/withdrawal` (titles, the legal tab bar "Privacy Policy · Terms of Use · Right of withdrawal · How ranking works · Reporting content · Accessibility" and the body text), and the public `/account/delete`. Only the "operator details" banner and the chrome are French. DE is translated. Expected: French texts (France, and Québec where French is mandatory; GOAL 16) — help, legal pages and /account/delete in FR (web, uncommitted)
- [x] V4-2 [web] The staff decision sheet keeps the previous report's decision. `Admin.tsx` `Decide`: `action`, `statement` and `grounds` are component state that is never reset when `report` changes (statement and grounds only on success, action never). Repro: decide a review report with "Remove the review"; open the next report, about listing l9: no option is pressed, the ground/clause/automated fields show, and the submit button reads "Remove the message"; pressing it would send `remove_content` for a listing. After a "Suspend" decision the next report opens preset to Suspend. A statement typed and then closed without deciding reappears on a different report. Expected: each report opens at Dismiss with an empty statement — Decide keyed by report (web, uncommitted)
- [x] V4-3 [backend] After an early hand-over the renter can neither report a problem nor withdraw until the booked time starts. Repro: instant-book l9 (Tue 29 Sep 17:00), press "I have collected it" (allowed from start − 30 min in production, any time locally), then "Report a problem": `POST /bookings/{id}/dispute` → 409 "nothing to report before the booked time; cancel instead", but cancel is refused from `active`. Someone who finds damage at the hand-over has no route for up to 30 min. Expected: allow a dispute from `active` at any time (or allow cancel) — backend: a dispute is open from `active` at any time; cancel stays closed from `active` (the renter holds the item, so no refund without staff; the dispute holds the payout)
- [x] V4-4 [web] Same repro as V4-3: the 409 is shown in a toast with the success check-mark icon, as the raw lower-case English server text ("nothing to report before the booked time; cancel instead"), the sheet closes and the typed description is lost, and there is no cancel button to follow the advice. Expected: an error style, a translated message, the sheet kept open with the text — error toasts have their own style everywhere; the dispute sheet keeps its text (web, uncommitted)
- [x] V4-5 [web] "Download my data" opens the operating-system share sheet on desktop browsers instead of downloading. `repo.ts` `exportMyData` shares whenever `navigator.canShare({files})` is true, which it is in desktop Chrome and Safari on macOS and Windows. Repro: buyer, Profile → Download my data at 1400 px: `navigator.share` is called with the file; closing the sheet gives no file and no message. Expected: a download on desktop, the share sheet only in the shells and on phones; a confirmation either way — share sheet only on touch-first devices (web, uncommitted)
- [x] V4-6 [web] Mixed units in a miles locale. Repro: browser en-US, Explore → Workshop & tools: the filter trigger reads "2 hours · 75 km", while the Filters sheet offers "6 mi · 19 mi · 47 mi · 93 mi" (none selected) and every result says "1.5 mi", "3.8 mi". Expected: the trigger in miles ("47 mi"), and the selected radius highlighted in the sheet — (web, uncommitted)
- [x] V4-7 [backend] The fee invoice names the recipient without an address. Repro: host, Earn → Invoices → CAP-2026-0000002: "An: Nadia Brandt", nothing else. § 14 (4) Nr. 1 UStG needs the recipient's full name and address (and the business name and VAT ID for a business). Expected: the recipient's address, or the business identity — backend: the recipient address is the trader's business address, else the address the payout provider verified (KYC); § 33 UStDV covers a small invoice without one
- [x] V4-8 [web] The invoice row mixes two date formats in the English UI: "Service fee · Festool TS 55 plunge saw + 1.4 m rail · 27.09.2026" and, on the next line, "CAP-2026-0000002 · 9/26/2026". The service date comes preformatted in German from the `description`. Expected: both dates in the reader's locale (send the date, not text) — rows built from title and serviceStart/End in the locale (web, uncommitted)
- [x] V4-9 [backend] A booking keeps the hand-over address it first saw. `booking/routes.py:112-114` caches `row.handover` on the first read of an accepted booking, so an address added or corrected later never reaches the renter. Repro: l9 had no address; the host accepted bk_…0vw6ka, then added "Teststraße 1, 12099 Berlin" in Edit; the renter's active booking still showed only "Tempelhof · 3.8 mi away", while a new booking of l9 shows the street. Expected: read the address live while the booking is open (or refresh the snapshot on `listing.changed`) — backend: the hand-over is read live while a booking is accepted or active
- [x] V4-10 [backend] The seeded listings have no address, and the address is required, so the host cannot save any edit of l9 until they invent one. Repro: `/earn/edit/l9`, change the price, Save: nothing is sent, focus jumps to Address, whose error reads like a hint ("The street address where it is collected or used."). Expected: seed addresses; an error that says the address is needed ("Add the street address…") — backend: every seeded listing has a demo hand-over address (real street, made-up number); the required-address message is the web's
- [x] V4-11 [app] 390 px: the listing's sticky bar truncates the booking time in English, "Tue, Sep 29, 05:00 PM – 09:00…", so the end time is hidden. In FR the host card cuts the name to "Nadia Bra…". Expected: the full window (two lines or a shorter format) and the full name — sticky time wraps; host name wraps (web, uncommitted)
- [ ] V4-12 [app] 200 % text size at 390 px (root font-size 200 %) on `/listing/l9`: the dock labels overlap ("Explore" and "Bookings" run into each other), the heart becomes a squashed pill, the category chip is cut to "Work…", and the sticky bar plus dock cover almost half the screen with the time truncated. Expected: labels that wrap or hide, a round heart, a sticky bar that stays compact — partly (web, uncommitted): dock labels capped and truncated, heart stays round; the sticky bar at 200 % is still tall
- [x] V4-13 [app] Hand-over photos can't be added one at a time. `Evidence.tsx:199` replaces the selection on every pick ("Choose other photos"). On a phone, the camera returns one photo per pick, so "every side, any marks, the meter" means one save per photo. There is no remove button per thumbnail either. Expected: each pick adds, up to 12, with a remove button on each thumbnail — picks add, remove per thumbnail (web, uncommitted)
- [x] V4-14 [web] Batch listings suggest a quantity that does not fit. Repro: `/listing/l31` (box truck) opens at 50 pallets, "Nothing free that long… Try 13 pallets"; after that tap, 13 pallets also says "Nothing free that long… Try 10 pallets". 10 works. Expected: the suggestion is checked against the offers; the page opens on a quantity that fits — suggestion from the longest free window; opens on a batch that fits (web, uncommitted)
- [ ] V4-15 [web] The staff console shows raw codes and ids. A report card reads "Offensive or abusive · Review rv_l9_2", without the review's text or a link, so staff decide without seeing it. The decided card in DE reads "Entschieden: remove_content — …". The audit log reads "dismiss · listing l9", "remove_content · review rv_l9_2", "by ccca1d18-8d09-44bb-9740-db695d18215f" in every language. Expected: the reported content (or a link) on the card, translated action and target names, and the staff member's name or email — partly (web, uncommitted): decisions, targets and staff in words; the reported review or message text needs the report answer to carry it (backend)
- [x] V4-16 [backend] Seeded businesses have no business identity. Havelspedition GmbH (b10, l31) is `kind: business` and the listing says "Business. EU consumer rights apply to your booking.", but there is no legal name, address, register number or VAT ID on the listing or in the confirm sheet (no TraderNote), because the seed has none. Expected: seed business details; a business without them should not be bookable (or the profile should require them) — backend: every seeded business has trader details (legal name, address, register number, VAT ID)
- [x] V4-17 [web] Help copy is wrong: `/help/paying` says "It is charged only when the owner accepts" (an instant booking is charged at once) and "Every booking has an invoice under Earn → Invoices" (renters get none; the invoices are the owner's fee invoices). Expected: copy that matches instant book and who gets an invoice — (web, uncommitted)
- [x] V4-18 [web] The copy on closed and completed bookings contradicts itself. A cancelled booking with no messages shows "No messages yet. Ask about the hand-over, access or anything you need." directly above "This booking is closed, so no new messages can be sent." A completed booking still says "Report it before the booking is marked complete". Expected: no invitation to write on a closed booking; the evidence hint reworded once the booking is complete — (web, uncommitted)
- [x] V4-19 [web] Mixed time formats. On `/earn/edit/l9` the listed windows read "05:00 PM – 09:00 PM" while the patterns read "18:00 – 23:00, every day" and "Sep 26 – Oct 9, 18:00 – 22:00". Everywhere in en-US the 12-hour times keep a leading zero ("05:00 PM", "From 11:30 AM"), which en-US does not use ("5:00 PM"). Expected: one format per locale — one clock per locale, no leading zero in 12-hour (web, uncommitted)
- [x] V4-20 [web] Profile business fields: the errors come one at a time (legal name, then address, then VAT), the fields are not `aria-invalid`, and the VAT ID is not checked on the device. The server's answer is shown raw, in lower-case English ("that VAT ID does not look right: a German one is DE and 9 digits"). On sign-up, "Create account" stays disabled for an invalid email with no message saying why. Expected: all errors at once and translated, and an inline email error — all field errors at once, server `fields` mapped, VAT checked on the device, inline email error (web, uncommitted)
- [x] V4-21 [web] French typography is inconsistent: no space before "?", ";" and ":" in "Que prêtez-vous?" (page title), "Pour combien de temps?", "Encore bloqué?" and "…ne s'appliquent pas;", while "Réservation instantanée :" has one. The day chips read "Mar. 29 Sept." while the sticky bar reads "mar. 29 sept.". Expected: a narrow no-break space before ? ; : ! throughout, and lower-case abbreviations — no-break space before :, narrow before ; ? !, first-letter-only chips (web, uncommitted)
- [x] V4-22 [web] Focus goes to `<body>` when the check-in sheet that opens on its own after "I have handed it over" is closed ("Not now"): the opener was replaced by "Back to Earn". Expected: focus on the photos panel or the new primary action. Sheets opened from a button return focus correctly (Filters, Report, Withdraw, Add photos, staff Decide) — (web, uncommitted)
- [x] V4-23 [web] Small things below Airbnb/Vinted: after rating the renter, the host sees the renter's rating of them but not the one they gave; the "How was …? Rate it" bell item stays after rating; an instant booking's first step reads "Requested"; Explore fetches the spotlight twice after sign-in (Kreuzberg, then the home district Mitte); the address placeholder is always "Oranienstraße 12, 10999 Berlin" and the footer says "One capacity network across Europe" (GOAL 16: US and Canada too) — own renter rating shown, "Booked" for instant book, one spotlight fetch, neutral placeholder and footer (web, uncommitted); the lingering "Rate it" bell item is backend
- [x] V4-24 [web] (unconfirmed) "Sign out everywhere" was logged by the browser as `POST /api/me/sign-out-everywhere` 503 while the gateway and catalog logged 204 for the same call; the app went on as if it succeeded. `auth.ts` throws on a non-OK answer, so the 503 is probably a logging artefact, as in V3-23 — backend: the real defect: the token that asked for sign-out-everywhere (and any issued in the same second) stayed valid for 15 min, since the check rounded the revocation time down; now compared exactly. The browser's 503 was not reproduced through the gateway or the dev proxy

### Batch V5 (backend)

- **Held out of market (V5-1):** `GET /me/listings` items carry `holdReason: "market_not_live" | "district_not_in_country"` next to `held: true`; `/admin/listings/held` items carry it too; approving one gets 409 with that code. The owner's `PUT /listings/{id}` into an open market releases it. Unset for the price check.
- **`booking.notice` → bell and email (V5-7), kinds:** `dispute_refunded`, `dispute_partial`, `dispute_owner_paid` (both sides, with the amount and "you agreed" or "Cappy decided"), `dispute_escalated` (both), `claim_filed` (renter), `claim_confirmed`, `claim_rejected` (both). A booking leaving `disputed` no longer sends "cancelled" or "How was …?".
- **Payout notice (V5-13):** names the listing and its start ("Table saw, Sat 3 Oct, 10:00"). **Decline notice (V5-16):** carries "Reason: …". `booking.status_changed` has `declineReason`.
- **Payments:** a refund of part of the price (a dispute settled in part, or a late cancellation) leaves the payment `partially_refunded`, not `refunded`.
- **Batch listings (V5-22):** optional `maxQuantity` (≥1); a request above it is not feasible ("takes at most N per booking"). `/api/categories` items carry `setupLabel` (freight: "Loading", the rest "Setup and programming"), which the quote's `extraLabel` now is.
- **Bell (V5-31):** a decision about someone's content or account (`taken_down`, `suspended`, `content_removed`) shows its whole statement in `body`.
- **Local:** `make confirm EMAIL=… LEAD=1` puts an account in `admin` and `admin-lead`.

## Verification round 5 (V5)

Run by a separate verifier on the local stack, 2026-09-26 (10:34–12:35 CEST), fake payments, signed in only through the demo buttons. `resize_window` did not change the viewport (it stayed 606×701), so the web version was checked in a 1400×1620 same-origin iframe scaled to fit, and the app version in a 390×844 same-origin iframe; most flows were walked in the 606 px tab (phone layout). Languages were switched with the app's own switch (Profile → Language, and the sign-in screen); the browser's `navigator.language` is en-US, so English was the en-US pass (miles, 12-hour clock). Walked end to end: instant book, request/accept/decline/cancel, masking and reveal, message report and removal, the closed conversation, early hand-over and complete, two-way blind reviews, a dispute on an active (early-handed-over) booking resolved both ways, no-show from each side, the held listing (van raised to €120, approved, put back), the weekly schedule editor, the van batch request, market, business and listing field errors. Severity order, most severe first.

- [ ] V5-1 [backend] A German owner can publish a live listing in a market that is not open. Repro: staff (country DE), `/earn/new` → Workshop & tools, "Where is it?" De Pijp (Amsterdam, NL), address "Ferdinand Bolstraat 1, 1072 LA Amsterdam", publish: the listing `ls_01m3ef3prs02kp8v92fv06rkdd` is `active`, priced in EUR, and the buyer can open it ("De Pijp · 358 mi"). GUIDE A3 and FLOWS §0 say a listing outside DE/AT/CH is refused with `market_not_live`. Expected: the listing's own country (from its district) must be live and match the owner's market, else 422 `market_not_live` — backend: listings already outside an open market are held with holdReason (hourly job); web part: V5-2
- [x] V5-2 [web] The listing form offers every seeded district in Europe to every owner: a German owner's "Where is it?" lists Amsterdam-Noord, De Pijp, Jordaan, Oud-West, Lumezzane, Strijp, Alcântara, Arroios, Benfica, Marvila, Vaulx-en-Velin, Bovisa, Isola, Lambrate, Navigli, Batignolles, Belleville, Le Marais, Montreuil next to the Berlin ones (`/earn/new`, `/earn/edit/*`, all languages). Expected: only districts in the owner's country (or live markets), grouped by city (web)
- [x] V5-3 [web] Profile → Edit profile → Country "Österreich" or "Schweiz": "Where are you?" becomes an empty select, so an Austrian or Swiss member cannot set a home district (saving was not tried). The listing form has no Austrian or Swiss district either. Expected: districts (or a city/postcode field) for every live market (web)
- [x] V5-4 [web] Staff approve held listings blind. "Waiting for a check" shows title, rate, the owner's UUID (`c95a286d-dd72-4af2-a658-50d3382aca28`) and age; the title links to `/listing/<id>`, which is "That listing is not here" for staff (repro: staff opens `/listing/ls_01m3edjahvhfzz3cj17qm25e8s`). There is no photo, description, address or owner name to check. Expected: a staff preview of the held listing (photos, text, address, owner name and record) (web: owner name and record, hold reasons; a staff preview of the held listing needs the server to open it to staff) (web)
- [x] V5-5 [web] Messages are not refetched when the booking's state changes. Repro (script 13): buyer sends "mail me at anna@example.com or +49 170 1234567, or see www.example.com" on a requested l9 booking; host presses Accept: the thread still reads "Kontakt verborgen bis zur Annahme" three times until a reload shows the real text. Host then cancels: the thread still shows the email and phone number until a reload masks them again ("Kontakt verborgen"). Expected: the conversation query invalidated on accept, cancel, decline and every other transition (web)
- [x] V5-6 [web] The blind-review confirmations are the wrong way round. Buyer rates first (booking `bk_01m3eecdphsebqfm7ta4ra50b0`): toast "Review posted on Bandsaw and bench, book instantly" (FR "Avis publié sur …") although nothing is published (`reviews` empty). Host rates second: toast "Thanks. Demo will see it once they have rated too." although both are now published (the review appears, signed "Demo B."). `BookingDetail.tsx:216` always says "posted" for the buyer and `:218` always says "will see it" for the host. GUIDE script 12 expects the "will see it once they have rated too" message for the first rater. Expected: the message depends on whether the other side has rated (web)
- [x] V5-7 [web]+[backend] Nobody is told how a dispute ended. After staff "Resolve dispute: pay the owner" (`bk_01m3eec015jh0rs0kgr46p6qed`) the renter's page shows a plain "Finished" timeline and the renter gets only "How was …?"; after "refund the buyer" (`bk_01m3eebjavjg6pc54aa29zb7wb`) the renter sees "This booking was cancelled. €15.00 is refunded to the card" and "Cancelled: …". The host sees "You have been paid" or nothing. The report confirmation promised "we will tell you our decision". Expected: both sides get the decision (upheld or not), what happens to the money, and a banner on the booking that says the report was decided — backend: booking.notice to both sides (outcome, amount, agreement or staff); web: the banner (web)
- [x] V5-8 [web]+[backend] Dispute resolutions are missing from the staff audit log. After both "Resolve dispute" actions the console's audit log still lists only "Removed · Message" and "Approved · Listing" (`catalog.moderation_actions` has 2 rows); the resolution is only a `booking_transitions` row. The resolve form also takes no statement. Expected: every staff money decision in the audit log with who, what and why (GUIDE script 19 "every action above"), and a required reason (web)
- [x] V5-9 [web] The listing page shows at most 12 start times per day (`Listing.tsx:553` `times.slice(0, 12)`). Repro: l9 has a window today 11:45–22:00; with 2 hours the starts stop at 17:30, so 18:00–20:00 can't be booked; with 4 hours 18:00 is missing. Expected: every start, in a scroller or a "show later times" row (web)
- [x] V5-10 [web] The generated cover says "Nothing free this week" (DE "Diese Woche nichts frei", FR "Rien de libre cette semaine") wherever it is drawn without slots: the booking page hero, the confirm sheet's thumbnail (FR text cropped to "cette semai"), the Bookings "Next up" card, and even a search result card that offers a time right under it (Explore → Workshop & tools, DE: "Diese Woche nichts frei · Bandsaw and bench … Mo., 28. Sept., 09:00 – 11:00"), for listings with 40+ free hours. Expected: no availability claim where the slots aren't known (title or category plate instead) (web)
- [x] V5-11 [web] The business tax field is labelled "USt-IdNr. / Steuernummer (optional)" but rejects a Steuernummer: "12/345/67890" → "Eine USt-IdNr. beginnt mit den zwei Buchstaben des Landes…". A Kleinunternehmer without a VAT ID can't enter the number the label asks for. Also, with the name cleared, "Sag den Leuten, wie sie dich nennen sollen." shows but `p-name` is not `aria-invalid`. The other field errors now come all at once (V4-20 fixed). Expected: accept a national tax number (or split the fields), and mark every invalid field (web)
- [x] V5-12 [web] Signed out, the emergency number follows the browser's region, not the chosen language or place: with the browser at en-US and the page switched to Deutsch, `/legal/report` and its form say "Ist jemand in unmittelbarer Gefahr, ruf zuerst die 911 an". A German visitor with an English (US) browser, which is common, is told to call 911. Signed in, the market's number (112) is shown. Expected: 112 unless the visitor is known to be in the US or Canada (or show both, e.g. "112 (EU) / 911 (US, Canada)") (web)
- [x] V5-13 [backend] Payout notices name the raw booking id: bell and email "Du hast 12,75 € erhalten — Dein Anteil für die Buchung bk_01m3eec015jh0rs0kgr46p6qed ist auf dem Weg…" (EN "Your share for booking bk_01m3eecdphsebqfm7ta4ra50b0…"). Expected: the listing title and date
- [x] V5-14 [web] Focus goes to `<body>` when the check-in sheet that opens by itself after the renter's "I have collected it" is closed with "Not now" (FR "Pas maintenant", booking `bk_01m3eec015jh0rs0kgr46p6qed`). V4-22 fixed the host's side only. Expected: focus on the photos panel or the new primary action (web)
- [x] V5-15 [web] Console errors on every booking page with messages: the message report button renders its Sheet inside the bubble's `<p>` (`Conversation` → `Bubble` → `ReportButton`), so React logs "In HTML, <div> cannot be a descendant of <p>" and the same for `<h2>` and `<p>`. Expected: the sheet portalled out of the `<p>` (or the meta line a `<div>`) (web)
- [x] V5-16 [web] After an owner declines, both sides read "Muss erst repariert werden Die Kartenreservierung ist aufgehoben…": the reason chip is glued to the next sentence with no full stop. The owner's page also offers the renter's CTA "Etwas anderes finden". The renter's bell and email say "abgelehnt" but not the reason (GUIDE script 7 expects the reason). Expected: "Grund: Muss erst repariert werden." on its own line; no buyer CTA for the owner; the reason in the notice — backend: the reason is in the notice; web: the chip and the owner CTA (web; the notice text is the server's) (web)
- [x] V5-17 [web] Numbers and plurals: "Renter 4.0 from 1 bookings" (EN), "Als Mieter 4.0 aus 1 Buchungen" (DE: English decimal point and wrong plural), "pour une réservation de 1 heures" (FR, listing form earnings box), "15 %" with a space in en-US. Expected: `Intl` number formatting and plural rules per locale (web)
- [x] V5-18 [web] Untranslated or mixed strings: DE van listing price row "Setup and programming"; DE removal email "Rechtsgrundlage: … (Terms of use: rules for listings and conduct)"; the default approve statement "Checked and approved" in the DE audit log; the audit log's "von du" (DE: "von dir"). Expected: German throughout (web strings; the removal email is the server's) (web)
- [x] V5-19 [web] French typography and grammar still slip: "Annulation: Remboursement intégral…" (no space before the colon, capital after it) in the confirm sheet; "09:00 – 18:00, lun.–ven.. Cappy garde…" (double full stop) in the weekly editor; bell and email subject "Comment s'est passé Bandsaw and bench, book instantly?" (no space before "?"); "Confirmé : Bandsaw …" for a réservation (masculine; "Annulée", "Refusée" are feminine). Expected: V4-21's rules everywhere, and "Confirmée" (web; email subjects are the server's) (web)
- [x] V5-20 [web] German wording: the confirm sheet says "Nadia muss zuerst annehmen; lehnt er ab…" (Nadia is a woman; use neutral wording); after the renter reports a no-show, the renter's page says "Der Mieter bekommt alles zurück (15,00 €)" in the third person; the owner's page says "Gemeldet: Du bist nicht erschienen" with no way to contest it, while after the owner reports the renter the owner's own page reads the renter's text "Stimmt das nicht, hol dir Hilfe zu dieser Buchung" and the sheet promises "Sie kann widersprechen". Expected: gender-neutral copy, "Du bekommst alles zurück", and a "this is wrong" route for the owner (web)
- [x] V5-21 [web] Instant-book copy still contradicts itself: on the bandsaw's confirm sheet "The exact address is shared once the owner accepts" (FR "…une fois la demande acceptée") sits above "Confirmed as soon as your card is held; Demo does not need to accept"; the owner's edit form says "Les locataires paient par carte quand vous acceptez" (FR) with Instant book on; the welcome screen says "Du bestätigst jede Buchung". Expected: copy that depends on instant book (web)
- [x] V5-22 [web] The van (batch listing "Two pallet spaces free") offers 10, 25, 50, 100, 250, 500 and 1000 pallets; the page opens on 2, which is not a chip, and there is no 1. The copy treats it as a machine: "2 pallets is about 5 hours on this machine", "Setup and programming €20.00", and the form's "Maschine: Ford Transit L3H2", "Teile pro Stunde 0.5". Expected: quantity choices within the listing's capacity, and freight wording (pallet spaces, loading time) for the freight category — backend: maxQuantity, freight setupLabel "Loading"; web: the chips and the form wording (web)
- [x] V5-23 [backend] A weekly window that has already started is dropped for the whole day (`catalog/schedule.py` `windows`: "one that already started is left out rather than cut"). With the stack started at 10:34 on a Saturday, the van (Sat/Sun 10:00–16:00) had no window today, so the "Van run … on Saturdays" could not be booked on a Saturday. Expected: cut the running window at now (plus the lead time), as the hourly roll-on should
- [x] V5-24 [guide] The 5-minute-lead flows can't be started as written on a weekend. GUIDE A3, A5 and scripts 9 and 11 say to "book a start about 5 to 10 minutes from now (the plunge saw, or one of the second host's listings)". On Saturday 26 Sep none had a window today: l9's first is Sunday 17:00, the bandsaw is Mon–Fri, the van's today window was dropped (V5-23). The tester has to add one first (Earn → Edit → "Choose dates myself" or "Set my own weekly hours"). Expected: the guide says how, or the seed gives l9 a window every day (seed: l9 and the bandsaw open every day)
- [x] V5-25 [guide] GUIDE A1 says "The web's listing form does not offer weekly opening hours yet; only the API does". The form has "Set my own weekly hours" with day chips, times and "Add more hours", and it works (bandsaw: Saturday 11:30–18:00 added, a window created today). Expected: the guide describes the editor
- [x] V5-26 [guide] GUIDE A1 and script 3 say the demo buyer's home district is Kreuzberg ("starting from Kreuzberg"); it is Mitte, because `local/e2e.py:219` PUTs `/me` with `"district": "Mitte"` for the demo buyer, so `make e2e` changes the demo data. Expected: e2e uses its own account (or restores Kreuzberg), and the guide matches
- [x] V5-27 [guide] GUIDE A3 and script 19 say staff see **Staff** in the desktop header; at 1400 px the header has Explore, Bookings, Earn, You only, and the staff link is in the footer (`AppShell.tsx:398`). Expected: a header link for staff, or the guide says footer
- [ ] V5-28 [app] V4-12 still open at 200 % text (390 px, `/listing/l9`, DE): dock labels cut to "Entdec…", "Buchu…", "Verdie…", the Bookings badge sits on its label, the category chip is "W…", and the sticky bar with the dock covers about half the screen. Expected: dock icons with labels hidden or wrapped at large text; a compact sticky bar — partly (web): the dock shows icons only at large text; the sticky bar is still tall
- [x] V5-29 [web] Desktop (1400 px): the Bookings badge in the header overlaps the icon and the first letter of "Réservations" (FR, buyer). Expected: the badge beside or on the icon's corner, clear of the label (web)
- [x] V5-30 [web] Earn does not show a disputed booking: host2's Earn listed "Upcoming 3" (the 11:30, 12:30 and 13:30 bookings) while the 14:30 booking was disputed; the only trace was the bell. Earn's "98 hours / 8.047,50 € nobody pays you" also counts the held studio, which nobody can book. Expected: an "Under review" group on Earn; unbookable listings left out of the idle figure (web)
- [x] V5-31 [web] The in-app removal notice says only "A message or review of yours was removed. Your account is not otherwise restricted." — which message, why and how to contest are only in the email. Expected: the Art. 17 statement (content, reason, ground, redress) in the app too — backend: the bell shows the whole statement; web: render it (web)
- [x] V5-32 [web] Small things below Airbnb/Vinted: the report sheet opens with "Betrug" (fraud) preselected instead of "Choose a reason"; after the host accepts, the past step still reads "Requested — Waiting for your answer"; the van's day chips drop the weekday after the first week ("Oct 3", "3 oct.") next to "Tue, Sep 29"; the bandsaw edit page lists all 40 generated windows with a "Remove" each, and after the first week without weekday ("5 oct."); the "Profitez-en" toast is drawn in the middle of the check-in sheet over the note field; a disputed booking's sticky CTA is "Browse capacity" and the hand-over address disappears while the renter still holds the item; a completed booking still offers "Add check-out photos" (web)
- [ ] V5-33 [web] (unconfirmed) After a sign-out and sign-in in one tab, the new session's refresh token was gone from storage four times (a reload then signed out). It happened only while an old tab from before many Vite hot reloads was open on `/login`; after reloading that tab it stopped. Probably dev-only: each hot reload of `auth.ts` leaves another `storage` listener whose stale module state calls `refresh()` and `forget()`. Worth a check with two fresh tabs in a production build

## Docs-sync contradictions (29b2323) — fixed in one batch

- [x] D-16 [backend]+[web] Case page payment rows: payments stores and answers what moved (`refunded_amount`, `paid_out_amount`, migration 0010), in minor units; the web shows payments' own statuses (`transferred`); a renter no-show is `transferred`, not `refunded`/`partially_refunded`
- [x] D-17 [backend] The staff note reaches both parties in the settled notice (EN/DE/FR framing, the note as written)
- [x] D-18 [backend] `/admin/listings/held` carries the listing's `currency`
- [x] D-19 [infra] `admin-lead` Cognito group in Terraform
- [x] D-20 [local] `COGNITO_ENDPOINT_URL` for every service (case search by email works locally)
- [x] D-21 [infra] Analytics lake keeps only `action`, `targetType`, `at` of `staff.action`
- [x] D-22 [backend] `ResolutionRow` docstring true (`by` is the accepter, `role` "parties")
- [x] D-23 [backend]+[web] Dispute offer window and late-return window as settings; locally 10-minute escalation and late returns from the hand-over; the booking answer carries `lateReturnFrom`; deployed settings refuse the short values

### Batch V6 (backend)

- `GET /bookings/{id}/dispute` (and the case's `dispute`): once settled, `outcome` (pay_owner | refund_buyer | partial), `refunded` (minor units), `settledBy` (staff | agreement), `staffNote` (staff's note as written; absent for an agreement).
- `GET /api/admin/listings/{id}/offers?hours=&limit=&perDay=` and `POST /api/admin/quote {listingId, requirement}` (staff; held listings included). `/api/admin/listings/{id}` adds `handover {address?, instructions, location?, postalCode?}` and `reviews` (first 20).
- `GET /listings/{id}/offers` accepts `perDay` (1–100): at most that many starts on any one (UTC) day.
- `GET /api/admin/audit` items add `details`: `{bookingId, listingTitle, currency, amount?, outcome?, reasonCode?, resolutionId?, claimKind?, claimId?}` for booking actions; `statement` is staff's note only ("" when none).
- `GET /admin/resolutions` items add `title`, `requesterId`, `ownerId`, `ownerName`.
- Bookings carry `extendsId` for an extension.
- New notice kinds (bell and email, category bookings, always emailed): `owner_cancelled`, `no_show_owner_renter`, `no_show_owner_owner`, `no_show_renter_owner`, `no_show_renter_renter`.
- `GET /api/payments/invoices/{number}` is rendered in `Accept-Language` (en, de, fr; German when absent).

## Verification round 6 (V6)

Run by a separate verifier on the local stack rebuilt from clean, 2026-09-26 (14:28–15:25 CEST), fake payments, signed in only through the demo buttons (plus, for the two-sided steps, the same demo sessions' access tokens replayed from the page, so buyer and owner could act while the other was on screen). The Chrome window stayed hidden the whole time (`document.visibilityState` "hidden"), so `resize_window` did not change the viewport (1600×857 CSS px, used as the desktop web version), background timers were throttled, and polling and toast timings could not be judged. The app version was checked in a 390×844 same-origin iframe. Browser locale en-US (miles, 12-hour clock); DE and FR through the app's own switch. The SES outbox (`/_aws/ses`, 76 mails) was read for every flow. Severity order, most severe first.

- [x] V6-1 [backend] The staff note never reaches the bell. Repro: staff decides bandsaw booking `bk_01m3evcp71vkhvs2kapypnjk2x` "Refund part of it" €5, note "The photos show a bent fence; a small refund is fair."; the email to both sides ends "From Cappy's team: The photos show…", but `GET /api/notifications` (EN, DE, FR) gives only "Cappy decided: €5.00 goes back to the renter, and the owner is paid for the rest." Same for "Pay the owner" (`bk_01m3evajsh927bem3ja74rn29k`) and "Refund in full" (`bk_01m3ex5yd8a12qrn4axkra0stv`). The booking page's "The reported problem was decided" banner does not show it either, so in the app nobody sees why Cappy decided. Expected: the note in the bell body (and on the banner), as D-17 promises for "the settled notice" — **backend: the note in the bell (summary keeps staff's paragraph) and `GET /bookings/{id}/dispute` → `outcome`, `refunded`, `settledBy`, `staffNote`; the banner is web** (uncommitted) — web: the decided banner shows "From Cappy’s team: …" from `staffNote`, and says when the parties agreed
- [x] V6-2 [web]+[backend] The staff listing preview misleads. `/admin/listing/ls_01m3etzv195qw6y4hwx013g4r4` (the held studio, Mon–Fri 09:00–18:00, "45 h free this week" on host2's Earn) says "Nothing free that long. Demo has no 4 hours gap in the next four weeks. A shorter booking may fit." with duration chips "2 hours · 8 hours": the page never asks for offers, and its `/api/quote` and `/api/listings/…/reviews` calls answer 404. The preview also has no hand-over address (`GET /api/admin/listings/{id}` carries none), so staff still cannot check where it is, and it shows the member actions **Report** and **Block** to staff. Expected: the real free windows (or no availability block), the address, no member actions — **backend: `GET /api/admin/listings/{id}/offers?hours=&perDay=`, `POST /api/admin/quote` (matching, staff, held listings included), and `/admin/listings/{id}` carries `handover` and `reviews`; removing Report/Block for staff is web** (uncommitted) — web: the staff preview uses `/admin/listings/{id}/offers` and `/admin/quote` (held listings included), shows `handover` and the reviews the admin answer carries, hides Report/Block, and shows no availability for listings nobody can book (hidden for where they are, paused, taken down)
- [x] V6-3 [web] The studio's page opens on a duration it has no chip for. `/listing/ls_01m3etzv195qw6y4hwx013g4r4` (2 to 10 hours) offers only "2 hours · 8 hours" (DE "2 Stunden · 8 Stunden"), yet prices "160,00 €/h × 4 Stunden = 640,00 €" and the sticky card says "4 Stunden", with no chip selected. Expected: a chip for the duration in use (4), or open on one of the chips — web: the priced duration is always a chip, and selected
- [x] V6-4 [web] Extend offers a duration the listing refuses, and shows the raw server text. On the plunge saw (at least 2 hours), accepted booking `bk_01m3ewe9k5tgtem0p3ndtnq682`: **Extend** opens with "1 hour" selected; **Book 1 hour more and pay** gives the toast "not feasible: minimum booking is 2 h" (lower-case English, in DE too). Expected: only durations within the listing's limits, and a translated message — web: Extend offers only the listing's own lengths (from its minimum); "not feasible" answers read as one translated sentence
- [x] V6-5 [web] One screen, two deadlines. After **Offer €10.00** on a disputed bandsaw booking the toast says "Offer sent. Demo has 72 hours to answer" while the card under it says "Otherwise Cappy decides in 10 min." (locally). The escalation mail then says "There was no agreement within 72 hours" after 10 minutes. GUIDE 25 says "the texts always say 72 hours", but the card does not. Expected: one source for the window in every text — web: the toast names the server's deadline (`respondBy`); no fixed "72 hours" left on the web
- [x] V6-6 [backend] Emails to one person switch between en-GB and en-US dates. Host: "Answer by Sat 26 Sep, 15:00" (13:53 request), then "Answer by Sat, Sep 26, 5:00 PM" and "Mon, Sep 28, 10:00 AM" in the payout. Host2: "by Sat 26 Sep, 14:45" in the offer mail, "Sat, Sep 26, 4:00 PM" in the payout of the same booking. The format seems to follow whoever triggered the mail, not the recipient. Expected: the recipient's locale every time — **backend: emails use the reader's own locale, the app's last `Accept-Language` (remembered on the bell) before Cognito's; a test with an en-US owner and an en-GB renter** (uncommitted)
- [x] V6-7 [app] 200 % text at 390 px (iframe, FR, `/listing/l9`): the page scrolls sideways (scrollWidth 420 of 390), because the host card's rating column "4,7 (19) toutes ses missions" does not wrap. The dock still shows truncated labels ("Réserv…") with the Bookings badge sitting off the icon, the category chip is "At…", and the sticky bar with the dock covers about a third of the screen. Expected: no sideways scroll; the V5-28 icons-only dock — web: the owner card's rating column wraps (no sideways scroll at 200 % FR), the dock follows text-size changes after load (1rem probe + resize), one probe per dock
- [x] V6-8 [web] The case list keeps stale offer and claim labels. Bandsaw `bk_01m3evcnz3xgmmt34bqqa9wx7m`, settled by agreement (Finished), still reads "Offer on the table: €7.00" under **All**. The claims filter shows "1 open claims". Expected: no offer line once settled; plural rules — web: offer and escalation labels only while disputed; "1 open claim"
- [x] V6-9 [web] The audit log still shows raw machine text: "Resolved a dispute · Booking … refund_buyer 1500 EUR (not_as_described) The motor fault…", "Proposed a refund … partial 26000 EUR (damage) …", an untranslated action "withdraw_resolution · Booking …" with the statement "withdrew rs_01m3ew8tk1cr57bt7ske5xcb5f". Every case view is logged twice ("Opened a case" ×2 per visit). Expected: outcome, amount in money and the reason in words (GUIDE 24); one entry per opening — **backend: audit lines carry `details` {amount, currency, reasonCode, outcome, bookingId, listingTitle, …} and `statement` is only what staff wrote; a case or evidence read repeated within the minute is one line (`dedupe`); rendering in words is web** (uncommitted) — web: `details` rendered in words (listing · outcome · money · reason. note); rows from before V6 (`details: {}`) read their old machine line in words; bare echoes dropped; the case fetched once per opening
- [x] V6-10 [web] The case page keeps offering **Decide** while a proposal waits. On the €320 studio case, after "Above your limit: it waits for a second staff member", the whole form stays live; **Pay the owner** + **Decide** answers "A refund for this booking is already waiting for approval." (for a decision that is not a refund). The **Waiting for approval** card on the console names no booking or listing ("Refund the renter in full · €320.00 · Damage · proposed by you"). Expected: the form replaced by the pending proposal and **Withdraw my proposal**; the booking title on the approval card — **backend: `GET /admin/resolutions` items carry `title`, `requesterId`, `ownerId`, `ownerName`; replacing the form while a proposal waits is web** (uncommitted) — web: a waiting proposal replaces the Decide form (Withdraw for the proposer); approval cards name the listing (`title`) and owner
- [x] V6-11 [backend] No-show and cancel notices say too little. After the renter reports the host as a no-show (`bk_01m3ewe9k5tgtem0p3ndtnq682`), the host gets "Cancelled: … The booking of … was cancelled." (not that it was reported as a no-show, that it counts against them, or how to contest), and the renter gets nothing, not even the refund. After the host cancels an accepted booking the renter's mail says only "was cancelled", with no refund amount and no word that the owner cancelled. Expected: who did what, the money, and the next step — **backend: no-show notices to both sides (`no_show_owner_renter/_owner`, `no_show_renter_owner/_renter`) with the refund and how to contest; `owner_cancelled` with the refund** (uncommitted)
- [x] V6-12 [web] DE: the Settle card reads "Sonst entscheidet Cappy in 10 Min.." (double full stop), and "Einigt euch, was der Mieter zurückbekommt" addresses the renter in the third person. A pay-the-owner decision reads "Zugunsten des Anbieters entschieden, er wird bezahlt." (gendered, see V5-20), and the listings say "sobald der Anbieter annimmt" — **backend: server DE texts gender-neutral (the taken-down phrase, the contest paragraph); the card and listing copy are web** (uncommitted) — web: no double stop after an abbreviated time; German role wording neutral ("die mietende/vermietende Seite")
- [x] V6-13 [web] Owner-side copy written for the renter: the owner's offer sheet says "Of €15.00. The owner is paid the rest." (should be "you are paid the rest"); the owner's booking page says "Found damage or a problem? Report it before the booking is marked complete", but only the renter can report; the case page files a pay-the-owner decision under "Refund decisions" — web: the owner reads "you are paid the rest", an owner-side damage hint, and "Decisions" instead of "Refund decisions"
- [x] V6-14 [web] Escape on the check-in sheet that opens by itself after the renter's **I have collected it** (`bk_01m3evajsh927bem3ja74rn29k`) sends focus to `<body>`. **Not now** on the owner's side lands on the photos panel, as fixed in V5-14 — web: checked, Escape lands on the photos panel on the renter's side too (the round was in a hidden window)
- [x] V6-15 [web] The freight listing form still labels **Setup time** and **Setup fee** (`/earn/new` → Freight), while the listing page says **Loading** (V5-22) — web: freight form reads Loading time / Loading fee
- [x] V6-16 [web] Profile → Edit profile → Switzerland lists "Kleinbasel, Länggasse, Plainpalais, Flon, Zürich-Kreis 5" and Austria "Lend, Wilten, Urfahr, Salzburg-Altstadt, Neubau": no city, and not sorted. Someone in Lausanne has to know that "Flon" is theirs. GUIDE 1 shows "Plainpalais (Genève)". Expected: "Flon (Lausanne)" style, sorted — **backend: `/districts` ordered by city, then district; the "Flon (Lausanne)" label is web** (uncommitted) — web: "Flon (Lausanne)" style labels, sorted
- [x] V6-17 [backend] French mails put a plain no-break space (U+00A0) before ";" ("avant sam. 26 sept., 15:21 ; ensuite"), where the V4-21 rule is a narrow one (U+202F) before ; ? !. The wording also changes between mails: "remboursés au locataire" in the offer, "à la personne locataire" in the settlement — **backend: French mails put U+00A0 before ':' and U+202F before ; ? !; « à la personne locataire » in every text** (uncommitted)
- [x] V6-18 [web] The confirm sheet's thumbnail crops the category plate to "Works… & tools" (the bandsaw, desktop) — web: the confirm sheet's thumbnail uses the small plate
- [x] V6-19 [web] The demo buttons are half translated: DE "Weiter als demo host 2 (new owner)"; FR "Continuer en tant que demo host 2 (new owner)", "Continuer en tant que hôte démo", "Continuer en tant que équipe démo" (no elision). Local builds only — web: host2's label translated; FR "Continuer avec le compte …" (no elision needed)
- [x] V6-20 [web] Pressing Enter in the Explore search blurs the field on desktop (`Browse.tsx:165`), so focus falls to `<body>` and further typing goes nowhere. Hiding the keyboard makes sense on a phone, not on a desktop — web: Enter keeps focus on desktop, puts the keyboard away on touch only
- [x] V6-21 [backend] The fee invoice is always German ("Rechnung", "Vermittlungsgebühr für Buchung bk_…"), also for a host who uses English; it names the raw booking id — **backend: the invoice page in the reader's language (EN/DE/FR, German without a header), named by the listing, the booking id as the reference line; the German issuer's tax fields in every language** (uncommitted)
- [x] V6-22 [web] (unconfirmed) An extension request outlives the booking it extends: the renter reported the host of `bk_01m3ewe9k5tgtem0p3ndtnq682` as a no-show, yet its extension request `bk_01m3ewmyazw4vhv14wqfpd92ft` stayed waiting for the host, with nothing on it saying it is an extension. After the no-show, 15:30–17:00 of the cancelled window was not offered again either — **backend: cancelling a booking (a no-show too) declines its pending extension (reason in EN/DE/FR) or cancels a confirmed one with a full refund; bookings carry `extendsId`** (uncommitted) — web: an extension links to the booking it extends (`extendsId`)
- [x] V6-23 [web] (unconfirmed) The plunge saw's day chips (2 hours) stop at Fri 2 Oct, although `/offers?limit=120` answers up to Sun 4 Oct and the schedule is open for eight weeks, so the next weekend can't be picked — **cause: 120 starts at 30-minute steps over an 08:00–22:00 day is about 4.5 days; backend: `perDay` on `/listings/{id}/offers` caps each day's starts so every day shows (web should send e.g. `perDay=28&limit=500`)** (uncommitted) — web: offers asked with `perDay=28&limit=500`, and the day rail shows two weeks
- [ ] V6-24 [web] (unconfirmed) V5-33 again: with a Cappy tab left over from an earlier session open on `/login`, **Continue as demo buyer** from `/login?next=/listing/l9` landed on "That listing is not here" (the listing, districts and reviews calls got 401), and a reload was signed out with no `cappy.refresh.v1` stored. After reloading the old tab it did not recur
- [ ] V6-25 [guide] Script 24: a staff member's own proposal no longer offers **Approve** (only **Open the case** and **Withdraw my proposal**), so "Approve … Expect: A second staff member has to approve a refund you proposed." cannot be reached. The decision reads "you", not "staff …"
- [ ] V6-26 [guide] Script 28: the Explore search is scoped to the searcher's metro (`useSearch(q, metro)`), so `sander` and `mitre` never show Amsterdam or Milan to a Berlin buyer, hidden or not. The check proves nothing. Before the job ran, `GET /api/search?q=mitre` without a metro did return the Milan saw. Expected: a check that can fail (open `/listing/n-l3`, the console list)
- [ ] V6-27 [guide] Script 7: the decline sheet's button reads **Decline**, not **Send decline**. Script 21: the dialog says "signed out within an hour", while the guide (and the server) end the old token at once — web part done: the booking page's decline sheet also says **Send decline**; the sign-out-everywhere dialog says "signed out at once" (guide part open)

| Script | Result | Notes |
|---|---|---|
| 1 Welcome and sign-up | blocked (partly) | Welcome (EN/DE/FR), `/listing/l9` signed out → sign-in → back to the listing, `/` after a visit → sign-in: pass. Sign-up, codes, onboarding, VAT: blocked, they need a typed password |
| 2 Language switch | pass | Findings V6-12, V6-17, V6-19; DE emails follow the switch; en-US "5:00 PM" |
| 3 Browse and search | pass | V6-20 |
| 4 A listing | pass | l9, bandsaw ("…once the booking is confirmed"), van (chips 1 and 2, Loading €20); studio: V6-3 |
| 5 Booking by request / instant | pass | Stripe-only limits not applicable (fake provider) |
| 6 Paying | pass | fake provider only |
| 7 Host accept / decline | pass | V6-27; the reason line and the email "Reason: …" |
| 8 Hand-over, complete | pass (photos not checked) | no file to pick; the completed booking opens the rating sheet; payout text names the listing |
| 9 No-show | pass (renter side) | the owner's side needs start + 30 min on a 19:00 booking; not waited. V6-11 |
| 10 Cancel and refund | pass | host cancel checked; the renter's withdraw sheets not re-walked. V6-11 |
| 11 Disputes | pass | early hand-over dispute, Settle card, Under review on Earn |
| 12 Blind reviews | pass | review shows as "Demo B." only after both rated; the toasts could not be timed (hidden window) |
| 13 Messaging and masking | pass | masking, reveal after acceptance (after a reload: the live refetch can't be judged in a hidden window), PayPal warning, re-masked after a no-show cancel |
| 14 ID check | pass | studio €320: sheet, consent, fake pass, booking goes on |
| 15 Becoming a host | blocked | needs a fresh account (password); the form checked as staff: Berlin districts only, freight labels V6-15 |
| 16 Payouts and invoices | pass | invoices for partial settlements are right (fee on what was kept); V6-21 |
| 17 Notifications | pass | Bookings email off → no "New request" mail, "Cancelled" still mailed; V6-1 |
| 18 Reporting | pass | min 10 characters, good-faith tick, reference, emails; the fourth signed-out report not tried |
| 19 Admin console | pass | reports dismiss, held studio approved, 29 out-of-market without Approve; V6-9 |
| 20 Data export, deletion | blocked | a download needs the user's go-ahead; deleting a demo account is off limits; a fresh account needs a password. `/account/delete` in FR: pass |
| 21 Sign out everywhere | pass | the old access tokens get 401 at once; one browser only |
| 22 Offline | blocked | the DevTools network throttle is not reachable |
| 23 Phone layout | fail | 390 px iframe: no sideways scroll at 100 % (EN/DE/FR, 10 screens); 200 %: V6-7 |
| 24 Staff case view | fail | V6-1, V6-9, V6-10, V6-25; within the limit, partial, pay the owner, full refund, the four-eyes hold and **Withdraw my proposal**: pass; the lead's approve and reject: blocked (`make confirm … LEAD=1` needs a password sign-in) |
| 25 Dispute offers | pass | €20 refused, offers both ways, stale offer "The offer changed a moment ago", €7 agreed, escalation after 10 min (both mails, console "Escalated to staff", banner); V6-5, V6-12 |
| 26 Late return | pass | 20 min refused, 90 min = €30.00, 45 min = €18.75, one per booking, Confirm and Reject mails |
| 27 Extend | fail | instant extend and refusal at 22:00: pass; by request on the plunge saw: V6-4 |
| 28 Hidden out-of-market | pass | held at 14:59 (32 min after `make up`), `/listing/n-l3` 404, Wien and Zürich (CHF 9.00 · 9,00 CHF) visible; V6-26 |
| 29 Daily limit | pass | the 11th refused, translated in DE |
