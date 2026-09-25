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
- [ ] R-13 Web deletion page for Google Play (`/account/delete`)

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

- [x] U-1 [all] App Store Connect review notes: the 5.1.1(v) justification for members-only access (verified private owners, location/availability of people's property, every feature account-bound) and demo accounts for renter and owner with email-code bypass — https://developer.apple.com/app-store/review/guidelines/#5.1.1 · https://developer.apple.com/distribute/app-review/ (backend, uncommitted)
- [x] U-2 [all] Welcome screen (`Welcome.tsx`) for first-timers: one hero, 3 value lines, "Create account" / "I have an account", DE/EN switch, legal links; no live listing data — https://developer.apple.com/design/human-interface-guidelines/onboarding (web, uncommitted)
- [x] U-3 [all] Welcome shown once: `welcomeSeen` flag; skipped for any device that has signed in before and for deep-link launches; "How Cappy works" reachable from Help — https://developer.apple.com/design/human-interface-guidelines/onboarding (web, uncommitted)
- [x] U-4 [app] Move the push permission prompt out of `pushSignedIn()`: priming sheet after the first booking request or listing publish; ask only when `checkPermissions()` is `prompt` — https://developer.android.com/training/permissions/usage-notes (web, uncommitted)
- [x] U-5 [app] Android back: `App.addListener('backButton')` closes the open sheet, else goes back, else minimises; predictive back enabled — https://capacitorjs.com/docs/apis/app (web, uncommitted)
- [x] U-6 [backend] `Idempotency-Key` on `POST /bookings`, `/listings`, `/reviews`, `/messages`, and on booking payment confirmation; web sends one key per form mount — https://docs.stripe.com/api/idempotent_requests (backend, uncommitted) + (web sends one key per form for listings, messages, evidence and ratings; web, uncommitted)
- [ ] U-7 [app] 3DS/SCA return into the shells: `return_url` on an associated domain, resume handler checks the PaymentIntent and shows the result; test with the 3DS2 test cards on iOS and Android — https://docs.stripe.com/payments/3d-secure/authentication-flow
- [x] U-8 [web] Times in the listing's time zone (`Intl.DateTimeFormat` with `timeZone`), label when it differs from the device; [backend] a DST-crossing booking test — https://developer.mozilla.org/docs/Web/JavaScript/Reference/Global_Objects/Intl/DateTimeFormat (backend, uncommitted)
- [x] U-9 [backend] Account deletion refused with a reason and a date while bookings are open or a payout is pending; the retention list (invoices kept 10 years) shown before confirming — https://developer.apple.com/support/offering-account-deletion-in-your-app/ (backend, uncommitted) + (web shows the 409 reason and date and the 10-year retention line; web, uncommitted)
- [x] U-10 [web] Session expiry mid-flow keeps the draft (AddListing, messages, review) and returns to it after sign-in — https://baymard.com/research/checkout-usability (web, uncommitted)
- [x] U-11 [web] Offline bar (`online`/`offline` events), cached reads, money actions disabled offline with the reason — https://web.dev/articles/offline-ux-design-guidelines (web, uncommitted)
- [x] U-12 [backend] Message scanner: detect phone, email, IBAN, URLs and "pay outside" phrases; before a booking is confirmed mask contact details; log for moderation — https://www.airbnb.com/help/article/209 (backend, uncommitted)
- [ ] U-13 [web] Chat safety UI: inline warning to the sender, a banner to the receiver ("Payments outside Cappy aren't protected"), report on each message, block offered after reporting — https://www.airbnb.com/help/article/2020 · https://www.vinted.com/help/628-recognize-spoof-and-phishing-messages
- [ ] U-14 [backend]+[web] Email one-time-code sign-in through Cognito `USER_AUTH`/`EMAIL_OTP`, password kept as an option — https://docs.aws.amazon.com/cognito/latest/developerguide/authentication.html
- [x] U-15 [backend]+[web] Password policy: min 12, no composition rules, breached-password check; rules visible under the field; show/hide toggle; paste allowed — https://pages.nist.gov/800-63-4/sp800-63b.html · https://baymard.com/blog/password-requirements-and-password-reset (backend, uncommitted) + (web: 12+ characters, rule shown under the field, show/hide toggle; web, uncommitted)
- [x] U-16 [web] Code field: `inputmode="numeric"`, auto-submit at 6 digits, 30-second resend countdown — https://www.w3.org/TR/WCAG22/#accessible-authentication-minimum (web, uncommitted)
- [ ] U-17 [app] Refresh token in Keychain/Keystore instead of Preferences (closes V1-28) — https://developer.apple.com/documentation/security/keychain-services
- [x] U-18 [web] Sign-in screen says why Cappy is members-only, with a "How we keep you safe" link — https://baymard.com/blog/password-requirements-and-password-reset (web, uncommitted)
- [x] U-19 [web] Onboarding: optional "rent / earn / both" choice that picks the landing tab and the empty states — https://www.nngroup.com/articles/mobile-app-onboarding/ (web, uncommitted)
- [ ] U-20 [web] Listing page: cancellation policy in plain words, owner response time, and a sticky bar with the total for the chosen slot, fee included — https://skift.com/2025/04/21/airbnb-makes-total-price-display-standard-on-listings-worldwide/
- [ ] U-21 [web] Browse filters: applied-filter chips with ✕ and "Clear all"; "Show N results" in the filter sheet; [backend] result count — https://baymard.com/blog/how-to-design-applied-filters
- [x] U-22 [backend]+[web] Notification centre: `GET /notifications` (paginated, unread count), a bell, each item opens its screen; per-category push/email settings, marketing off by default — https://m3.material.io/foundations/content-design/notifications (backend, uncommitted) + (web: bell in the desktop header, unread badge on the You tab, /notifications list; web, uncommitted)
- [x] U-23 [web] Empty states for Bookings, Earn, inbox, reviews, saved and no-results, each with a reason and one action — https://www.nngroup.com/articles/empty-state-interface-design/ (web, uncommitted)
- [x] U-24 [web] Error messages: Stripe decline codes mapped to plain DE/EN; a generic error screen with "Try again" and the request id — https://www.nngroup.com/articles/error-message-guidelines/ (web, uncommitted)
- [ ] U-25 [web] Photo uploads: per-photo progress and retry, client-side downscale to 2048 px, HEIC accepted or converted, the draft survives the app being killed — https://baymard.com/research/mcommerce-usability
- [ ] U-26 [app] Keyboard: `@capacitor/keyboard`; focused inputs and the chat composer stay above the keyboard on iOS and Android 15 edge-to-edge (WCAG 2.4.11) — https://capacitorjs.com/docs/apis/keyboard — partly (web, uncommitted): no keyboard plugin: interactive-widget=resizes-content and scroll margins instead
- [ ] U-27 [app] Dynamic Type in the iOS shell (`-apple-system-body` root, rem sizes); check dock, listing bar and sheets at the largest size — https://www.tpgi.com/text-resizing-web-pages-ios-using-dynamic-type/
- [ ] U-28 [web] Pseudo-localisation switch (+40% string length) and one verifier pass on it per round, for German length — https://www.w3.org/International/articles/article-text-size
- [x] U-29 [web] Colour scheme: dark tokens with `prefers-color-scheme`, or pin `color-scheme: light` plus the status-bar style so native controls match — https://developer.apple.com/design/human-interface-guidelines/dark-mode (web, uncommitted)
- [ ] U-30 [web] axe-core accessibility check over every route in CI; fix targets under 24 px, focus return from sheets, `role="status"` toasts, reduced motion — https://www.w3.org/TR/WCAG22/
- [x] U-31 [web] Accessibility statement (Barrierefreiheitserklärung) at `/legal/accessibility` in DE/EN with a feedback contact — https://www.bundesfachstelle-barrierefreiheit.de/DE/Fachwissen/Produkte-und-Dienstleistungen/Barrierefreiheitsstaerkungsgesetz/barrierefreiheitsstaerkungsgesetz_node.html (web, uncommitted)
- [ ] U-32 [backend]+[web] ID verification badge (Stripe Identity / Connect KYC), required before the first booking above a threshold and for vans; the badge says what was checked — https://www.airbnb.com/help/article/1237
- [ ] U-33 [web] Hand-over photos: a prompt at start and end, the upload time shown, the 24-hour damage-report window stated — https://help.turo.com/en_us/trip-photos-guide-or-guests-HytcE4g49
- [ ] U-34 [web] Safety card on BookingDetail before the first hand-over; one line on payment protection under the pay button — https://help.turo.com/en_us/trip-photos-guide-or-hosts-BkKcBEeN5
- [x] U-35 [backend]+[web] Sessions: "sign out everywhere" in Profile; Cognito `GlobalSignOut` on password reset; push devices removed with it — https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_GlobalSignOut.html (backend, uncommitted) + (web: Profile → Sign out everywhere; plain sign-out now revokes only this device's refresh token; web, uncommitted)
- [x] U-36 [app] Push-denied state: a Profile row "Notifications are off — Turn on" that opens the OS settings — https://developer.android.com/training/permissions/usage-notes (web, uncommitted)
- [x] U-37 [web] Bookings: a "next up" card at the top with the one action that matters now; statuses in text as well as colour (WCAG 1.4.1) — https://www.w3.org/TR/WCAG22/#use-of-color (web, uncommitted)
- [x] U-38 [web] Earn: "needs you" section first, with a countdown to each request's expiry (Airbnb Today tab pattern) — https://www.nngroup.com/articles/dashboards-preattentive/ (web, uncommitted)
- [x] U-39 [web] `/help` with 10–15 DE/EN articles and "Get help with this booking" (booking id attached) on BookingDetail — https://help.turo.com/ (web, uncommitted)
- [ ] U-40 [backend]+[web] Responsive images: 400/800/1600 widths from the media service, `srcset` with `width`/`height` set, placeholders — https://web.dev/articles/cls

## Stores and marketplace (S) — from docs/research/2026-09-store-and-marketplace.md

- [ ] S-1 [app] Add `PrivacyInfo.xcprivacy` to the App target: UserDefaults `CA92.1`, file timestamp `C617.1`, disk space `E174.1` if filesystem uses it, `NSPrivacyTracking=false`, the collected data types. Check with an Xcode privacy report — https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api
- [ ] S-2 [app] `NSCameraUsageDescription` (and `NSPhotoLibraryAddUsageDescription` if saving) in `Info.plist`, DE/EN via `InfoPlist.strings`. Test evidence "Take Photo" on a device — https://developer.apple.com/forums/thread/772332
- [ ] S-3 [legal/business] Data inventory → Apple app privacy label + Play Data safety form (Stripe.js/Identity signals, payment, ID images, photos, messages, location district, crash data), matching the privacy policy — https://developer.apple.com/app-store/app-privacy-details/ · https://support.google.com/googleplay/android-developer/answer/10787469
- [ ] S-4 [backend]+[web] Business owners: collect legal name, address, register number and VAT ID. Show them on the listing and at checkout, with "Cappy is not your contract partner" (§ 5b UWG, § 312l BGB). This is also the base for KYBC later — https://www.gesetze-im-internet.de/uwg_2004/__5b.html
- [ ] S-5 [legal/business] Minimum age 18 in the terms, an "I am 18+" confirmation at sign-up, and 18+ in both store questionnaires, including Apple's September 2026 social-media question — https://developer.apple.com/news/?id=tlur8uvi
- [ ] S-6 [legal/business] App Store Connect DSA trader status (address, phone and email published) and a Play organisation account with a D-U-N-S number (avoids the 12-tester/14-day gate) — https://developer.apple.com/help/app-store-connect/manage-compliance-information/manage-european-union-digital-services-act-trader-requirements/ · https://support.google.com/googleplay/android-developer/answer/14151465
- [ ] S-7 [web] Crash and error reporting: `@sentry/capacitor` (or a self-hosted `/api/client-errors` endpoint) from `ErrorBoundary`, `window.onerror` and `unhandledrejection`. Upload source maps per release. No replay or device id without consent (§ 25 TDDDG) — https://docs.sentry.io/platforms/javascript/guides/capacitor/
- [ ] S-8 [backend]+[web] Owner damage claim: owners report within 24 h of the end with evidence. The payout is held while a claim is open, the renter has 72 h to answer, then staff decide with reasons — https://www.airbnb.com/help/article/1415 · https://faq.fatllama.com/en/articles/10391171-what-are-the-criteria-for-the-lender-guarantee
- [ ] S-9 [backend]+[legal/business] Collecting on a claim: save the card for off-session use at booking (`setup_future_usage`), or a separate deposit hold per category (vans). The amount is shown in the total and the terms. Depends on G-B1 — https://docs.stripe.com/payments/save-during-payment
- [ ] S-10 [app] `android:allowBackup="false"` (or `dataExtractionRules` excluding the token prefs), and `arm64` instead of `armv7` in `UIRequiredDeviceCapabilities` — https://developer.android.com/identity/data/autobackup
- [ ] S-11 [backend]+[web] No-show reports: either side within 2 h of the start. A renter no-show counts as a late cancellation under the policy. An owner no-show means a full refund and counts against the owner — https://www.airbnb.com/help/article/3591
- [ ] S-12 [backend]+[web] Late return: "extend booking" when the next window is free. Otherwise, after 30 min grace, the normal rate for the extra time plus a capped late fee, reported by the owner within 24 h — https://getaround.com/help/articles/b075d5c22795
- [ ] S-13 [backend]+[web] Structured Art. 17 statement: restriction, facts, automated yes/no, legal ground or T&C clause, redress text (reply to contest, courts). A good-faith checkbox in the report form (Art. 16(2)(d)) — https://dsa-library.com/article/17/ · https://dsa-library.com/article/16/
- [ ] S-14 [app] Android 16 edge-to-edge check at targetSdk 36: Capacitor SystemBars / insets for the dock, sheets and toasts, with gesture and 3-button navigation on API 35 and 36 (with U-26) — https://developer.android.com/about/versions/16/behavior-changes-16
- [ ] S-15 [web] Route-level code splitting (`React.lazy` for Admin, AddListing, Earn, Profile, Legal). A CI budget of ≤170 KB gz for the entry chunk — https://web.dev/articles/performance-budgets-101
- [ ] S-16 [all] Review notes for 3.1.3(e) (physical services, card/Apple Pay, no IAP) and 4.2 (the native features list), added to U-1 — https://developer.apple.com/app-store/review/guidelines/
- [ ] S-17 [backend] Ban-evasion linkage: store the Stripe card fingerprint and the Connect bank fingerprint. A new account sharing one with a suspended account is held for review — https://docs.stripe.com/api/cards/object#card_object-fingerprint
- [ ] S-18 [backend] Owner cancellation consequences: counted per owner, shown as a rate on the profile, a ranking signal (and the ranking page updated), repeat cancellations queued for staff. A fee **(counsel)** — https://www.airbnb.com/help/article/990
- [ ] S-19 [legal/business] Withdrawal right by category: vehicle rental and fixed-date leisure services are exempt (§ 312g(2) Nr. 9 BGB). The checkout text and button follow the category **(counsel, G-B2)** — https://www.gesetze-im-internet.de/bgb/__312g.html
- [ ] S-20 [backend] Duplicate-listing detection: a perceptual hash (pHash) per photo. Matches across different owners go to the held queue (G-9) — https://github.com/JohannesBuchner/imagehash
- [ ] S-21 [backend]+[web] Dispute flow between the parties: a 72 h response window, an offer or counter-offer for a partial refund, auto-escalation to staff after the deadline — https://www.airbnb.com/help/article/767
- [ ] S-22 [legal/business] P2B for business owners: 30 days' notice before termination, two named mediators in the terms, the 15-day notice for terms changes as a process — https://eur-lex.europa.eu/eli/reg/2019/1150/oj/eng
- [ ] S-23 [web] Core Web Vitals field data (`web-vitals` → the analytics event pipeline). Targets: LCP 2.5 s, INP 200 ms, CLS 0.1 at p75 — https://web.dev/articles/vitals
- [ ] S-24 [app] Cold-start measurement on a mid-range Android (TTID in Play vitals, Xcode Organizer launch time). Budget 2 s; the splash screen hides on the first render — https://developer.android.com/topic/performance/vitals/launch-time
- [ ] S-25 [infra]+[docs] Release runbook: Play staged rollout 5→20→50→100% and App Store phased release, with a gate on crash-free sessions ≥99.5% and Android vitals below 1.09%/0.47%, and a halt procedure — https://support.google.com/googleplay/android-developer/answer/6346149 · https://developer.apple.com/help/app-store-connect/update-your-app/release-a-version-update-in-phases
- [ ] S-26 [backend]+[web] Percentage and per-user feature flags (on top of R-10 kill switches), read at app start from `/api/app-config` — https://martinfowler.com/articles/feature-toggles.html
- [ ] S-27 [app] In-app review prompt (`@capacitor-community/in-app-review` or similar) after a completed booking the user rated 4★ or more, at most once per 120 days — https://developer.apple.com/documentation/storekit/requesting-app-store-reviews · https://developer.android.com/guide/playcore/in-app-review
- [ ] S-28 [backend] Review-collusion signals: reciprocal 5★ pairs, reviews between accounts that share a payment fingerprint, bursts from new accounts. Flag for staff, never auto-delete (Omnibus) — https://www.gesetze-im-internet.de/uwg_2004/anlage.html
- [ ] S-29 [app] 16 KB alignment check of the release AAB (`zipalign -c -P 16`, Play bundle explorer) once per plugin upgrade — https://developer.android.com/guide/practices/page-sizes
- [ ] S-30 [backend] DSA counts derivable on request: monthly active recipients (Art. 24(3)), notices by reason and decision, median time to decision — https://prighter.com/resources/dsa-reporting-obligations/
- [ ] S-31 [legal/business] DAC7: switch on Stripe payout withholding for sellers who don't provide their TIN, and document the two-reminder rule (with G-10) — https://docs.stripe.com/connect/platform-tax-reporting
- [ ] S-32 [docs] Tick R-13 in TASKS: `/account/delete` already works signed-out (`web/src/app/App.tsx:55`) — https://support.google.com/googleplay/android-developer/answer/13327111
