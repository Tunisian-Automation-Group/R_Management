# Features and their provider seams

Every feature Cappy has today, where it lives, and what replacing its
provider with another third party takes. It describes the **committed code**,
not the plan: planned work appears only as task ids from
[`TASKS.md`](TASKS.md). Markets are all of Europe, the US and Canada
([GOAL 16](GOAL.md), [ADR 0013](adr/0013-markets.md)). Where the code
assumes one market (EUR, German texts, Berlin time), this file says so.

Paths are relative to the repository root. `path:line` points at the
definition. "Seam" means the interface or module boundary a replacement
plugs into. "No seam" means the provider is called directly, and the entry
names the smallest refactor that would create one.

Related living docs: [`INFRA.md`](INFRA.md) covers the AWS resources behind
each provider, and [`DATA.md`](DATA.md) covers the tables and events named
here.

## Contents

- [Summary](#summary)
- [Cross-cutting seams](#cross-cutting-seams)
- [1. Identity and accounts](#1-identity-and-accounts)
- [2. Profiles and business identity](#2-profiles-and-business-identity)
- [3. Listings and photos](#3-listings-and-photos)
- [4. Search and matching](#4-search-and-matching)
- [5. Booking lifecycle](#5-booking-lifecycle)
- [6. Instant book, policies and discounts](#6-instant-book-policies-and-discounts)
- [7. Payments, payouts and refunds](#7-payments-payouts-and-refunds)
- [8. Invoices and tax](#8-invoices-and-tax)
- [9. Identity verification](#9-identity-verification)
- [10. Messaging and masking](#10-messaging-and-masking)
- [11. Reviews](#11-reviews)
- [12. Notifications (email, push, inbox, settings)](#12-notifications-email-push-inbox-settings)
- [13. Trust and safety](#13-trust-and-safety)
- [14. Privacy (export, deletion)](#14-privacy-export-deletion)
- [15. The app shell (PWA and Capacitor)](#15-the-app-shell-pwa-and-capacitor)
- [16. Operations](#16-operations)
- [Features with no seam today](#features-with-no-seam-today)
- [How to keep this file true](#how-to-keep-this-file-true)

## Summary

Swap effort: **S** is about a day and touches one module. **M** is a few days
across service, config and infra. **L** means data migration, legal work or
changes to several services.

| Feature | Provider today | Seam exists? | Swap effort |
|---|---|---|---|
| Sign-up, sign-in, password reset | Amazon Cognito (the web app calls it directly) | Backend yes (any OIDC issuer/JWKS). Web no (`web/src/data/auth.ts` is Cognito-only) | L |
| Token verification in services | Cognito JWKS, RS256 | Yes (`TokenVerifier`) | S |
| Sign out everywhere | Cognito `AdminUserGlobalSignOut` | Yes (`Directory.sign_out_everywhere`) | S |
| Staff role | Cognito group `admin` (`cognito:groups` claim) | No (`require_admin` reads the claim) | S |
| Profiles, business identity, VAT ID check | In-house (regex, no VIES) | n/a (no provider) | S to add VIES |
| Listings, windows, saved | In-house (Postgres) | n/a | n/a |
| Photo storage | S3 + CloudFront; Pillow re-encode | Yes (`MediaStore`) | S |
| CDN purge on take-down | CloudFront `CreateInvalidation` | No (direct boto3 call) | S |
| Places, distance, map | Own `districts` table, haversine, own SVG map | No geocoder at all | M (M-5, M-7) |
| Free-text search | Postgres `LIKE` + trigram index | No (in `CatalogRepository.search`) | M |
| Matching, ranking, pricing | In-house (`matching/domain`) | n/a | n/a |
| Booking state machine, no double booking | In-house (Postgres exclusion constraint) | n/a | n/a |
| Instant book, cancellation policies, discounts | In-house | n/a | n/a |
| Card authorise, capture, cancel, refund | Stripe PaymentIntents (manual capture) | Yes (`payments/provider.py` `Provider`) | L |
| Owner onboarding and payouts | Stripe Connect Express, transfers | Yes (same `Provider`) | L |
| Webhooks, chargebacks | Stripe events | Partial (signature check behind `Provider`; event handling is Stripe-shaped) | M |
| Reconciliation sweep | Stripe intent status | Partial (`Provider.intent_status` returns Stripe's words) | S |
| Fee invoices | In-house HTML, German § 14 UStG template | Partial (`Issuer`: zone, rate, label) | M |
| VAT / sales tax, platform tax reporting | None (fixed rate from settings; DAC7 tags only) | No | L (M-11..M-14, M-24..M-27) |
| Identity verification | Stripe Identity (document + selfie) | Partial (`Provider.verification_session` + Stripe webhook + Stripe.js modal) | M |
| Messaging, contact masking, pay-outside flag | In-house regex | Module boundary (`mask`, `flagged`) | S |
| Blocks | In-house | n/a | n/a |
| Hand-over evidence photos | In-house, catalog media store | Yes (via `MediaStore`) | S |
| Reviews (two-way, blind) | In-house | n/a | n/a |
| Email | Amazon SES (v1 `SendEmail`) | Yes (`Mailer`) | S |
| Recipient email and locale | Cognito `AdminGetUser` | Yes (`Directory`) | S |
| Push | SNS Mobile Push → APNs / FCM v1 | Yes (`Pusher`), but tokens are APNs/FCM-native | M |
| Inbox (bell), notification settings | In-house | n/a | n/a |
| Email/push texts, languages | In-house (`texts.py`, EN/DE) | n/a | M to a TMS |
| Reports, moderation, DSA statements, stats | In-house | n/a | n/a |
| Fraud signals: card fingerprint | Stripe card fingerprint | Yes (`Provider.card_fingerprint`) | S |
| Fraud rules: velocity, held listings | In-house (settings) | n/a | n/a |
| Edge protection | AWS WAF (+ Bot Control in prod) | Infra only | M |
| Data export, account deletion | In-house fan-out over `/internal` | n/a | n/a |
| Web app shell, offline cache | vite-plugin-pwa (Workbox) | n/a | S |
| Store shells, push registration, deep links | Capacitor 8 plugins | `web/src/native.ts` | M |
| Feature flags, rollouts | In-house (`FEATURE_FLAGS` env) | Yes (`cappy_common/flags.py` + `web/src/domain/flags.ts`) | S |
| Kill switches | Settings via Terraform `switches` | Yes (settings) | n/a |
| Client crash reports | Gateway log line (`/api/client-errors`) | Yes (`reportClientError` / one endpoint) | S |
| Product analytics | SNS → Firehose → S3 → Athena | Infra only (subscription to the event topic) | M |
| Traces | OpenTelemetry → ADOT sidecar → X-Ray | Yes (OTLP) | S |
| Event bus | SNS + SQS (LocalStack locally, `memory://` in tests) | Yes (`Publisher` / `Consumer`) | M |

## Cross-cutting seams

These apply to several features below.

- **Provider selection is settings.** Every service reads its settings from the
  environment (`backend/libs/cappy_common/cappy_common/settings.py:23`). In
  `staging` and `prod` a service refuses to start when a setting is unsafe
  (`unsafe_reasons`, `settings.py:114`). Payments demands `PAYMENTS_PROVIDER=stripe`
  and notifications demands `MAILER=ses`. **A new provider must add its own
  `unsafe_reasons` checks**, or a fake can reach production.
- **Terraform wires the providers.** Environment per service is set in
  `infra/platform/ecs.tf:17-59`, secrets in `ecs.tf:70-78` (Stripe keys from
  the operator-filled secret `infra/platform/data.tf:154`), and IAM per task in
  `ecs.tf:206-216`.
- **Events decouple services.** The catalogue of event types is
  `backend/libs/cappy_common/cappy_common/events.py:52-82`. A provider swap that
  keeps the events the same (for example `payment.authorised`) touches only the
  service that owns the provider.
- **Local parity.** `compose.yaml` runs LocalStack Pro (S3, SNS, SQS, SES) and
  cognito-local. Stripe is either the fake provider or real test mode with the
  Stripe CLI forwarding webhooks (`compose.yaml:108-132`). A new provider needs
  a local fake or emulator here (ADR 0009). Nothing is applied to real AWS
  (GOAL 12).
- **Processors are legal work.** Every processor needs a DPA, an entry in the
  records of processing and a line in the privacy policy (G-B3, P-15, P-19,
  P-30). Swapping one is not done until that paperwork is.

---

## 1. Identity and accounts

### 1.1 Sign-up, email verification, sign-in, password reset

Members create an account with email and password, confirm the email with a
6-digit code, sign in and reset a forgotten password.

- **Where:** the web app talks to Cognito directly with `X-Amz-Target` JSON
  calls: `web/src/data/auth.ts:45` (`cognito()`), `signIn` `:228`
  (`USER_PASSWORD_AUTH`), `signUp` `:259`, `confirmSignUp` `:269`, `resendCode` `:272`,
  `forgotPassword` `:274`, `confirmForgotPassword` `:276`, `refresh` `:141`
  (`REFRESH_TOKEN_AUTH`). Screens: `web/src/app/screens/Login.tsx`,
  `Welcome.tsx`, `Onboarding.tsx`. Pool and client:
  `infra/platform/identity.tf:4` (email as username, password minimum 12
  characters with no composition rules, verification by code, TOTP MFA optional)
  and `:71` (public client, SRP and password flows, token revocation, 60-minute
  access tokens, 30-day refresh tokens, `prevent_user_existence_errors`,
  writable attributes `email` and `locale` only).
  Cognito sends the code email through SES (`identity.tf:47`).
- **Token check in services:** every service verifies the access token itself:
  `backend/libs/cappy_common/cappy_common/auth.py:44` (`TokenVerifier`, RS256,
  issuer, expiry, `token_use`, `client_id`), and it keeps a last-known-good JWKS
  (`auth_jwks_fallback`, fetched at deploy: `identity.tf:104`). The gateway
  passes `Authorization` through and does not authenticate
  (`backend/services/gateway/gateway/main.py:33`).
- **Signed-in only (GOAL 13):** the catalog, matching and booking routers
  require a principal (`catalog/routes.py:31`, `matching/routes.py:36`). What is
  public: `/api/categories`, `/api/groups` and `/api/review-tags`, used by the
  welcome screen (`matching/routes.py:35`), `/media/*`, `POST /api/reports`,
  `/api/app-config`, `/api/client-errors` and the legal pages.
- **Seam:**
  - Backend: **yes.** `TokenVerifier` accepts any issuer with a JWKS and
    RS256 access tokens. It is selected by `AUTH_ISSUER`, `AUTH_JWKS_URL`,
    `AUTH_CLIENT_IDS` and `AUTH_JWKS_FALLBACK` (`settings.py:60-69`). Two
    Cognito-specific assumptions: `token_use == "access"` (`auth.py:136`) and
    `client_id` rather than `aud` (`auth.py:130,138`).
  - Web: **no.** `auth.ts` is the whole Cognito client. Nothing else in the
    app knows Cognito exists: screens call the functions `auth.ts` exports, and
    the rest of the app only asks it for the session and the access token.
- **Provider-specific data:** the Cognito `sub` is every person's id in every
  service (`owners.id`, `bookings.requester_id`, `payments.owner_id` and so on).
  Passwords, emails and `email_verified` live only in Cognito. No service copies
  the email (`notifications/settings.py:14`).
- **To swap it** (for example to Auth0, Okta CIC or Keycloak):
  1. Web: re-implement the exports of `web/src/data/auth.ts` (`signIn`,
     `signUp`, `confirmSignUp`, `resendCode`, `forgotPassword`,
     `confirmForgotPassword`, `refresh`, `accessToken`, `updateLocale`,
     `deleteAccount`, `signOut`, `useSession`). Keep the `staff` flag on the
     session.
  2. Backend: point `AUTH_ISSUER`, `AUTH_JWKS_URL` and `AUTH_CLIENT_IDS` at the
     new issuer. Relax the `token_use` and `client_id` checks in `auth.py:136-139`
     or make them configurable.
  3. **Data: keep the ids.** Every table keys people on the Cognito `sub`.
     Import users with their old `sub` as the new provider's user id (or as a
     custom claim mapped to `sub`), or migrate every `*_id` column in all five
     databases.
  4. Replace `CognitoDirectory` (see 12.2) and the staff-group check (1.3).
  5. Infra: remove `identity.tf`, add the new tenant. Remove the CSP
     `connect-src` entry for `cognito-idp` (`infra/platform/edge.tf:413`) and
     add the new origin. Drop the Cognito WAF (`identity.tf:121`) or replace it.
  6. Sign-up email: Cognito sends it through SES today; the new provider needs
     its own sender (SPF/DKIM for our domain).
  7. Local: replace cognito-local in `compose.yaml` and `local/bootstrap.py`.
  8. Tests: `cappy_common/tests/test_foundations.py` covers the verifier. The
     e2e (`local/e2e.py`) signs in through Cognito.
  9. Legal: DPA, data location (EU pool for EU users, ADR 0013 cell plan).
- **Status and limits:**
  - One user pool per cell. The code has one region (`eu-central-1`). The
    North America cell is M-21 and region switching in the app is M-22.
  - Email one-time codes are not built (U-14). Staff have no enforced MFA and
    the web sign-in cannot answer an MFA challenge (P-3, P-4).
  - Threat protection (compromised credentials, adaptive auth) is switched by
    `cognito_threat_protection` (`infra/platform/variables.tf:113`). It is on
    in prod (`infra/envs/prod/main.tf:69`) and off by default elsewhere.
  - On the web the refresh token is in `localStorage` (`auth.ts:87-110`). In
    the store shells it is in Capacitor Preferences, not the Keychain (U-17,
    V1-28, P-5).
  - Access tokens stay valid up to 60 minutes after sign-out or deletion (P-24).

### 1.2 Sessions: sign out, sign out everywhere, cross-tab sign-out

Signing out revokes this device's refresh token. "Sign out everywhere"
revokes every refresh token the person has and stops push to all their
devices.

- **Where:** `web/src/data/auth.ts:304` (`signOut`, which calls `RevokeToken`, or
  `GlobalSignOut` plus the API for "everywhere"). The API route is
  `backend/services/notifications/notifications/routes.py:176`
  (`POST /api/me/sign-out-everywhere`). It calls
  `Directory.sign_out_everywhere` (`notifications/mail.py:30`), which is
  `CognitoDirectory._sign_out` → `AdminUserGlobalSignOut` (`mail.py:73`), and
  then deletes the person's devices. The cross-tab sign-out listens for the
  `storage` event (`auth.ts:185`). Screen: `Profile.tsx`.
- **Seam:** yes, `Directory.sign_out_everywhere`.
- **To swap it:** implement it on the new directory (1.1). IAM:
  `cognito-idp:AdminUserGlobalSignOut` in `ecs.tf:213`.
- **Limits:** cognito-local does not support global sign-out, so locally only
  the devices go (`mail.py:74`). There are no per-user rate limits (P-12).

### 1.3 Staff role

Moderators and support reach `/admin` and the `/api/admin/*` routes.

- **Where:** `require_admin` (`backend/libs/cappy_common/cappy_common/auth.py:178`)
  checks that `cognito:groups` contains `admin`. The group is
  `infra/platform/identity.tf:113`, granted by hand. The web session's
  `staff` flag is read from the same claim (`auth.ts:121`). Screen:
  `web/src/app/screens/Admin.tsx`.
- **Seam:** **no.** The claim name is hard-coded in two places.
- **Smallest refactor:** a `STAFF_CLAIM` / `STAFF_VALUE` setting read by
  `require_admin`, and the same for the web in `auth.ts`.
- **Limits:** no MFA for staff (P-3). There is one role and no separation of
  duties.

### 1.4 App version gate

Store builds older than the minimum are asked to update.

- **Where:** `GET /api/app-config` (`backend/services/gateway/gateway/main.py:190`)
  returns `minVersion` and `latestVersion` from `APP_MIN_VERSION` and
  `APP_LATEST_VERSION` (`gateway/settings.py:34-35`). The app sends
  `X-App-Version` (`web/src/data/repo.ts:74`) and compares versions with
  `versionBelow` (`repo.ts:390`). CloudFront caches the answer
  (`infra/platform/edge.tf:494`).
- **Seam:** n/a (in-house).

---

## 2. Profiles and business identity

### 2.1 Profile, age confirmation, home district

A member gives a display name, says whether they are a person or a business,
picks a home district and confirms they are 18 or older.

- **Where:** `GET/PUT /api/me` (`backend/services/catalog/catalog/routes.py:297`, `:306`).
  The input is `ProfileIn` (`routes.py:126`); `adult` is required at creation
  and stored as `owners.adult_confirmed_at` (`catalog/tables.py:72`). The event
  `profile.created` is emitted at `routes.py:330`. Public profile:
  `GET /api/owners/{id}` (`routes.py:401`). Screens: `Onboarding.tsx` (the 18+
  checkbox is at `:106`), `Profile.tsx`.
- **Provider:** none. The `owners` table is in the catalog database.
- **Status and limits:**
  - Districts are the only notion of place (see 4.3). There is no country,
    address or time zone on a person.
  - The minimum age is one rule for every market. Age by market and category is
    M-38. The terms text and store questionnaires are still open (S-5).
  - `Owner.verified` (`cappy_common/models.py:133`) is **not** linked to
    identity verification. New profiles get `False` (`catalog/repository.py:330`),
    and only seed data sets it. A badge from the ID check is U-32.

### 2.2 Business identity (traders)

A business owner states its legal name, address, register number and VAT ID.
Renters see it on the listing and at checkout ("your contract is with…").

- **Where:** `BusinessIn` with VAT normalisation and a regex check
  (`catalog/routes.py:101-123`), stored in `owners.business` (JSON,
  `catalog/tables.py:70`). It is copied into the booking snapshot
  (`booking/routes.py:189`) and onto fee invoices (`payments/invoices.py:85-102`).
  Web: `web/src/app/components/BusinessFields.tsx` (also `TraderNote`).
- **Provider:** none. A German VAT ID must be `DE` and 9 digits; other EU
  prefixes are checked only by shape. There is no VIES lookup.
- **To add a checker** (VIES, HMRC, Swiss UID, CRA BN): put it behind a
  `validate_vat(country, id)` function called from `BusinessIn.normalised`. Make
  it tolerant of VIES downtime (accept and re-check later). Add per-country
  error texts. This is M-33.
- **Limits:** EU only. GB, CH, CA and US identifiers are rejected or not
  understood (M-33). KYBC is not built.

---

## 3. Listings and photos

### 3.1 Listings and idle windows

Owners list an asset in one of nine categories, with price, rules, photos, a
private hand-over address and the windows it is free. They can edit, pause,
resume and remove a listing.

- **Where:** catalog routes: `GET /api/me/listings` `routes.py:452`,
  `POST /api/listings` `:480` (idempotent; kill switch; suspension check;
  20 per day; a new owner's expensive listing is held), `PUT` `:516`,
  slots `:545`/`:559`, pause and resume `:577`/`:582`, delete `:587`,
  `GET /api/listings/{id}` `:406`. Validation (text limits, category mode,
  numeric bounds `_check_numbers` `:270`, photo ownership) is at `:223`.
  Categories, including their `dac7` tag, are in
  `backend/libs/cappy_common/cappy_common/categories.py`. Events:
  `listing.changed`. Screens: `AddListing.tsx`, `Earn.tsx`, `Listing.tsx`.
- **Private address:** the address is stored on `listings.address`
  (`catalog/tables.py:90`). Booking fetches it from `/internal/listings/{id}/handover`
  (`routes.py:713`) and shows it only in accepted, active, completed or disputed
  states (`booking/repository.py:70`).
- **Provider:** none (Postgres).
- **Status and limits:**
  - Prices are integers in minor units with no currency on the listing. The
    booking currency is hard-coded `"eur"` (`booking/routes.py:180`, column
    default `booking/tables.py:50`). Multi-currency is M-3 and M-4.
  - Listings have no time zone or coordinates, only a district (M-5, M-15). The
    address is free text (M-8).
  - The kill switch `ACCEPTING_LISTINGS` is at `catalog/settings.py:41`.

### 3.2 Saved listings

Members keep a shortlist.

- **Where:** `GET /api/saved`, `PUT/DELETE /api/saved/{id}` (`catalog/routes.py:640-661`).
  Web: `useSaveToggle` (`web/src/data/repo.ts:550`).
- **Provider:** none.

### 3.3 Photos

Owners upload photos. The server re-encodes each one to WebP, strips EXIF and
GPS, bounds its size and stores it under a content hash.

- **Where:**
  - Upload: `POST /api/uploads` (`catalog/routes.py:600`), with 100 per person
    per day and two decodes at a time.
  - Processing: `media.process` (`backend/services/catalog/catalog/media.py:46`,
    Pillow).
  - Storage: `MediaStore` (`media.py:77`), `S3Store` (`:116`), `DirectoryStore`
    (`:88`), chosen by `make_store` (`:154`). URLs come from `url_for` (`:160`).
  - Serving: CloudFront `/media/*` from S3 (`infra/platform/edge.tf:548`).
    Locally the catalog serves it (`routes.py:629`) through the gateway
    (`gateway/main.py:246`).
  - Cleanup: uploads never used on a listing are swept after a day
    (`catalog/jobs.py:20`). A file is deleted only when nobody holds it.
  - Web: `shrink` downsizes to 1600 px JPEG on the device
    (`web/src/app/photos.ts`); `uploadPhoto` (`repo.ts:533`).
- **Seam:** **yes,** `MediaStore` (`put`, `get`, `delete`), selected by
  `MEDIA_BUCKET` (S3) or `MEDIA_DIR` (local). `MEDIA_PUBLIC_BASE` sets the
  public URL prefix (`catalog/settings.py:16-29`).
- **Provider-specific data:** listing `photos` hold full URLs of the form
  `{MEDIA_PUBLIC_BASE}/media/<sha>.webp`. `media` rows hold only the name.
  `name_from_url` (`media.py:164`) accepts only URLs with the current prefix.
- **To swap it** (for example to Cloudflare R2, GCS or Cloudinary):
  1. Add a `MediaStore` subclass and a branch in `make_store`.
  2. Set `MEDIA_PUBLIC_BASE` to the new CDN origin.
  3. Data: copy `s3://<bucket>/media/*` across. If the URL prefix changes,
     rewrite `listings.photos` and booking evidence `photos`, or listings with
     old URLs will fail validation on their next edit (`routes.py:250-256`).
  4. Infra: the IAM statement at `ecs.tf:206`, the bucket in
     `infra/platform/storage.tf:10` and the CloudFront origin in `edge.tf:458`.
     Add the new origin to the CSP `img-src` (`edge.tf:412`).
  5. If the new service transforms images itself (Cloudinary, imgix), keep
     `media.process` anyway: it is the EXIF/GPS stripping and the bomb guard.
- **Limits:** no responsive sizes (U-40). No per-photo progress, retry or HEIC
  on the server (U-25). No duplicate detection (S-20).

### 3.4 CDN purge on take-down

When moderation removes a listing, its cached API answers are purged at once.

- **Where:** `moderation.purge` (`backend/services/catalog/catalog/moderation.py:228`)
  calls CloudFront `CreateInvalidation` through `aws_client` when
  `CDN_DISTRIBUTION_ID` is set (`catalog/settings.py:49`). IAM: `ecs.tf:207`.
- **Seam:** **no,** the call is inline.
- **Smallest refactor:** a `Cdn.purge(paths)` interface next to `MediaStore`,
  with CloudFront and no-op implementations chosen in `catalog/main.py`.

---

## 4. Search and matching

### 4.1 Requirement matching and ranking

A renter describes what they need (category, hours or quantity, when, how
far). Matching returns ranked offers with a quote.

- **Where:** matching service routes (`backend/services/matching/matching/routes.py`):
  `POST /api/matches` `:167`, `GET /api/browse/spotlight` `:180`,
  `GET /api/listings/{id}/offers` `:199`, `POST /api/quote` `:215`,
  `POST /api/feasibility` `:224`, internal `match-for-offer` `:233`.
  Candidates come from the catalog (`catalog/routes.py:667` →
  `repository.py:516`: nearest districts first, capped at `CANDIDATE_CAP` = 300).
  Busy windows come from booking (`booking/routes.py:575`). Search degrades
  without them if booking is down (`matching/routes.py:75`).
- **Ranking:** hand-tuned weights (`matching/domain/match.py:54`): price 0.3,
  soon 0.2, trust 0.3, near 0.2. Trust is cut by the owner's cancellation rate
  (`match.py:57`). This is explained on the ranking page (`Legal.tsx`, G-6).
- **Provider:** none.
- **Limits:** distance is between district centres, not points (M-5). The
  radius is in km only (M-18).

### 4.2 Free-text search

Searching listing titles and descriptions by keyword.

- **Where:** `GET /api/search` (`catalog/routes.py:434`, at least 3
  characters) → `CatalogRepository.search` (`catalog/repository.py:624`),
  a `lower(title|blurb) LIKE %q%` backed by a trigram index (see
  `catalog/tables.py:120` and the 0001 migration). Web: `useSearch`
  (`repo.ts:236`), `Browse.tsx`.
- **Seam:** **no.** The query is inside the repository.
- **Smallest refactor:** a `SearchIndex` protocol
  (`search(q, metro, category, cursor, limit) -> (ids, next)`), with the current
  SQL as the default implementation. Feed an external index (OpenSearch,
  Typesense, Algolia) from `listing.changed` events. The catalog already emits
  one on create, update, pause, resume, removal and approval
  (`routes.py:510,541,571,593`, `moderation.py:259,509`).
- **To swap it:** the refactor above, plus a consumer that indexes on
  `listing.changed` and a backfill command. Keep the "live and bookable
  owners only" filters (`repository.py:164`, `:631-633`). Add infra and IAM for
  the index. There is no relevance ranking today (newest first).
- **Limits:** no stemming, language analysis or typo tolerance; newest first.

### 4.3 Places and the map

Members pick a city and district. Browse shows a map of what is free nearby,
or a Europe view of cities.

- **Where:** reference table `districts` (name, city, metro, country,
  lat/lng: `catalog/tables.py:32`), loaded from seed data. Routes:
  `GET /api/districts`, `/api/cities`, `/api/districts/nearest`
  (`catalog/routes.py:374-395`, in-memory haversine `repository.py:252`,
  `catalog/geo.py`). The map is an in-house SVG projection with no tiles and no
  map library (`web/src/app/components/CapacityMap.tsx`). The district picker is
  `LocationPicker.tsx` and `DistrictSelect.tsx`. The browser's geolocation is
  not used.
- **Seam:** none, and **no provider**: there is no geocoder, no autocomplete and
  no tile service.
- **To add one** (Amazon Location, Google Maps, Mapbox): this is M-5 to M-7.
  Add `geography(Point)` and a time zone to listings. Put a `Geocoder`
  interface in the catalog, called when an address is saved. Store only
  storable results (`IntendedUse=Storage` on Amazon Location; Google's terms
  restrict caching). Snap public coordinates to about 500 m (M-6). A tile
  map in the web needs a CSP change (`edge.tf:405-420`) and a consent check if
  the tile host sets cookies. Legal: Google's terms require Google maps when
  Google geocoding results are shown.

---

## 5. Booking lifecycle

### 5.1 Request, accept, hand over, complete

A renter books a window. The card is authorised. The owner accepts or
declines within 24 hours (never past the start). Either side marks the
hand-over from 30 minutes before. The renter confirms completion, or the
system completes it 48 hours after the end.

- **Where:** booking service.
  - State machine as data: `backend/services/booking/booking/state.py:67`
    (`TRANSITIONS`), `:80` (`SYSTEM`).
  - Create: `POST /api/bookings` (`booking/routes.py:122`). Matching prices the
    window. It then checks the per-listing advisory lock, the Postgres
    exclusion constraint (ADR 0004, `booking/tables.py:5-7`), the
    `Idempotency-Key`, `MAX_UNPAID` (3) and 10 requests a day.
  - Payment start: `routes.py:258`. Actions: `routes.py:334-380`.
  - Sweeps (lapse, auto-complete, publish reviews): `booking/jobs.py:18`.
  - Every change writes `booking_transitions` and emits `booking.status_changed`
    (`booking/repository.py:172`).
  - Screens: `Listing.tsx`, `Bookings.tsx`, `BookingDetail.tsx`, `Earn.tsx`.
- **Provider:** none (Postgres). Money moves through section 7.
- **Settings:** `booking/settings.py`: `PAYMENT_TIMEOUT_MINUTES` 30,
  `ANSWER_WITHIN_HOURS` 24, `AUTO_COMPLETE_AFTER_HOURS` 48,
  `START_EARLY_MINUTES` 30, `MAX_UNPAID`, `MAX_REQUESTS_PER_DAY`, and the kill
  switch `ACCEPTING_BOOKINGS` (`:40`).
- **Limits:** EUR only (M-3). Cross-cell bookings are not refused (M-23). No
  extension or late return (S-12). No 3DS return into the store shells (U-7).

### 5.2 Cancellation, no-shows, disputes

Either side can cancel before the start, with a refund preview. Either side
can report a no-show in the first two hours. The renter can dispute once the
window has started. Staff resolve a dispute by paying the owner or refunding
the renter.

- **Where:** `_transition` (`booking/routes.py:285`, no-show windows
  `:304-317`), refund preview `GET /api/bookings/{id}/cancellation` (`:433`),
  admin resolution `POST /api/admin/bookings/{id}/resolve` (`:493`) and its
  internal twin (`:501`). Screens: `BookingDetail.tsx`, `Admin.tsx`.
- **Provider:** none. The refund is carried as `refundAmount` on
  `booking.status_changed` and executed by payments (7.1).
- **Limits:** no dispute negotiation between the parties or deadlines (S-21). No
  owner damage claim (S-8), which needs a saved card or deposit first (S-9).

### 5.3 Hand-over evidence photos

Both sides can add check-in and check-out photos to a booking.

- **Where:** `POST/GET /api/bookings/{id}/evidence` (`booking/messages.py:236`,
  `:265`). The photos must be the person's own uploads, checked by catalog
  `/internal/media/evidence` (`catalog/routes.py:694`), and are never swept.
  Web: `web/src/app/components/Evidence.tsx`.
- **Seam:** storage goes through the catalog's `MediaStore` (3.3).
- **Limits:** the photos are public CloudFront URLs with unguessable names
  (P-27). There is no prompt at start and end, and no damage window (U-33).

### 5.4 Blocks

A member blocks another: no messages and no new bookings between them, in
either direction.

- **Where:** `PUT/DELETE/GET /api/me/blocks` (`booking/messages.py:193-212`),
  enforced in `create_booking` (`booking/routes.py:156`) and `send`
  (`messages.py:136`).
- **Provider:** none.

---

## 6. Instant book, policies and discounts

### 6.1 Instant book

An owner lets bookings confirm as soon as the card is authorised.

- **Where:** `Listing.instant_book` (`cappy_common/models.py:163`), copied into
  the booking snapshot (`booking/routes.py:190`). On `payment.authorised` the
  system action `authorised_instant` moves the booking straight to `accepted`
  (`booking/handlers.py:55-58`, `state.py:83`). The owner is told with the
  `instant_booked` notification (`notifications/handlers.py:70`). Form:
  `AddListing.tsx:221`.
- **Provider:** none.

### 6.2 Cancellation policies

Flexible, moderate or strict refunds for a renter who cancels an accepted
booking.

- **Where:** `booking/cancellation.py:17` (`refund_share`), used by `_refund`
  (`booking/routes.py:227`). The policy is on the listing
  (`models.py:167`) and in the booking snapshot.
- **Switches, two of them:** the backend applies moderate or strict only when
  `PAID_CANCELLATION_POLICIES=true` (`booking/settings.py:37`); otherwise every
  booking is flexible. The web shows the stricter terms to renters only when the
  feature flag `paidCancellationPolicies` is on (`Listing.tsx:67`, via
  `FEATURE_FLAGS`). **Both must be switched together.**
- **Limits:** off until counsel confirms against the EU withdrawal right
  (G-B2, S-19). The same rules apply in every market; US and Canadian wording is
  M-19.

### 6.3 Duration discounts

The owner sets a day rate (from 8 hours) and a week rate (from 40 hours),
taken off the hourly base.

- **Where:** `matching/domain/pricing.py:34` (`duration_discount`), with fields
  `day_discount_pct` and `week_discount_pct` (0 to 50, `models.py:170-171`).
  Form: `AddListing.tsx:223-224`.
- **Provider:** none.

### 6.4 Platform fee

A 15% fee sits inside the total the renter pays.

- **Where:** `PLATFORM_FEE_BPS = 1500` (`matching/domain/pricing.py:14`). It is
  computed in `quote_for` (`:45`) and carried as `ownerNet` to payments.
- **Limits:** one fee for every market and category. A per-market fee is M-2.

---

## 7. Payments, payouts and refunds

### 7.1 Card authorisation, capture, release and refund

The renter's card is authorised when they book, captured when the owner
accepts, released if the booking never happens, and refunded (in full or in
part) if it is cancelled after capture.

- **Where:**
  - Intent: booking calls payments `POST /internal/intents`
    (`booking/clients.py:82` → `payments/routes.py:111`). One intent per
    booking, idempotent. No database connection is held while Stripe answers.
    The owner must be payable (ADR 0005).
  - Card form: Stripe Payment Element, loaded only at the pay step
    (`web/src/app/components/PayStep.tsx:4,27`, `confirmPayment` `:47`).
    `GET /api/payments/config` (`payments/routes.py:191`) tells the app which
    provider and publishable key to use. The app skips the card step when the
    provider is `fake` (`Listing.tsx:199`).
  - Money follows booking events: `payments/handlers.py:53`. On accepted it
    captures; on declined, cancelled, expired or payment_failed it cancels the
    hold; on cancelled after capture it refunds `refundAmount`; on completed it
    transfers (7.2). The events it emits are `payment.captured`,
    `payment.refunded`, `payment.failed` and `payment.payout_sent`.
  - Webhooks: `POST /api/payments/webhooks/stripe` (`payments/routes.py:332`),
    deduplicated by Stripe event id in `processed_events`.
    `payment_intent.amount_capturable_updated` marks the payment authorised,
    which emits `payment.authorised` with the card fingerprint.
  - Reconciliation: `payments/jobs.py:29` looks up intents still `created`
    after 10 minutes, every 5 minutes.
- **Seam:** **yes,** `Provider` (`backend/services/payments/payments/provider.py:39`):
  `create_intent`, `client_secret`, `intent_status`, `capture`, `cancel`,
  `refund`, `transfer`, `card_fingerprint`, `create_account`,
  `onboarding_link`, `account_status`, `verification_session`,
  `parse_webhook`, `aclose`, plus the `authorises_immediately` flag and
  `Declined`. Implementations: `StripeProvider` (`:73`) and `FakeProvider`
  (`:200`). It is selected by `make_provider` (`:264`) from `PAYMENTS_PROVIDER`
  (`payments/settings.py:16`, `fake` or `stripe`; deployed environments demand
  `stripe`, `:42`).
- **Config:** `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` and
  `STRIPE_WEBHOOK_SECRET` from Secrets Manager (`ecs.tf:76-78`,
  `data.tf:154`), and `STRIPE_API_BASE` for stripe-mock contract tests
  (`payments/tests/test_stripe_contract.py`).
- **Provider-specific data** (`backend/services/payments/payments/tables.py`):
  - `payments.intent_id` (`pi_…`), `charge_id` (`ch_…`), `transfer_id`
    (`tr_…`) and `refund_id` (`re_…`).
  - `payments.card_fingerprint`, copied to `bookings.card_fingerprint`.
  - `payments.status`, whose vocabulary mirrors ours, not Stripe's.
  - `processed_events.event_id` (`evt_…`).
  - Stripe metadata `bookingId`, `requesterId` and `ownerId`, and
    `transfer_group = booking id`.
  - Idempotency keys `intent-`, `capture-`, `cancel-`, `refund-` and
    `transfer-{bookingId}`.
- **Stripe assumptions outside the provider:**
  - The webhook handler's event names and object shapes (`routes.py:347-379`).
  - The reconciliation job compares against the Stripe statuses
    `requires_capture` and `canceled` (`jobs.py:47,53`).
  - The `FAKE_ACCOUNT_PREFIX` logic (`routes.py:143`).
  - The web `PayStep` and the Stripe.js identity modal.
  - The CSP `script-src`, `connect-src`, `frame-src` and `img-src` entries for
    Stripe (`edge.tf:407-414`).
  - The WAF exemptions for `/api/payments/webhooks/` (`edge.tf:174-180`,
    `:232`, `:308`).
  - The chargeback log alarm (`infra/platform/observability.tf:134`).
  - The operator command `payments.cli demo-payouts` (`payments/cli.py:48`, test
    keys only).
- **To swap it** (for example to Adyen for Platforms, or Mangopay):
  1. Code: an `AdyenProvider(Provider)` and a branch in `make_provider`. Widen
     `PAYMENTS_PROVIDER` and `unsafe_reasons`. Map the provider's statuses to
     Stripe's words in `intent_status`, or change `jobs.py` to use our own
     vocabulary.
  2. Webhooks: a new route (for example `/payments/webhooks/adyen`). Keep the
     `processed_events` deduplication. Map the notifications (authorisation,
     capture failure, chargeback, account status, KYC) onto the same calls:
     `_authorised`, `_update_account`, `_verified` and `chargeback_at`. The
     gateway already routes `/api/payments/*`. Add the path to the WAF
     exemptions and the `stripe-signature`-style header to the gateway's
     forwarded headers (`gateway/main.py:33-43`).
  3. Web: replace `PayStep.tsx` with the provider's drop-in. Extend
     `/payments/config` with what the drop-in needs. Update the CSP.
  4. Data: in-flight bookings are tied to Stripe intents. Drain them first
     (switch off new bookings with `ACCEPTING_BOOKINGS=false`, let captures,
     refunds and transfers finish), or run both providers side by side with a
     `provider` column on `payments` and `connect_accounts`. **Connected
     accounts cannot be migrated**: owners onboard again with the new
     provider's KYC.
  5. Infra: a new secret, the IAM `read_secrets` entry (`ecs.tf:184-195`) and
     the alarm pattern.
  6. Tests: the fake keeps working. Add a contract test like
     `test_stripe_contract.py` against the new provider's sandbox.
  7. Legal: the platform agreement, DPA, the payment-services licence position
     (who holds funds), the terms' payment clause, and the privacy policy.
- **Status and limits:**
  - Separate charges and transfers, with no `on_behalf_of`.
  - One Stripe platform for all markets. Accounts are created without a
    country (`provider.py:171`; M-9). A client per platform is M-10.
  - EUR only (M-3, M-39).
  - No saved card or deposit (S-9). No 3DS return into the shells (U-7).
  - The kill switch is `PAYOUTS_ON` (7.2).

### 7.2 Owner onboarding and payouts

An owner sets up payouts on a Stripe-hosted page and is paid their share when
a booking completes, or their share of what was kept after a late
cancellation.

- **Where:**
  - `POST /api/payments/connect/onboarding` (`payments/routes.py:208`, Express
    account plus account link) and `GET /api/payments/connect/status` (`:224`).
  - `account.updated` webhook (`:353`) → `payment.payouts_ready` →
    catalog `payable_owners` (`catalog/handlers.py:24`). Buyers only see
    listings of payable owners when `REQUIRE_PAYABLE_OWNERS=true` (required
    deployed, `catalog/settings.py:38,57`).
  - Transfers happen in `payments/handlers.py:119-142` (completed) and
    `:88-115` (the owner's share of a late cancellation).
  - Screen: `Earn.tsx:110`.
- **Seam:** yes, the same `Provider` (`create_account`, `onboarding_link`,
  `account_status`, `transfer`).
- **Provider-specific data:** `connect_accounts.account_id` (`acct_…`; the fake
  uses `acct_fake_…`, `provider.py:31`). Stripe keeps the identity and bank
  details; Cappy never sees them.
- **To swap it:** as 7.1. Owners must onboard again. Keep `payment.payouts_ready`
  as the only thing the catalog knows.
- **Limits:**
  - Kill switch `PAYOUTS_ON` (`payments/settings.py:26`, Terraform
    `switches.payouts`): payouts wait on the queue with backoff and nothing is
    lost.
  - A chargeback holds the payout (`handlers.py:116`).
  - Payout currency and FX are M-39. The Connect bank-account fingerprint is not
    read (S-17 note).

### 7.3 Chargebacks

A card holder's dispute with their bank holds the owner's payout and pages
support.

- **Where:** `charge.dispute.created` (`payments/routes.py:369`) sets
  `payments.chargeback_at` and logs `CHARGEBACK`. The metric filter and alarm are
  in `infra/platform/observability.tf:134`.
- **Seam:** partial (Stripe event name and `obj["charge"]`).
- **Limits:** `charge.dispute.closed` is not handled; support settles by hand
  (runbook). There is no evidence submission.

---

## 8. Invoices and tax

### 8.1 Fee invoices to owners

Each payout (or kept late-cancellation fee) issues an invoice for Cappy's
fee. Numbers have no gaps per year, and an invoice never changes once issued.

- **Where:** `issue` (`backend/services/payments/payments/invoices.py:55`,
  under a row lock on `invoice_counters`), `GET /api/payments/invoices` (`:155`,
  with a `description` line) and `GET /api/payments/invoices/{number}` (`:164`,
  printable HTML in German with § 14 (4) UStG fields). Tables `invoices` and
  `invoice_counters` (`payments/tables.py:59-89`). Screen: `Earn.tsx:414`.
- **Seam:** partial. `Issuer` (`invoices.py:33`) makes the time zone, tax rate
  and label data (`INVOICE_TIME_ZONE`, `INVOICE_TAX_RATE_BPS`,
  `INVOICE_TAX_LABEL`, `payments/settings.py:34-36`). The issuer's name, address
  and tax ids are `LEGAL_*` (`:29-32`, Terraform `legal`, required deployed).
  The template, language and number series are code.
- **To swap it** (for example to an invoicing service or Stripe Invoicing): call
  it from `issue` and store its invoice id on `invoices`. Keep the local number
  series if the provider cannot guarantee gapless per-entity numbering. Keep the
  10-year retention (GoBD).
- **Limits:**
  - One issuing entity for everyone. The per-market entity, template and series
    are M-13.
  - Dates are in `Europe/Berlin` by default.
  - A private owner's invoice carries only their name.
  - No e-invoice format (2027 obligation in Germany).

### 8.2 VAT, sales tax and platform reporting

- **What exists:** the fee is treated as including 19% German VAT for every
  owner (`invoices.py:3-6`, `Issuer.tax_rate_bps`). Each category carries a
  DAC7 activity tag (`cappy_common/categories.py:29`). Nothing else exists: no
  tax engine, no reverse charge, OSS, UK/CH VAT, US sales tax or GST/HST/QST,
  and no DAC7, 1099-K or Canadian reports.
- **Seam:** **no.** The rate is one setting.
- **Smallest refactor:** a `tax_for(owner, market, fee) -> (rate_bps, scheme,
  legal_note)` function called by `issue`, stored per invoice line. Its first
  implementation is the current fixed rate. Stripe Tax, Avalara or a rules table
  plug in behind it (M-12). Reporting is planned through Stripe Connect platform
  tax reporting (G-10, S-31, M-14, M-26); it collects TIN and date of birth in
  onboarding.
- **Limits:** counsel must confirm the VAT treatment (G-B2). BZSt registration
  is G-B4. US and CA prices before tax at checkout are M-25.

---

## 9. Identity verification

A renter proves who they are once (government ID and a live selfie) before a
booking above €300, or in categories configured for it.

- **Where:**
  - Gate: `create_booking` returns 403 `verification_required` when
    `total > VERIFY_ABOVE_CENTS` (30 000) or the category is in
    `VERIFY_CATEGORIES` (`booking/routes.py:160-164`, `booking/settings.py:33-34`)
    and the person is not in `verified_people`.
  - Session: `POST /api/payments/identity/session` (`payments/routes.py:253`),
    which calls `Provider.verification_session` (`provider.py:161`: type
    `document`, matching selfie, live capture, metadata `personId`), and
    `GET /api/payments/identity` (`:274`).
  - Result: webhooks `identity.verification_session.verified` and
    `.requires_input` (`routes.py:360-368`) → `payment.identity_verified` →
    booking `verified_people` (`booking/handlers.py:112`).
  - Web: `Listing.tsx:217-239` loads Stripe.js on demand, calls
    `stripe.verifyIdentity(clientSecret)`, and polls for the webhook's result
    for up to a minute before retrying the booking.
- **Seam:** partial. Creating a session is behind `Provider`. The web modal
  and the webhook are Stripe's.
- **Provider-specific data:** `identities.session_id` (`vs_…`; fake `vs_fake_…`),
  `status` (`pending`, `requires_input`, `verified`) and `verified_at`
  (`payments/tables.py:47`). The document and selfie stay with Stripe; Cappy
  stores only the outcome.
- **To swap it** (for example to Onfido or Veriff):
  1. Code: move ID checks out of the payments `Provider` into their own
     `IdentityProvider` (`start(person_id) -> (session_id, client_token_or_url)`,
     `parse_webhook`). It is the smallest clean seam, and it lets payments stay
     on Stripe. Keep `payment.identity_verified` as the event, or rename it to an
     identity-neutral name in `events.py` and every subscriber (booking, and the
     SNS filter in `infra/modules/messaging/main.tf`).
  2. Webhook: a new route. Match on the session id, not on metadata alone (P-28).
  3. Web: replace the `verifyIdentity` call in `Listing.tsx` with the vendor's
     SDK or hosted link. The shells may need camera permission strings (S-2).
     Update the CSP.
  4. Data: existing `verified_people` rows stay valid. The `identities` rows
     point at Stripe sessions; keep them as history.
  5. Legal: a DPIA (G-B3), explicit consent for biometric data, recorded before
     the check (P-17, P-18), the vendor's DPA and its data location.
- **Limits:**
  - The verified name is not compared with the profile (P-28).
  - No badge on the profile (U-32; `Owner.verified` is unrelated, see 2.1).
  - Consent is a web checkbox only; it is not stored against the session (P-18).
  - The €300 threshold is one for every market.

---

## 10. Messaging and masking

Renter and owner message each other on a booking. Before acceptance, phone
numbers, emails, links, IBANs and messenger handles are masked. Afterwards
both sides see what was written. Asking to pay outside Cappy is flagged, and
the app warns both sides.

- **Where:** `backend/services/booking/booking/messages.py`: `mask` `:69`,
  `flagged` `:65`, `POST /api/bookings/{id}/messages` `:121` (idempotent,
  blocks enforced, the original kept in `unmasked`),
  `GET /api/bookings/{id}/messages` `:168` (unmasked once the booking is in
  `SHOWS_HANDOVER`). The event `booking.message` becomes a push to the other side,
  never an email (`notifications/handlers.py:76`). Web:
  `web/src/app/components/Conversation.tsx` (sender warning `:43`, receiver
  banner `:109`).
- **Seam:** module boundary. `mask(text)` and `flagged(text)` are pure
  functions. A moderation API (for example Hive, or a text classifier) would sit
  behind them.
- **Limits:**
  - The phone rule is European-shaped (`+`, `00` or `0` prefixes). NANP numbers
    without a prefix slip through (M-32).
  - English and German phrases only.
  - Messages can be sent in any booking state, with no per-user limit (P-12).
  - After a cancellation, messages are masked again (`messages.py:102`).

---

## 11. Reviews

After a completed booking the renter rates the listing and owner (stars,
on-time, tags, text), and the owner rates the renter. Reviews are blind: both
are published together once both are in, or when the 14-day window closes.

- **Where:**
  - Rating routes: `POST /api/bookings/{id}/rate` (`booking/routes.py:394`) and
    `/rate-renter` (`:448`).
  - Blind publishing: `publish_reviews` (`booking/repository.py:313`) and the
    sweep `reviews_due` (`:347`).
  - Events: `booking.rated` → catalog review plus the owner's record
    (`catalog/handlers.py:30`), and `booking.renter_rated` → the renter's record
    (`:20`).
  - Reads: `GET /api/listings/{id}/reviews` (`catalog/routes.py:425`) and the
    summary in the listing detail. Tags: `/api/review-tags`
    (`matching/domain/reviews.py`).
  - Web: `web/src/app/components/Reviews.tsx`, `BookingDetail.tsx`.
- **Provider:** none.
- **Limits:** no collusion signals (S-28). No in-app store review prompt (S-27).
  Reviewers are shown as "First L."; deleted accounts as "Former member".

---

## 12. Notifications (email, push, inbox, settings)

### 12.1 Email

Transactional email for booking changes, payouts, reports and moderation
decisions, in the recipient's language.

- **Where:** `backend/services/notifications/notifications/handlers.py`
  (`messages` `:39`, `moderation_mail` `:105`, `deliver` `:128`). Texts:
  `texts.py:11` (EN/DE), chosen by Cognito's `locale` (`texts.py:104`). Sender:
  `Mailer` (`mail.py:34`), `SesMailer` (`:93`, SES v1 `SendEmail`, plain text),
  `LogMailer` (`:111`). Selected in `notifications/main.py:26` by `MAILER`
  (`log` or `ses`; deployed must be `ses`, `settings.py:12,27`) and `MAIL_FROM`.
  Always-emailed kinds are in `prefs.py:58`.
- **Seam:** **yes,** `Mailer.send(Email(to, subject, text))`.
- **Provider-specific data:** none stored. Bounces and complaints are handled
  by SES's account suppression list (`infra/platform/email.tf:50`), with alarms
  (`:54`, `:68`).
- **To swap it** (for example to Postmark or SendGrid):
  1. Code: a `PostmarkMailer(Mailer)` using `httpx` and a `MAILER` value. Add
     its `unsafe_reasons` (API key present).
  2. Config and secret: the API key in Secrets Manager, wired in `ecs.tf`
     `secrets`.
  3. Suppression: move the SES suppression list across and handle the new
     provider's bounce webhooks, or bounced addresses get mailed again.
  4. DNS: DKIM, SPF and the return path for the new provider. `email.tf` today
     has SES DKIM, MAIL FROM and DMARC. Remove `ses:SendEmail` from the
     notifications role (`ecs.tf:212`).
  5. Cognito's own emails (codes, resets) still go through SES
     (`identity.tf:47`) unless Cognito is swapped too, so SES may stay.
  6. Local: LocalStack SES today. Use `LogMailer` or the provider's sandbox.
  7. Legal: DPA. Mail is sent from the EU region today.
- **Limits:**
  - Plain text only; no templates or HTML.
  - Two languages. French and the rest are M-17 and M-34.
  - Deadlines are told in `Europe/Berlin` unless the event carries a
    `timeZone` (`texts.py:129`), and listings have none yet (M-15).
  - No marketing mail, so no unsubscribe handling (M-30).

### 12.2 Recipient directory

Who to write to: a person's verified email and locale, looked up at send
time and never copied.

- **Where:** `Directory` (`notifications/mail.py:21`), `CognitoDirectory` (`:38`,
  `AdminGetUser` with a `ListUsers` fallback; only verified emails are used).
  IAM: `ecs.tf:213`.
- **Seam:** yes. It is replaced together with identity (1.1).

### 12.3 Push

Every notification that emails (except moderation) is also pushed to the
person's signed-in phones. Chat messages are push-only.

- **Where:**
  - Devices: `POST/DELETE /api/notifications/devices` (`notifications/routes.py:35`,
    `:56`), at most 10 per person, in the `devices` table (token, platform,
    endpoint: `tables.py:21`).
  - Sending: `Pusher` (`push.py:15`), `SnsPusher` (`:38`, SNS Mobile Push
    `CreatePlatformEndpoint` and `Publish` with APNS and FCM v1 payloads carrying a
    `link`), `LogPusher` (`:23`). Selected in `notifications/main.py:27-28`: SNS
    when `PUSH_IOS_APP_ARN` or `PUSH_ANDROID_APP_ARN` is set
    (`settings.py:20-21`, Terraform `push_app_arns`, `variables.tf:119`).
  - Dead endpoints are forgotten (`handlers.py:175`).
  - App side: `enablePush` and `pushSignedOut` (`web/src/native.ts:82`, `:120`,
    with `@capacitor/push-notifications`), the priming sheet
    `web/src/app/components/PushPrime.tsx`, and tap-to-open with the `link`
    (`native.ts:57-61`).
- **Seam:** **yes,** `Pusher.register(platform, token) -> endpoint` and
  `Pusher.send(endpoint, title, body, link) -> alive`.
- **Provider-specific data:** `devices.endpoint` holds SNS endpoint ARNs.
  `devices.token` holds the native token: the APNs device token on iOS and the
  FCM registration token on Android.
- **To swap it** (for example to OneSignal, Expo or direct FCM):
  1. Code: a `OneSignalPusher(Pusher)`. `register` can return the provider's
     subscription id as the endpoint. Branch in `main.py:27`.
  2. App: if the provider needs its own SDK (OneSignal does), replace
     `@capacitor/push-notifications` in `native.ts` and send the provider's id
     as `token`. Direct FCM on both platforms needs Firebase on iOS as well.
  3. Data: `devices.endpoint` values are SNS ARNs. Re-register on the next app
     start, which already happens after sign-in, or clear the table.
  4. Infra: remove the SNS platform-endpoint IAM statements (`ecs.tf:215-216`)
     and the platform applications (runbook). Add a secret for the provider key.
  5. Shells: Android needs `google-services.json` (not in the repo;
     `web/android/app/build.gradle:50-55`). iOS has `aps-environment`
     `development` in `web/ios/App/App/App.entitlements`, which must be
     `production` for release.
  6. Legal: APNs, FCM and the new vendor are processors; US transfer (P-19).
- **Limits:** re-registering a token moves it to the new user without proof of
  the previous install (P-33). No web push.

### 12.4 Inbox (the bell)

A paginated list of everything a person was notified about, with an unread
count, rendered in the reader's language.

- **Where:** `InboxRow` (`notifications/tables.py:33`, text key plus params),
  written by `_keep` (`handlers.py:194`). `GET /api/notifications`
  (`routes.py:107`, uses `Accept-Language`, which the gateway forwards at
  `gateway/main.py:37`) and `POST /api/notifications/read` (`:149`). Screen:
  `web/src/app/screens/Notifications.tsx`. The bell is in `AppShell.tsx`.
- **Provider:** none.

### 12.5 Notification settings

Per category (bookings, messages, payouts, marketing), push and email on or
off. Marketing is off by default. Contract and moderation emails are always
sent.

- **Where:** `notifications/prefs.py` (`DEFAULTS` `:37`, `CATEGORY` `:47`,
  `wanted` `:76`), `GET/PUT /api/notifications/settings` (`routes.py:134`,
  `:139`), table `notification_prefs`. Screen: `Profile.tsx`.
- **Provider:** none.
- **Limits:** there is no consent record for marketing (M-30). The messages
  email switch changes nothing, because messages are never emailed.

---

## 13. Trust and safety

### 13.1 Reports (DSA Art. 16)

Anyone can report a listing, profile, message or review with a reason,
details and a good-faith confirmation. People without an account leave an
email. Every report is acknowledged by email.

- **Where:** `POST /api/reports` (`backend/services/catalog/catalog/moderation.py:137`),
  public, idempotent when signed in. Limits: 3 a day per anonymous email, and 20
  a day per target. The event `moderation.report_received` becomes an email.
  Web: `web/src/app/components/Report.tsx`, `sendReport` (`repo.ts:632`).
- **Provider:** none. No CAPTCHA.
- **Limits:** the per-target cap can turn genuine reports away. Anonymous
  addresses are not confirmed (P-7). `reporterEmail` travels in events into the
  analytics lake (P-6).

### 13.2 Moderation queue and decisions (DSA Art. 17)

Staff see open reports oldest first, dismiss, take down a listing or suspend
an owner, with a structured statement of reasons. Both sides are told, and
every action is audited.

- **Where:** `moderation.py`: queue `:206`, decide `:324`, take-down `:388`,
  suspend `:410`, reinstate `:433`, audit `:448`, statement of reasons
  `:104`. The event `moderation.decision` goes to notifications
  (`statement_params`, `notifications/handlers.py:90`). `moderation.owner_suspended`
  goes to booking, which declines the owner's pending requests and blocks new
  bookings by them (`booking/handlers.py:95`). Screen:
  `web/src/app/screens/Admin.tsx`.
- **Provider:** none. There is no automated content classifier. `automated`
  in the statement is always what staff say.

### 13.3 Held listings (fraud rule)

A new owner's listing above €100 an hour waits for a staff check.

- **Where:** `create_listing` and `update_listing` (`catalog/routes.py:504`,
  `:535`), `REVIEW_ABOVE_CENTS` (`catalog/settings.py:46`), and admin
  `GET /api/admin/listings/held` and `POST .../approve` (`moderation.py:477`,
  `:498`).
- **Provider:** none.

### 13.4 System notices: reliability and ban evasion

- **Owner reliability (S-18):** booking counts an owner's cancellations and
  no-shows over 12 months (`booking/repository.py:188`). It emits
  `booking.owner_reliability`, which becomes `owners.cancellation_rate`, a
  ranking signal (4.1), shown on the listing. Three failures in 30 days emit
  `moderation.person_flagged`, which joins the queue (`moderation.py:517`).
- **Linked cards (S-17):** payments reads the card fingerprint on
  authorisation (`payments/routes.py:99`, `Provider.card_fingerprint`). Booking
  compares it with cards used by suspended accounts
  (`booking/handlers.py:63`) and flags the person. The booking still goes ahead.
- **Seam:** the fingerprint is behind `Provider.card_fingerprint`. A new payment
  provider must supply a stable per-card fingerprint, or this signal goes dark.
- **Limits:** no bank-account fingerprint, no device fingerprint, no
  duplicate-photo detection (S-20).

### 13.5 Velocity limits and card testing

- **Where:** 10 booking requests a day and at most 3 unpaid bookings
  (`booking/settings.py:27-29`, `routes.py:145-148`). 20 new listings a day
  (`catalog/settings.py:45`). 100 photos a day (`catalog/settings.py:29`).
- **Edge:** AWS WAF per-IP rate rule, IP reputation, and Bot Control in prod
  (`infra/platform/edge.tf:171`, `:263`; `bot_control`, `variables.tf:107`,
  on in `infra/envs/prod/main.tf:85`). A separate WAF sits on Cognito
  (`identity.tf:121`). Stripe webhooks are exempt from rate and bot rules and
  are protected by their signatures.
- **Seam:** infra only. Swapping the WAF (for example to Cloudflare) is a
  Terraform change plus the webhook exemptions.
- **Limits:** no per-user limits in the gateway (`gateway/settings.py:40-42`,
  P-12).

### 13.6 DSA transparency numbers

- **Where:** `GET /api/admin/dsa-stats?month=` (`moderation.py:556`): notices by
  reason and decision, median hours to decision, and active recipients from
  booking `/internal/stats/active-people` (`booking/routes.py:530`). The exact
  count is an Athena query (`docs/analytics.md`).
- **Provider:** none.

---

## 14. Privacy (export, deletion)

### 14.1 Data export (GDPR Art. 15/20)

A member downloads one JSON file with everything held about them.

- **Where:** `GET /api/me/export` (`catalog/routes.py:359`) gathers the
  catalog's part (`repository.py:194`) and each service's `/internal/people/{id}/export`:
  booking (`booking/routes.py:550`), payments (`payments/routes.py:295`) and
  notifications (`notifications/routes.py:159`). Web: `exportMyData`
  (`repo.ts:405`). In the store shells it goes to the share sheet
  (`native.ts:136`).
- **Provider data not included:** anything held by Stripe (cards, KYC, ID
  documents) and Cognito (the email). The export says so only implicitly.
- **Limits:** no per-user rate limit (P-12). No CCPA or Law 25 request workflow
  (P-29).

### 14.2 Account deletion

A member deletes their account in the app or at `/account/delete` (Google
Play). It is refused while bookings are open or a payout is pending, with the
reason and a date.

- **Where:** `DELETE /api/me` (`catalog/routes.py:337`). It checks booking
  `/internal/people/{id}/open` (`booking/routes.py:519`) and payments
  `/internal/people/{id}/open` (`payments/routes.py:283`), then
  `repository.forget` (`catalog/repository.py:171`: listings down, the profile
  becomes "Former member", reviews anonymised). `profile.deleted` goes to:
  - booking: blocks and verification go, messages are redacted
    (`booking/handlers.py:117`);
  - payments: the Connect link and identity row go (`payments/handlers.py:151`);
  - notifications: devices, inbox and settings go (`notifications/handlers.py:157`).
  The app then calls Cognito `DeleteUser` (`web/src/data/auth.ts:281`).
  Screens: `Profile.tsx`, `App.tsx:55` (`/account/delete`).
- **Provider data:** the Stripe Connect account stays with Stripe, which keeps
  what financial regulation requires. Invoices are kept for 10 years.
- **Limits:** if the app never calls `DeleteUser`, the Cognito user (and the
  email) remains. `AdminDeleteUser` on `profile.deleted` is P-23. Booking
  snapshots keep the owner's name (P-23).

---

## 15. The app shell (PWA and Capacitor)

### 15.1 Web app and PWA

- **Where:** React 19 and Vite. The PWA comes from `vite-plugin-pwa` with
  auto-update (`web/vite.config.ts:64`): the app shell is cached and the API is
  never cached. Routes are in `web/src/app/App.tsx` (signed-out routes `:52-57`,
  signed-in `:145-161`). The welcome screen is shown once per device
  (`device.ts`).
- **Hosting:** S3 plus CloudFront in AWS. Locally the gateway can serve
  `web/dist` (`gateway/main.py:251`).
- **Fonts:** self-hosted through `@fontsource-variable` (`web/src/main.tsx:5-6`).
- **Languages:** English and German (`web/src/i18n.ts`, `Lang = 'en' | 'de'`).
  A French catalogue exists (`web/src/i18n.fr.ts`) but is not wired into
  `i18n.ts` yet (M-16, M-17).
- **Limits:** no route-level code splitting (S-15). No Web Vitals (S-23). No
  axe checks in CI (U-30).

### 15.2 Store shells (Capacitor)

The same build ships in the App Store and Google Play.

- **Where:** `web/capacitor.config.ts` (appId `app.cappy`), `web/ios`,
  `web/android`, and `web/src/native.ts`. Plugins used: `app`, `preferences`,
  `push-notifications`, `filesystem`, `share` (`web/package.json`).
  - Storage: `nativeStore` (`native.ts:13`, Capacitor Preferences) holds the
    refresh token and the device flags.
  - Android back button: `native.ts:52`.
  - iOS privacy manifest: `web/ios/App/App/PrivacyInfo.xcprivacy`.
- **Seam:** `native.ts` is the only file that imports Capacitor. Everything
  there is a no-op on the web.
- **To swap** (for example to React Native): the web app would be rewritten.
  Out of scope for a provider swap.
- **Limits:**
  - The token is not in the Keychain or Keystore (U-17).
  - No CSP inside the shells (P-5). Release builds are not minified (P-31).
  - No keyboard plugin (U-26). Android 16 edge-to-edge is unchecked (S-14).
  - Building and signing need Xcode and Android Studio with store credentials.

### 15.3 Deep links

Universal Links and App Links open `/listing/*`, `/bookings/*` and `/earn*` in
the app. Notification taps open their `link`.

- **Where:** the build emits `.well-known/apple-app-site-association` and
  `assetlinks.json` from `VITE_APPLE_TEAM_ID` and `VITE_ANDROID_SHA256`
  (`web/vite.config.ts:25-55`). The `appUrlOpen` listener is at `native.ts:49`.
  The iOS associated domain is `applinks:cappy.example` in `App.entitlements`,
  a placeholder (P-31).
- **Provider:** none (no Branch or Firebase Dynamic Links).

### 15.4 Offline and drafts

- **Offline:** `useOnline` and `OfflineBar` (`web/src/app/components/Offline.tsx`).
  Money actions are disabled offline (`PayStep.tsx:63`). Reads are served from
  the React Query cache.
- **Drafts:** `drafts` (`web/src/app/device.ts:47`, `localStorage`). The listing
  form keeps its whole state (`AddListing.tsx:188,246`). Drafts are cleared on
  sign-out (`device.ts:67`).
- **Retries:** the client honours `Retry-After` and backs off
  (`web/src/data/repo.ts:109`, `:197`), and refreshes once on a 401 (`:88`).
- **Provider:** none.

---

## 16. Operations

### 16.1 Feature flags and rollouts

- **Where:** `FEATURE_FLAGS="name:percent,…"` (`gateway/settings.py:37`,
  Terraform `feature_flags`, `variables.tf:101`). They are parsed by
  `backend/libs/cappy_common/cappy_common/flags.py:15` and served in
  `/api/app-config` as `flags` (100 means on) and `rollouts` (0 < percent < 100)
  (`gateway/main.py:190-205`, cached by CloudFront for 5 minutes). The app places
  each user with FNV-1a (`web/src/domain/flags.ts`, `useFlag` `repo.ts:383`;
  check: `npm run check:flags`). A service can enforce a flag with
  `flags.enabled` (`flags.py:32`).
- **Seam:** **yes.** Two small modules and one endpoint.
- **To swap it** (for example to LaunchDarkly, Unleash or ConfigCat): keep
  `useFlag(name)` as the web API. Back it with the vendor's SDK, or have the
  gateway fetch flags from the vendor into the same `app-config` shape. Mind
  that the vendor's per-user evaluation breaks the CDN cache of `app-config`,
  and that a client SDK is a new third-party script before consent (§ 25 TDDDG;
  CSP).
- **In use:** `paidCancellationPolicies` (6.2).

### 16.2 Kill switches

Stop new bookings, stop payouts or stop new listings without a deploy.

- **Where:** `ACCEPTING_BOOKINGS` (`booking/settings.py:40`), `PAYOUTS_ON`
  (`payments/settings.py:26`) and `ACCEPTING_LISTINGS` (`catalog/settings.py:41`),
  set from Terraform `switches` (`variables.tf:86`, `ecs.tf:39,43,46`). How to use
  them is in `docs/runbook.md`.
- **Seam:** settings. A task restart is needed (new task definition).

### 16.3 Client crash reports

- **Where:** `POST /api/client-errors` (`gateway/main.py:209`): 8 KB at most, 10
  a minute per address, logged and never stored. It is sent from the
  `ErrorBoundary`, `window.onerror` and `unhandledrejection`
  (`web/src/app/components/ErrorBoundary.tsx`, `web/src/main.tsx:12-13`,
  `reportClientError` `repo.ts:363`).
- **Seam:** yes. `reportClientError` is the one client call site.
- **To swap it** (for example to Sentry): call the Sentry SDK from
  `reportClientError` (or keep the endpoint and forward from the gateway, which
  avoids a third-party script). Upload source maps per release. No replay or
  device id without consent. Add Sentry's ingest host to the CSP `connect-src`.
  DPA.
- **Limits:** the per-address key is forgeable, and messages may carry
  personal data (P-34). No source maps.

### 16.4 Product analytics

- **Where:** every domain event goes SNS → Firehose → S3 (2 years, cold after 90
  days) and can be queried in Athena as `cappy_events`
  (`infra/platform/analytics.tf`, `docs/analytics.md`). There is no client SDK.
- **Seam:** infra only (an SNS subscription).
- **To swap it** (for example to Segment, Amplitude or BigQuery): add a
  subscriber to the events topic that forwards to the vendor. Filter personal
  data out of events first (P-6).
- **Limits:** no Web Vitals or client events (S-23).

### 16.5 Logs and traces

- **Where:** JSON logs with request ids (`cappy_common/observability.py`).
  OpenTelemetry over OTLP to an ADOT sidecar and on to X-Ray, when
  `OTEL_ENABLED=true` (`observability.py:148`, `settings.py:93-94`). Trace
  context travels inside events (`events.py:119-121`). Alarms, SLOs and a
  synthetic canary are in `infra/platform/observability.tf`, `synthetics.tf` and
  `docs/slo.md`.
- **Seam:** yes, OTLP. Swap to Datadog, Honeycomb or Grafana by pointing
  `OTEL_ENDPOINT` at their collector, or by changing the sidecar.

### 16.6 Event bus

- **Where:** a transactional outbox per service. `Publisher`, `SnsPublisher`,
  `Consumer` and `SqsConsumer` are in `cappy_common/events.py:205,436,462`,
  selected by `EVENT_BUS_URL` (`memory://` or `sns://…`) and `EVENT_QUEUE_URL`
  (`events.py:545`). Queues, DLQs and filters are in
  `infra/modules/messaging/main.tf`.
- **Seam:** yes. Swapping to EventBridge, Kafka or Pub/Sub means a new
  `Publisher` and `Consumer` pair and a URL scheme. Consumers are already
  idempotent (`processed_events`).

---

## Features with no seam today

The provider is called directly, or the logic has no module boundary. The
smallest refactor that would create one:

| Feature | Called directly at | Smallest refactor |
|---|---|---|
| Web sign-in, sign-up, reset, refresh (Cognito) | `web/src/data/auth.ts` (whole module) | Treat `auth.ts`'s exports as the interface. Move the Cognito `fetch` calls behind an `AuthProvider` object in the same file, so a second implementation can be picked by `VITE_AUTH_PROVIDER` |
| Staff role (Cognito group claim) | `cappy_common/auth.py:181`, `web/src/data/auth.ts:121` | `STAFF_CLAIM` and `STAFF_VALUE` settings |
| CDN purge (CloudFront) | `catalog/moderation.py:228` | A `Cdn.purge(paths)` interface beside `MediaStore`, chosen in `catalog/main.py` |
| Free-text search (Postgres LIKE/trigram) | `catalog/repository.py:624` | A `SearchIndex` protocol with the current SQL as the default, fed by `listing.changed` |
| Places and geocoding (none exists) | `districts` table, `catalog/repository.py:252` | A `Geocoder` interface when addresses become structured (M-5, M-7, M-8) |
| Tax on the fee (fixed rate) | `payments/invoices.py:83` (`Issuer.tax_rate_bps`) | A `tax_for(owner, market, fee)` function per invoice line (M-12) |
| Stripe webhook event handling | `payments/routes.py:332-379` | Have `Provider.parse_webhook` return neutral events (`authorised`, `account_changed`, `identity_verified`, `chargeback`) instead of Stripe's event dict |
| Identity verification UI (Stripe.js modal) | `web/src/app/screens/Listing.tsx:217-239` | An `IdentityProvider` in payments, split from the payment `Provider`, with the session returning either a client secret or a hosted URL |
| Card form (Stripe Payment Element) | `web/src/app/components/PayStep.tsx` | Already one component. Pick it by `/payments/config.provider` |

## How to keep this file true

This is a living doc (CLAUDE.md, "Living docs — keep them true"). Any commit
that changes what it says updates it **in the same commit**, builders and
agents included. That means a feature added or removed, a provider added or
swapped, a new setting that selects a provider, provider-specific data
stored, a webhook added, or a task id closed.

- Describe the code as committed, not the plan. Planned work is a task id from
  `TASKS.md`.
- Keep the summary table and the "no seam" table in step with the sections.
- Check `path:line` references when the code they point at moves.
- A decision to change a provider is a new ADR (`docs/adr/`), not a silent
  edit here. This file then records the result.
