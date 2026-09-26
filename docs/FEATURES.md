# Features and their provider seams

Every feature Cappy has today, where it lives, and what replacing its
provider with another third party takes. It describes the **committed code**,
not the plan: planned work appears only as task ids from
[`TASKS.md`](TASKS.md). Markets are all of Europe, the US and Canada
([GOAL 16](GOAL.md), [ADR 0013](adr/0013-markets.md)). Where the code
assumes one market (German tax, Berlin time, EU-shaped rules), this file
says so. Last synced at `c454c92` (the code as of `7ef9b2c`, covering
`44a5520` and `235eeaa`).

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
| Sign-up, sign-in (with a TOTP code step), password reset | Amazon Cognito (the web app calls it directly) | Yes. Backend: any OIDC issuer/JWKS. Web: `AuthProvider` (`web/src/data/cognito.ts`, since `f22f143`) | L (the data and the users move; the code seam is S) |
| Token verification in services | Cognito JWKS, RS256, plus an in-house not-before check per person (`revoked_sessions`) | Yes (`TokenVerifier`; the revocation check is provider-neutral) | S |
| Sign out everywhere | In-house revocation (`person.signed_out`) plus Cognito `AdminUserGlobalSignOut` | Yes (`Directory.sign_out_everywhere`) | S |
| Staff role and staff MFA | Cognito group `admin` (`cognito:groups` claim) by default; TOTP MFA checked with Cognito `AdminGetUser` | Role: yes since `235eeaa` (`STAFF_CLAIM`, `STAFF_VALUE`, F-3). MFA: no (`StaffMfa` calls Cognito) | S |
| Profiles, business identity, VAT ID check | In-house (regex, no VIES) | n/a (no provider) | S to add VIES |
| Listings, windows, saved | In-house (Postgres) | n/a | n/a |
| Photo storage | S3 + CloudFront (listing photos), S3 private prefix (hand-over evidence); Pillow re-encode | Yes (`MediaStore`, public and private instances) | S |
| CDN purge on take-down | CloudFront `CreateInvalidation` | Yes (`Cdn`, `catalog/cdn.py`, since `235eeaa`, F-4) | S |
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
| Identity verification | Stripe Identity (document + selfie) | Backend: yes (`IdentityProvider`, `payments/identity.py`, its own webhook route, since `235eeaa`, F-1). Web: no (the Stripe.js modal, whatever `identityProvider` says) | M |
| Messaging, contact masking, pay-outside flag | In-house regex | Module boundary (`mask`, `flagged`) | S |
| Blocks | In-house | n/a | n/a |
| Hand-over evidence photos | In-house: catalog's private media store, booking's signed links | Yes (via `MediaStore`) | S |
| Reviews (two-way, blind) | In-house | n/a | n/a |
| Email | Amazon SES (v1 `SendEmail`) | Yes (`Mailer`) | S |
| Recipient email and locale | Cognito `AdminGetUser` | Yes (`Directory`) | S |
| Push | SNS Mobile Push → APNs / FCM v1 | Yes (`Pusher`), but tokens are APNs/FCM-native | M |
| Inbox (bell), notification settings | In-house | n/a | n/a |
| Email/push texts, languages | In-house (`texts.py`, EN/DE/FR since `235eeaa`) | n/a | M to a TMS |
| App texts, money and distance formats | In-house (`web/src/i18n.ts`, EN/DE/FR catalogues; `Intl` for money, units and plurals) | n/a | M to a TMS |
| Reports, moderation, DSA statements, stats | In-house | n/a | n/a |
| Fraud signals: card fingerprint | Stripe card fingerprint | Yes (`Provider.card_fingerprint`) | S |
| Fraud rules: velocity, held listings | In-house (settings) | n/a | n/a |
| Edge protection | AWS WAF (+ Bot Control in prod) | Infra only | M |
| Data export, account deletion | In-house fan-out over `/internal`; deletion also removes the Cognito user (`AdminDeleteUser`), the Stripe Identity session (redact) and SNS endpoints; a register of personal data with a test (`cappy_common/privacy.py`) | n/a | n/a |
| Web app shell, offline cache | vite-plugin-pwa (Workbox) | n/a | S |
| Store shells, push registration, deep links | Capacitor 8 plugins | `web/src/native.ts` | M |
| Feature flags, rollouts | In-house (`FEATURE_FLAGS` env) | Yes (`cappy_common/flags.py` + `web/src/domain/flags.ts`) | S |
| Kill switches | Settings via Terraform `switches` | Yes (settings) | n/a |
| Client crash reports | Gateway log line (`/api/client-errors`), emails and phone numbers scrubbed | Yes (`reportClientError` / one endpoint) | S |
| Product analytics | SNS → Firehose (Lambda allowlist scrub) → S3 → Athena | Infra only (subscription to the event topic) | M |
| Service-to-service auth | In-house per-service tokens, checked by hash (`INTERNAL_CALLERS`) | n/a | n/a |
| Traces | OpenTelemetry → ADOT sidecar → X-Ray | Yes (OTLP) | S |
| Event bus | SNS + SQS (LocalStack locally, `memory://` in tests) | Yes (`Publisher` / `Consumer`) | M |

## Cross-cutting seams

These apply to several features below.

- **Provider selection is settings.** Every service reads its settings from the
  environment (`backend/libs/cappy_common/cappy_common/settings.py:23`). In
  `staging` and `prod` a service refuses to start when a setting is unsafe
  (`unsafe_reasons`, `settings.py:148`). Payments demands `PAYMENTS_PROVIDER=stripe`
  and refuses `IDENTITY_PROVIDER=fake`, and notifications demands `MAILER=ses`. **A new provider must add its own
  `unsafe_reasons` checks**, or a fake can reach production.
- **Terraform wires the providers.** Environment per service is set in
  `infra/platform/ecs.tf:13-76`, secrets in `ecs.tf:77-88` (Stripe keys from
  the operator-filled secret `infra/platform/data.tf:169`), and IAM per task in
  `ecs.tf:206-228`.
- **Events decouple services.** The catalogue of event types is
  `backend/libs/cappy_common/cappy_common/events.py:50-100`. A provider swap that
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
6-digit code, sign in and reset a forgotten password. An account with TOTP MFA
on (every staff account, when deployed) is asked for the authenticator code at
sign-in.

- **Where:** the web app talks to Cognito directly with `X-Amz-Target` JSON
  calls, all in `web/src/data/cognito.ts` (the `cognito` `AuthProvider`,
  `:123-207`; the transport `call`, `:69`): `signIn` `:124`
  (`USER_PASSWORD_AUTH`), `answerMfa` `:131` (`RespondToAuthChallenge`
  `SOFTWARE_TOKEN_MFA`), `refresh` `:139` (`REFRESH_TOKEN_AUTH`), `signUp`
  `:153`, `confirmSignUp` `:163`, `resendCode` `:166`, `forgotPassword` `:169`,
  `confirmForgotPassword` `:172`. `web/src/data/auth.ts` keeps the session,
  storage and tabs and calls the provider (`signIn` `:225`, `answerMfa`
  `:229`, `refresh` `:123`). Screens:
  `web/src/app/screens/Login.tsx` (mode `mfa` is the code step),
  `Welcome.tsx`, `Onboarding.tsx`. Pool and client:
  `infra/platform/identity.tf:4` (email as username, password minimum 12
  characters with no composition rules, verification by code, TOTP MFA optional)
  and `:71` (public client, SRP and password flows, token revocation,
  15-minute access and ID tokens, 30-day refresh tokens,
  `prevent_user_existence_errors`, writable attributes `email` and `locale`
  only). Cognito sends the code email through SES (`identity.tf:47`).
- **Token check in services:** every service verifies the access token itself:
  `backend/libs/cappy_common/cappy_common/auth.py:45` (`TokenVerifier`, RS256,
  issuer, expiry, `token_use`, `client_id`), and it keeps a last-known-good JWKS
  (`auth_jwks_fallback`, fetched at deploy: `identity.tf:107`). Services with
  a database then refuse a token issued before the person's last
  sign-out-everywhere or deletion (401 `token_expired`, `auth.py:168-174`,
  `cappy_common/guard.py`, P-24). The gateway passes `Authorization` through
  and does not authenticate (`backend/services/gateway/gateway/main.py:34`).
- **Signed-in only (GOAL 13):** the catalog, matching and booking routers
  require a principal (`catalog/routes.py:32`, `matching/routes.py:36`). What is
  public: `/api/categories`, `/api/groups` and `/api/review-tags`, used by the
  welcome screen (`matching/routes.py:35`), `/media/*`, `POST /api/reports`,
  `/api/app-config`, `/api/client-errors`, the legal pages, and hand-over
  photo links, which carry their own 15-minute signature (5.3).
- **Seam:**
  - Backend: **yes.** `TokenVerifier` accepts any issuer with a JWKS and
    RS256 access tokens. It is selected by `AUTH_ISSUER`, `AUTH_JWKS_URL`,
    `AUTH_CLIENT_IDS` and `AUTH_JWKS_FALLBACK` (`settings.py:66-75`). Two
    Cognito-specific assumptions: `token_use == "access"` (`auth.py:137`) and
    `client_id` rather than `aud` (`auth.py:131,139`). The revocation check
    needs only `sub` and `iat`.
  - Web: **yes** since `f22f143` (F-2): `AuthProvider`
    (`web/src/data/cognito.ts:24-43`: sign-in, the MFA answer, refresh,
    identity from tokens, sign-up and codes, TOTP setup, locale, delete, revoke,
    sign out everywhere). `auth.ts:18` picks `cognito`. Nothing else in the
    app knows Cognito exists.
- **Provider-specific data:** the Cognito `sub` is every person's id in every
  service (`owners.id`, `bookings.requester_id`, `payments.owner_id` and so on).
  Passwords, emails, `email_verified` and TOTP secrets live only in Cognito. No
  service copies the email (`notifications/settings.py:14-15`).
- **To swap it** (for example to Auth0, Okta CIC or Keycloak):
  1. Web: a second `AuthProvider` next to `cognito.ts`, chosen in
     `auth.ts:18`. `identity` must return the `staff` flag; an MFA step is
     `{ mfa }` from `signIn`, which `auth.ts` turns into the
     `SOFTWARE_TOKEN_MFA` error `Login.tsx` switches to the code step on.
  2. Backend: point `AUTH_ISSUER`, `AUTH_JWKS_URL` and `AUTH_CLIENT_IDS` at the
     new issuer. Relax the `token_use` and `client_id` checks in `auth.py:137-140`
     or make them configurable. Set `STAFF_CLAIM` and `STAFF_VALUE` to the new
    provider's staff claim (1.3). Replace `StaffMfa`.
  3. **Data: keep the ids.** Every table keys people on the Cognito `sub`.
     Import users with their old `sub` as the new provider's user id (or as a
     custom claim mapped to `sub`), or migrate every `*_id` column in all five
     databases. TOTP secrets cannot be exported: staff enrol again.
  4. Replace `CognitoDirectory` (see 12.2).
  5. Infra: remove `identity.tf`, add the new tenant. Remove the CSP
     `connect-src` entry for `cognito-idp` (`infra/platform/edge.tf:413`) and
     add the new origin. Drop the Cognito WAF (`identity.tf:124`) or replace it.
     Remove the `cognito-idp:*` task permissions (`ecs.tf:210`, `:223`).
  6. Sign-up email: Cognito sends it through SES today; the new provider needs
     its own sender (SPF/DKIM for our domain).
  7. Local: replace cognito-local in `compose.yaml` and `local/bootstrap.py`.
  8. Tests: `cappy_common/tests/test_foundations.py` covers the verifier. The
     e2e (`local/e2e.py`) signs in through Cognito and checks the user is
     deleted with the account.
  9. Legal: DPA, data location (EU pool for EU users, ADR 0013 cell plan).
- **Status and limits:**
  - One user pool per cell. The code has one region (`eu-central-1`). The
    North America cell is M-21 and region switching in the app is M-22.
  - Email one-time codes are not built (U-14). Staff MFA is enforced
    (**fixed in `f303350`**, P-3) and the web sign-in answers the TOTP
    challenge (**fixed in `f42a4ef`**, P-4). Members cannot turn MFA on: the
    setup screen is only in the staff console.
  - Threat protection (compromised credentials, adaptive auth) is switched by
    `cognito_threat_protection` (`infra/platform/variables.tf:113`). It is on
    in prod (`infra/envs/prod/main.tf:69`) and off by default elsewhere.
  - On the web the refresh token is in `localStorage` (`auth.ts:34-58`). In
    the store shells it is in Capacitor Preferences, not the Keychain (U-17,
    V1-28, P-5).
  - Access tokens last 15 minutes. After sign-out-everywhere or deletion,
    catalog refuses them at once and booking, payments and notifications as
    soon as the event arrives (**fixed in `f303350`**, P-24). Matching has no
    database and accepts them until they expire.

### 1.2 Sessions: sign out, sign out everywhere, cross-tab sign-out

Signing out revokes this device's refresh token. "Sign out everywhere"
ends every session the person has, revokes every refresh token and stops push
to all their devices.

- **Where:** `web/src/data/auth.ts:292` (`signOut`, which calls `RevokeToken`, or
  `GlobalSignOut` plus the API for "everywhere"; a 429 is shown with the
  server's reason). The API route is catalog's
  `POST /api/me/sign-out-everywhere`
  (`backend/services/catalog/catalog/routes.py:377-395`, moved from
  notifications in `f303350`): at most 5 an hour (`rate_hits`, P-12), it
  records the person in catalog's `revoked_sessions` and publishes
  `person.signed_out`. Booking, payments and notifications record the same
  (`cappy_common/guard.py:58-77`). Notifications then calls
  `Directory.sign_out_everywhere` (`notifications/mail.py:30`), which is
  `CognitoDirectory._sign_out` → `AdminUserGlobalSignOut` (`mail.py:76`), and
  deletes the person's devices, each SNS endpoint first
  (`notifications/handlers.py:208-213`, `push.py:85-94`, D-7). On
  another device, a request refused with 401 `token_expired` even after a
  refresh ends the session there (`web/src/data/repo.ts:100`, `endSession`
  `auth.ts:85`). The cross-tab sign-out listens for the `storage` event
  (`auth.ts:188`). Screen: `Profile.tsx`.
- **Seam:** yes, `Directory.sign_out_everywhere`. The revocation itself is
  in-house.
- **To swap it:** implement it on the new directory (1.1). IAM:
  `cognito-idp:AdminUserGlobalSignOut` in `ecs.tf:223`.
- **Limits:** cognito-local does not support global sign-out, so locally only
  the devices go and the tokens are refused (`mail.py:77`).

### 1.3 Staff role and staff MFA

Moderators and support reach `/admin` and the `/api/admin/*` routes.

- **Where:** `require_admin` (`backend/libs/cappy_common/cappy_common/auth.py:229`)
  checks that the token is staff and, wherever
  `ADMIN_MFA_REQUIRED` holds (always when deployed; a deployed service refuses
  to start with it false: `settings.py:161-163`), that the account has TOTP MFA
  on. Staff means the claim `STAFF_CLAIM` holds `STAFF_VALUE` (a list claim
  or a space-separated string), `cognito:groups` and `admin` by default
  (`is_staff`, `auth.py:222-226`; `settings.py:108-109`; since `235eeaa`,
  F-3). Booking's evidence route uses the same check (`booking/messages.py:310`).
  `StaffMfa` (`auth.py:186-219`) asks Cognito `AdminGetUser` for
  `UserMFASettingList`, caches the answer 5 minutes per person, and answers
  503 when Cognito cannot say. Without MFA a staff call gets 403
  `mfa_required`. IAM: `cognito-idp:AdminGetUser` for catalog and booking
  (`ecs.tf:210`, `:217`, `:219`). The group is
  `infra/platform/identity.tf:116`, granted by hand. The web session's
  `staff` flag is read from the same claim (`cognito.ts:148-152`). Screen:
  `web/src/app/screens/Admin.tsx`: on `mfa_required` it shows the TOTP setup
  (`TotpSetup`, `:145`, with `startTotp` and `confirmTotp`, `auth.ts:247`,
  `:256`, over `cognito.ts:175-190`: `AssociateSoftwareToken`,
  `VerifySoftwareToken`, `SetUserMFAPreference`), an `otpauth://` link and the
  key, no QR code.
- **Seam:** the role, **yes** (two settings on the server; on the web the
  provider's `identity` sets `staff`). The MFA check, **no**: it calls Cognito
  directly.
- **Smallest refactor:** `StaffMfa` behind the `Directory`-style interface, or
  an `amr` claim check where the new provider puts one in the token.
- **Limits:** there is one role and no separation of duties. Turning MFA off
  takes up to 5 minutes to bite (the cache).

### 1.4 App version gate

Store builds older than the minimum are asked to update.

- **Where:** `GET /api/app-config` (`backend/services/gateway/gateway/main.py:210`)
  returns `minVersion` and `latestVersion` from `APP_MIN_VERSION` and
  `APP_LATEST_VERSION` (`gateway/settings.py:34-35`). The app sends
  `X-App-Version` (`web/src/data/repo.ts:82`) and compares versions with
  `versionBelow` (`repo.ts:421`). CloudFront caches the answer
  (`infra/platform/edge.tf:494`).
- **Seam:** n/a (in-house).

---

## 2. Profiles and business identity

### 2.1 Profile, age confirmation, home district

A member gives a display name, says whether they are a person or a business,
picks a home district and confirms they are 18 or older.

- **Where:** `GET/PUT /api/me` (`backend/services/catalog/catalog/routes.py:306`, `:315`).
  The input is `ProfileIn` (`routes.py:127`); `adult` is required at creation
  and stored as `owners.adult_confirmed_at` (`catalog/tables.py:77`).
  `country` (ISO 3166-1 alpha-2, default `DE`, since `235eeaa`, M-9) is stored
  on `owners.country`; the web does not send it yet. The event
  `profile.created` is emitted at `routes.py:340`. Public profile:
  `GET /api/owners/{id}` (`routes.py:448`). Screens: `Onboarding.tsx` (the 18+
  checkbox is at `:106`), `Profile.tsx`.
- **After a deletion:** the same sign-in (`sub`) signing up again gets a fresh
  profile: counters reset, `verified` and business cleared, 18+ asked again,
  and `profile.created` emitted; a suspension stays (FL-11,
  `catalog/repository.py:406-415`).
- **Provider:** none. The `owners` table is in the catalog database.
- **Status and limits:**
  - Districts are the only notion of place (see 4.3), plus the profile's
    `country`, which only sets the payout account's country (7.2). There is no
    address or time zone on a person.
  - The minimum age is one rule for every market. Age by market and category is
    M-38. The terms text and store questionnaires are still open (S-5).
  - `Owner.verified` (`cappy_common/models.py:137`) is set by a passed ID
    check since `235eeaa` (F-10): catalog handles `payment.identity_verified`
    (`catalog/handlers.py:84-90`). New profiles get `False`, and deletion
    clears it.

### 2.2 Business identity (traders)

A business owner states its legal name, address, register number and VAT ID.
Renters see it on the listing and at checkout ("your contract is with…").

- **Where:** `BusinessIn` with VAT normalisation and a regex check
  (`catalog/routes.py:102-124`), stored in `owners.business` (JSON,
  `catalog/tables.py:73`). It is copied into the booking snapshot
  (`booking/routes.py:190`) and onto fee invoices (`payments/invoices.py:95-112`).
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

- **Where:** catalog routes: `GET /api/me/listings` `routes.py:502`,
  `POST /api/listings` `:530` (idempotent; kill switch; suspension check;
  20 per day; a new owner's expensive listing is held), `PUT` `:566`,
  slots `:595`/`:609`, pause and resume `:627`/`:632`, delete `:637`,
  `GET /api/listings/{id}` `:453` (since `235eeaa` the owner can open their
  own held or paused listing; anyone else gets 404, FL-6). Validation (text
  limits, category mode, numeric bounds `_check_numbers` `:277`, photo
  ownership) is at `:226`.
  Categories, including their `dac7` tag, are in
  `backend/libs/cappy_common/cappy_common/categories.py`. Events:
  `listing.changed`. Screens: `AddListing.tsx`, `Earn.tsx`, `Listing.tsx`.
- **Private address:** the address is stored on `listings.address`
  (`catalog/tables.py:93`). Booking fetches it from `/internal/listings/{id}/handover`
  (`routes.py:779`) and shows it only in accepted, active, completed or disputed
  states (`booking/repository.py:70`).
- **Provider:** none (Postgres).
- **Status and limits:**
  - Prices are integers in minor units of the listing's `currency`, one of
    twelve ISO 4217 codes (EUR, GBP, CHF, SEK, NOK, DKK, PLN, CZK, HUF, RON,
    USD, CAD; default EUR; `cappy_common/models.py:156`, `:183`), since
    `235eeaa` (M-3). Quotes carry it upper-case and bookings lower-case
    (`booking/routes.py:181`); nothing is converted. The price bounds scale
    roughly with the currency (`catalog/routes.py:273-289`). The web formats
    and inputs money per currency (`formatMoney`, `currencySymbol`:
    `web/src/domain/money.ts`, M-4) and now gets the currency from the API.
  - Listings have no time zone or coordinates, only a district (M-5, M-15). The
    address is free text (M-8).
  - The kill switch `ACCEPTING_LISTINGS` is at `catalog/settings.py:41`.
  - Account deletion clears the listing's title, blurb, instructions, rules,
    photos and address; the row stays for bookings and reviews (D-2).

### 3.2 Saved listings

Members keep a shortlist.

- **Where:** `GET /api/saved`, `PUT/DELETE /api/saved/{id}` (`catalog/routes.py:698-720`).
  Web: `useSaveToggle` (`web/src/data/repo.ts:631`).
- **Provider:** none.

### 3.3 Photos

Owners upload photos. The server re-encodes each one to WebP, strips EXIF and
GPS, bounds its size and stores it under a content hash.

- **Where:**
  - Upload: `POST /api/uploads` (`catalog/routes.py:650`), with 100 per person
    per day and two decodes at a time. `?purpose=evidence` stores the file in
    the private store and answers `evidence:<name>` instead of a URL (5.3).
  - Processing: `media.process` (`backend/services/catalog/catalog/media.py:46`,
    Pillow).
  - Storage: `MediaStore` (`media.py:77`), `S3Store` (`:116`, key prefix
    `media/` or `private/`), `DirectoryStore` (`:88`), chosen by `make_store`
    (`:155`, `private=True` for evidence; catalog keeps one of each:
    `catalog/main.py:76`, `:78`). URLs come from `url_for` (`:177`).
  - Serving: CloudFront `/media/*` from S3 (`infra/platform/edge.tf:548`).
    Locally the catalog serves it (`routes.py:687`) through the gateway
    (`gateway/main.py:263`).
  - Cleanup: uploads never used on a listing are swept after a day, from both
    stores (`catalog/jobs.py:24-42`). A file is deleted only when nobody holds
    it. Since `235eeaa` an account deletion hands every photo of the person to
    the next sweep (D-1).
  - Web: `shrink` downsizes to 2048 px JPEG on the device and refuses HEIC
    with a reason where the browser cannot decode it (`web/src/app/photos.ts`);
    `uploadPhoto` (`repo.ts:576`, `purpose` `listing` or `evidence`) reports
    per-photo progress over XHR, and the
    listing form keeps a failed photo with a **Retry** button.
- **Seam:** **yes,** `MediaStore` (`put`, `get`, `delete`), selected by
  `MEDIA_BUCKET` (S3) or `MEDIA_DIR` (local). `MEDIA_PUBLIC_BASE` sets the
  public URL prefix (`catalog/settings.py:16-29`).
- **Provider-specific data:** listing `photos` hold full URLs of the form
  `{MEDIA_PUBLIC_BASE}/media/<sha>.webp`. `media` rows hold only the name.
  `name_from_url` (`media.py:181`) accepts only URLs with the current prefix.
- **To swap it** (for example to Cloudflare R2, GCS or Cloudinary):
  1. Add a `MediaStore` subclass and a branch in `make_store`.
  2. Set `MEDIA_PUBLIC_BASE` to the new CDN origin.
  3. Data: copy `s3://<bucket>/media/*` across. If the URL prefix changes,
     rewrite `listings.photos` and booking evidence `photos`, or listings with
     old URLs will fail validation on their next edit (`routes.py:250-256`).
  4. Infra: the IAM statement at `ecs.tf:215` (both prefixes), the bucket in
     `infra/platform/storage.tf:10` and the CloudFront origin in `edge.tf:458`.
     Add the new origin to the CSP `img-src` (`edge.tf:412`).
  5. If the new service transforms images itself (Cloudinary, imgix), keep
     `media.process` anyway: it is the EXIF/GPS stripping and the bomb guard.
- **Limits:** no responsive sizes (U-40). The server does not decode HEIC;
  the device converts it (Safari) or refuses it (U-25, done in `f42a4ef`). No
  duplicate detection (S-20).

### 3.4 CDN purge on take-down

When moderation removes a listing, its photos are purged from the CDN at
once. No listing page is cached at the edge (sign-in is required, GOAL 13);
its photos are, for a year.

- **Where:** `moderation.purge` (`backend/services/catalog/catalog/moderation.py:242-253`)
  collects the listing's own photo names (a foreign URL is not ours to purge)
  and calls `app.state.cdn.purge(["/media/<name>", …])`. `Cdn`
  (`backend/services/catalog/catalog/cdn.py`, since `235eeaa`, F-4) is a
  no-op; `CloudFrontCdn` calls `CreateInvalidation` and only logs a failure;
  `make_cdn` picks CloudFront when `CDN_DISTRIBUTION_ID` is set
  (`catalog/settings.py:52`, `catalog/main.py:77`). IAM: `ecs.tf:216`.
- **Seam:** **yes,** `Cdn.purge(paths)`.
- **To swap it** (Fastly, Cloudflare): a `Cdn` subclass, a branch in
  `make_cdn` and its setting and secret; the IAM statement goes.
- **Limits:** an account deletion does not purge the person's photos; they
  leave the edge when their cache expires.

---

## 4. Search and matching

### 4.1 Requirement matching and ranking

A renter describes what they need (category, hours or quantity, when, how
far). Matching returns ranked offers with a quote.

- **Where:** matching service routes (`backend/services/matching/matching/routes.py`):
  `POST /api/matches` `:167`, `GET /api/browse/spotlight` `:180`,
  `GET /api/listings/{id}/offers` `:199`, `POST /api/quote` `:215`,
  `POST /api/feasibility` `:224`, internal `match-for-offer` `:233`.
  Candidates come from the catalog (`catalog/routes.py:725` →
  `repository.py:613`: nearest districts first, capped at `CANDIDATE_CAP` = 300).
  Busy windows come from booking (`booking/routes.py:626`). Search degrades
  without them if booking is down (`matching/routes.py:75`).
- **Ranking:** hand-tuned weights (`matching/domain/match.py:54`): price 0.3,
  soon 0.2, trust 0.3, near 0.2. Trust is cut by the owner's cancellation rate
  (`match.py:57`). This is explained on the ranking page (`Legal.tsx`, G-6).
- **Provider:** none.
- **Limits:** distance is between district centres, not points (M-5). The
  API works in km; the web shows distances and radius presets in miles for
  US and GB locales and km elsewhere (`formatDistance`, `formatRadius`:
  `web/src/app/format.ts:77-97`), though the presets are still km values
  converted, not round miles (M-18). The unit follows the formatting locale.
  Since `44a5520` an English reader whose device has no English region of
  its own (not US, CA, GB and so on) is formatted as `en-IE`: km and 24 h
  (`web/src/i18n.ts:56-57`).

### 4.2 Free-text search

Searching listing titles and descriptions by keyword.

- **Where:** `GET /api/search` (`catalog/routes.py:484`, at least 3
  characters) → `CatalogRepository.search` (`catalog/repository.py:721`),
  a `lower(title|blurb) LIKE %q%` backed by a trigram index (see
  `catalog/tables.py:123` and the 0001 migration). Web: `useSearch`
  (`repo.ts:261`), `Browse.tsx`.
- **Seam:** **no.** The query is inside the repository.
- **Smallest refactor:** a `SearchIndex` protocol
  (`search(q, metro, category, cursor, limit) -> (ids, next)`), with the current
  SQL as the default implementation. Feed an external index (OpenSearch,
  Typesense, Algolia) from `listing.changed` events. The catalog already emits
  one on create, update, pause, resume, removal and approval
  (`routes.py:560,591,621,643`, `moderation.py:262,539`).
- **To swap it:** the refactor above, plus a consumer that indexes on
  `listing.changed` and a backfill command. Keep the "live and bookable
  owners only" filters (`repository.py:182-187`, `_live` `:471`). Add infra and IAM for
  the index. There is no relevance ranking today (newest first).
- **Limits:** no stemming, language analysis or typo tolerance; newest first.

### 4.3 Places and the map

Members pick a city and district. Browse shows a map of what is free nearby,
or a Europe view of cities.

- **Where:** reference table `districts` (name, city, metro, country,
  lat/lng: `catalog/tables.py:35`), loaded from seed data. Routes:
  `GET /api/districts`, `/api/cities`, `/api/districts/nearest`
  (`catalog/routes.py:421-445`, in-memory haversine `repository.py:339`,
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
  - Create: `POST /api/bookings` (`booking/routes.py:122`), in the listing's
    currency (`:181`, M-3). Matching prices the
    window. It then checks the per-listing advisory lock, the Postgres
    exclusion constraint (ADR 0004, `booking/tables.py:5-7`), the
    `Idempotency-Key`, `MAX_UNPAID` (3) and 10 requests a day.
  - Payment start: `routes.py:253`. Actions: `routes.py:341-389`.
  - Sweeps (lapse, auto-complete, publish reviews): `booking/jobs.py:18`.
  - Every change writes `booking_transitions` and emits `booking.status_changed`
    (`booking/repository.py:192-200`).
  - The owner sees a booking only once the card is held: never while it is
    `awaiting_payment`, nor one whose payment failed before they saw it; a
    capture declined after they accepted they do see (`_owner_sees`,
    `repository.py:97-110`, used by `visible` and the list; since `235eeaa`,
    FL-15).
  - Screens: `Listing.tsx`, `Bookings.tsx`, `BookingDetail.tsx`, `Earn.tsx`.
- **Provider:** none (Postgres). Money moves through section 7.
- **Settings:** `booking/settings.py`: `PAYMENT_TIMEOUT_MINUTES` 30,
  `ANSWER_WITHIN_HOURS` 24, `AUTO_COMPLETE_AFTER_HOURS` 48,
  `START_EARLY_MINUTES` 30, `MAX_UNPAID`, `MAX_REQUESTS_PER_DAY`, and the kill
  switch `ACCEPTING_BOOKINGS` (`:52`).
- **Limits:** one set of thresholds in minor units for every currency (M-2).
  Cross-cell bookings are not
  refused (M-23). No extension or late return (S-12). No 3DS return into the
  store shells (U-7).
- **Retries (FL-1, `f42a4ef`):** every create in the web (booking, listing,
  message, rating, evidence, report) takes its `Idempotency-Key` from
  `attemptKeys` (`web/src/domain/attempt.ts`, `useAttemptKey` `repo.ts:554-556`):
  the same body keeps its key after a 5xx, a timeout or a lost connection, and
  gets a new one after a success, a 4xx or a changed body
  (`npm run check:attempt`).

### 5.2 Cancellation, no-shows, disputes

Either side can cancel before the start, with a refund preview. Either side
can report a no-show in the first two hours. The renter can dispute once the
window has started. Staff resolve a dispute by paying the owner or refunding
the renter.

- **Where:** `_transition` (`booking/routes.py:291`, no-show windows
  `:310-323`), refund preview `GET /api/bookings/{id}/cancellation` (`:442`,
  with `charged`: false before the accept, when cancelling only releases the
  hold; FL-8, `235eeaa`), admin resolution `POST /api/admin/bookings/{id}/resolve`
  (`:504`) and its internal twin (`:512`). Screens: `BookingDetail.tsx`, `Admin.tsx`.
- **Provider:** none. The refund is carried as `refundAmount` on
  `booking.status_changed` and executed by payments (7.1). A cancellation
  before the accept records none (`routes.py:228-231`, `:326-328`;
  `cancellation.py:31-36` returns 0 when nothing was charged).
- **Notifications:** a dispute tells the owner ("A problem was reported") and
  the renter ("We received your report"), since `235eeaa` (FL-2).
- **Limits:** no dispute negotiation between the parties or deadlines (S-21). No
  owner damage claim (S-8), which needs a saved card or deposit first (S-9).

### 5.3 Hand-over evidence photos

Both sides can add check-in and check-out photos to a booking. They are
private to the two sides and staff.

- **Where:** `POST/GET /api/bookings/{id}/evidence` (`booking/messages.py:270`,
  `:299`). The photos must be the person's own uploads made with
  `POST /api/uploads?purpose=evidence`, which stores them under the private
  prefix and answers `evidence:<name>` (`catalog/routes.py:650-685`); catalog
  `/internal/media/evidence` (`catalog/routes.py:752-764`) accepts only such
  references and marks them never swept. `GET …/evidence` hands each photo out
  as `/api/bookings/{id}/evidence/{eid}/{i}?exp&sig`, an HMAC link valid 15
  minutes, keyed from booking's own internal token (`messages.py:335-370`);
  booking fetches the bytes from catalog `/internal/evidence/{name}`
  (`catalog/routes.py:767-771`) and serves them `private`. Staff with MFA see
  them too (`messages.py:307-312`, `is_staff`). Web: `web/src/app/components/Evidence.tsx`
  uploads with `purpose=evidence` (since `f22f143`), shows per-photo progress,
  and a retried save reuses photos already up and the same key. The list is
  read again every 10 minutes and after a lapsed link fails to load
  (`repo.ts` `useEvidence`, `Evidence.tsx` `renew`). Prompted at hand-over and
  hand-back (`BookingDetail.tsx` `evidencePrompt`), with the upload time and
  the report window ("at the latest 48 hours after it ends") shown (U-33).
- **Seam:** storage goes through the catalog's private `MediaStore` (3.3).
- **Limits:** evidence saved before `f303350` keeps its public URLs.

### 5.4 Blocks

A member blocks another: no messages and no new bookings between them, in
either direction.

- **Where:** `PUT/DELETE/GET /api/me/blocks` (`booking/messages.py:227-246`),
  enforced in `create_booking` (`booking/routes.py:156`) and `send`
  (`messages.py:141`). A report on a message offers **Block {name} too**
  right after it is sent (`Report.tsx`, U-13).
- **Provider:** none.

---

## 6. Instant book, policies and discounts

### 6.1 Instant book

An owner lets bookings confirm as soon as the card is authorised.

- **Where:** `Listing.instant_book` (`cappy_common/models.py:173`), copied into
  the booking snapshot (`booking/routes.py:191`). On `payment.authorised` the
  system action `authorised_instant` moves the booking straight to `accepted`
  (`booking/handlers.py:86-92`, `state.py:83`). The owner is told with the
  `instant_booked` notification (`notifications/handlers.py:71`). Form:
  `AddListing.tsx:222`.
- **Provider:** none.

### 6.2 Cancellation policies

Flexible, moderate or strict refunds for a renter who cancels an accepted
booking.

- **Where:** `booking/cancellation.py:18` (`refund_share`), used by `_refund`
  (`booking/routes.py:233`). The policy is on the listing
  (`models.py:177`) and in the booking snapshot.
- **One switch** (since `f303350`): the feature flag `paidCancellationPolicies`
  in `FEATURE_FLAGS`, which every service now receives (`ecs.tf:31`). Booking
  applies moderate or strict only when it is at 100; any partial rollout
  counts as off (`booking/settings.py:38-47`). Since `44a5520` the web reads it
  the same way, with `useGlobalFlag` (`repo.ts:416-418`, `Listing.tsx:70`):
  only a flag at 100 shows the stricter terms, so app and server agree.
- **Limits:** off until counsel confirms against the EU withdrawal right
  (G-B2, S-19). The same rules apply in every market; US and Canadian wording is
  M-19.

### 6.3 Duration discounts

The owner sets a day rate (from 8 hours) and a week rate (from 40 hours),
taken off the hourly base.

- **Where:** `matching/domain/pricing.py:34` (`duration_discount`), with fields
  `day_discount_pct` and `week_discount_pct` (0 to 50, `models.py:180-181`).
  Form: `AddListing.tsx:224-225`.
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
    (`booking/clients.py:89` → `payments/routes.py:121`). One intent per
    booking, idempotent. No database connection is held while Stripe answers.
    The owner must be payable (ADR 0005).
  - Card form: Stripe Payment Element, loaded only at the pay step
    (`web/src/app/components/PayStep.tsx:4,28`, `confirmPayment` `:48`; a
    redirect method returns to `/pay/return?booking=` on Cappy's own domain,
    which the store apps claim as an app link: `repo.ts:54`, `App.tsx`
    `PayReturn`, U-7); the
    component itself is a lazily loaded chunk (`React.lazy` in `Listing.tsx`
    and `BookingDetail.tsx`, S-15). `GET /api/payments/config`
    (`payments/routes.py:201`) tells the app which provider and publishable key
    to use, and since `235eeaa` which ID-check provider (`identityProvider`,
    section 9). The app skips the card step when the provider is `fake`
    (`Listing.tsx:203`).
  - Money follows booking events: `payments/handlers.py:59`. On accepted it
    captures; on declined, cancelled, expired or payment_failed it cancels the
    hold; on cancelled after capture it refunds `refundAmount`; on completed it
    transfers (7.2). The events it emits are `payment.captured`,
    `payment.refunded`, `payment.failed` and `payment.payout_sent`.
  - Webhooks: `POST /api/payments/webhooks/stripe` (`payments/routes.py:419`),
    deduplicated by Stripe event id in `processed_events`.
    `payment_intent.amount_capturable_updated` marks the payment authorised,
    which emits `payment.authorised` with the card fingerprint.
  - Reconciliation: `payments/jobs.py:29` looks up intents still `created`
    after 10 minutes, every 5 minutes.
- **Seam:** **yes,** `Provider` (`backend/services/payments/payments/provider.py:39`):
  `create_intent`, `client_secret`, `intent_status`, `capture`, `cancel`,
  `refund`, `transfer`, `card_fingerprint`, `create_account(owner_id,
  country)`, `onboarding_link`, `account_status`, `parse_webhook`, `aclose`,
  plus the `authorises_immediately` flag and `Declined`. ID checks left it for
  their own `IdentityProvider` in `235eeaa` (section 9). Implementations:
  `StripeProvider` (`:72`) and `FakeProvider` (`:194`). It is selected by
  `make_provider` (`:255`) from `PAYMENTS_PROVIDER` (`payments/settings.py:16`,
  `fake` or `stripe`; deployed environments demand `stripe`, `:46`).
- **Config:** `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` and
  `STRIPE_WEBHOOK_SECRET` from Secrets Manager (`ecs.tf:83-85`,
  `data.tf:169`), and `STRIPE_API_BASE` for stripe-mock contract tests
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
  - The webhook handler's event names and object shapes (`routes.py:420-460`).
  - The reconciliation job compares against the Stripe statuses
    `requires_capture` and `canceled` (`jobs.py:47,53`).
  - The `FAKE_ACCOUNT_PREFIX` logic (`routes.py:153`).
  - The web `PayStep` (and `PayReturn`, which reads Stripe's
    `redirect_status`) and the Stripe.js identity modal.
  - `stripe_result` (`payments/identity.py:61-75`), because Stripe sends ID-check
    events to the same webhook.
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
     forwarded headers (`gateway/main.py:34-44`).
  3. Web: replace `PayStep.tsx` with the provider's drop-in. Extend
     `/payments/config` with what the drop-in needs. Update the CSP.
  4. Data: in-flight bookings are tied to Stripe intents. Drain them first
     (switch off new bookings with `ACCEPTING_BOOKINGS=false`, let captures,
     refunds and transfers finish), or run both providers side by side with a
     `provider` column on `payments` and `connect_accounts`. **Connected
     accounts cannot be migrated**: owners onboard again with the new
     provider's KYC.
  5. Infra: a new secret, the IAM `read_secrets` entry (`ecs.tf:190-204`) and
     the alarm pattern.
  6. Tests: the fake keeps working. Add a contract test like
     `test_stripe_contract.py` against the new provider's sandbox.
  7. Legal: the platform agreement, DPA, the payment-services licence position
     (who holds funds), the terms' payment clause, and the privacy policy.
- **Status and limits:**
  - Separate charges and transfers, with no `on_behalf_of`.
  - One Stripe platform for all markets. Since `235eeaa` accounts are created
    in the owner's country with the full service agreement, which lets a
    German platform pay US and Canadian accounts (`provider.py:160-175`, M-9).
    A client per platform is M-10.
  - Charges are in the listing's currency (M-3, `235eeaa`); nothing is
    converted, and payout currency and FX are M-39.
  - No saved card or deposit (S-9). No 3DS return into the shells (U-7).
  - The kill switch is `PAYOUTS_ON` (7.2).

### 7.2 Owner onboarding and payouts

An owner sets up payouts on a Stripe-hosted page and is paid their share when
a booking completes, or their share of what was kept after a late
cancellation.

- **Where:**
  - `POST /api/payments/connect/onboarding` (`payments/routes.py:228`, Express
    account plus account link). Since `235eeaa` it takes `{"country": "CA"}`
    (default `DE`): the account is created in that country, and one outside
    `PAYOUT_COUNTRIES` (the EEA, CH, GB, US, CA: `routes.py:33-35`) gets 422
    `country_unsupported`. Stripe fixes an account's country at creation. The
    web sends no country yet, so every account is German.
    `GET /api/payments/connect/status` (`:253`).
  - `account.updated` webhook (`:439`) → `payment.payouts_ready` →
    catalog `payable_owners` (`catalog/handlers.py:24`). Buyers only see
    listings of payable owners when `REQUIRE_PAYABLE_OWNERS=true` (required
    deployed, `catalog/settings.py:38,57`).
  - Transfers happen in `payments/handlers.py:125-148` (completed) and
    `:94-121` (the owner's share of a late cancellation).
  - Screen: `Earn.tsx:112`.
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
  - A chargeback holds the payout (`handlers.py:122`).
  - Payout currency and FX are M-39. The Connect bank-account fingerprint is not
    read (S-17 note).

### 7.3 Chargebacks

A card holder's dispute with their bank holds the owner's payout and pages
support.

- **Where:** `charge.dispute.created` (`payments/routes.py:450`) sets
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

- **Where:** `issue` (`backend/services/payments/payments/invoices.py:65`,
  under a row lock on `invoice_counters`), `GET /api/payments/invoices` (`:165`,
  with a `description` line) and `GET /api/payments/invoices/{number}` (`:174`,
  printable HTML in German with § 14 (4) UStG fields). Tables `invoices` and
  `invoice_counters` (`payments/tables.py:64-94`). Screen: `Earn.tsx:416`.
- **Seam:** partial. `Issuer` (`invoices.py:34`) makes the time zone, tax rate,
  label and retention period data (`INVOICE_TIME_ZONE`, `INVOICE_TAX_RATE_BPS`,
  `INVOICE_TAX_LABEL`, `INVOICE_RETENTION_YEARS`, `payments/settings.py:37-40`).
  The issuer's name, address and tax ids are `LEGAL_*` (`:32-35`, Terraform
  `legal`, required deployed).
- **Retention** (since `235eeaa`, D-9): `purge_invoices_once`
  (`payments/jobs.py:61-77`, daily) deletes invoices once the issuer's period
  (10 years by default) has run from the end of the year of issue
  (`docs/retention.md`).
  The template, language and number series are code.
- **To swap it** (for example to an invoicing service or Stripe Invoicing): call
  it from `issue` and store its invoice id on `invoices`. Keep the local number
  series if the provider cannot guarantee gapless per-entity numbering. Keep the
  legal retention (GoBD) and the purge after it.
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
booking above 30 000 minor units (€300 for a euro listing), or in categories
configured for it.

- **Where:**
  - Gate: `create_booking` returns 403 `verification_required` when
    `total > VERIFY_ABOVE_CENTS` (30 000, one number for every currency) or the
    category is in `VERIFY_CATEGORIES` (`booking/routes.py:160-164`,
    `booking/settings.py:33-37`) and the person is not in `verified_people`.
  - Session: `POST /api/payments/identity/session` (`payments/routes.py:294-322`)
    requires `{"consent": true}` (422 `consent_required` otherwise) and stores
    `consent_at` and `consent_version` (`identity-2026-09`, `:287`) on the
    person's `identities` row (P-18). It calls
    `IdentityProvider.start_session` and answers `{status: "pending",
    clientSecret, url}`: a client secret for Stripe.js, a `url` for a hosted
    flow. `StripeIdentity.start_session` (`payments/identity.py:88-96`) asks
    for type `document`, a matching selfie, live capture and metadata
    `personId`. `GET /api/payments/identity` (`routes.py:342`) answers
    `none`, `pending`, `requires_input`, `failed` or `verified`.
  - Result: a provider verdict in neutral words, `IdentityResult(session_id,
    person_id, verified | failed | needs_input)`, applied by `_identity_result`
    (`routes.py:325-340`) only to the person's current session (P-28). Stripe
    sends its `identity.verification_session.*` events to the payments
    webhook, which maps them with `stripe_result` (`identity.py:61-75`:
    `verified`, `requires_input` → needs input, `canceled` → failed). A provider
    with its own webhook posts to `POST /api/payments/webhooks/identity`
    (`routes.py:463-477`), verified by the provider class and handled once per
    session and status (`processed_events`). A pass publishes
    `payment.identity_verified` → booking `verified_people`
    (`booking/handlers.py:147-150`) and, since `235eeaa`, catalog's
    `owners.verified`, the profile's badge (`catalog/handlers.py:84-90`, F-10).
  - Web: the sheet needs the consent box ticked (`Listing.tsx:98`, `:714-729`);
    `verify` (`Listing.tsx:222-244`) sends `{consent: true}`
    (`startIdentity`, `web/src/data/repo.ts:543`), loads Stripe.js on demand,
    calls `stripe.verifyIdentity(clientSecret)`, and polls for the webhook's
    result for up to a minute before retrying the booking. It does not read
    `identityProvider` from `/payments/config` or the session's `url`.
- **Seam:** backend **yes** since `235eeaa` (F-1): `IdentityProvider`
  (`payments/identity.py:48-58`: `name`, `verifies_immediately`,
  `start_session`, `parse_webhook`, `redact`), with `StripeIdentity` (`:78`)
  and `FakeIdentity` (`:115`, a started check is a passed check), chosen by
  `make_identity` (`:132`) from `IDENTITY_PROVIDER` (`payments/settings.py:24`:
  `stripe` or `fake`; empty follows `PAYMENTS_PROVIDER`; `fake` refused
  deployed, `:50-51`). Routes and handlers see only `IdentitySession` and
  `IdentityResult`. `/payments/config` names the provider (`identityProvider`).
  Web: **no**, the Stripe.js modal is the only UI.
- **Provider-specific data:** `identities.session_id` (`vs_…`; fake
  `vs_fake_…`), `status`, `verified_at`, and the consent columns
  (`payments/tables.py:47-61`). The document and selfie stay with the
  provider; Cappy stores only the outcome. On account deletion the session is
  redacted at the provider (`StripeIdentity.redact`, `identity.py:105-112`,
  D-6) before the row goes.
- **To swap it** (for example to Onfido, Veriff or Persona), as the module
  docstring says (`identity.py:1-17`):
  1. Code: a class in `identity.py` mapping the vendor's statuses to
     verified / failed / needs_input, with `redact`. Widen the
     `IDENTITY_PROVIDER` literal (`payments/settings.py:24`) and its
     `unsafe_reasons`.
  2. Config: its keys and webhook secret in Terraform secrets and `ecs.tf`
     (today payments gets no `IDENTITY_PROVIDER`, so it follows
     `PAYMENTS_PROVIDER=stripe`).
  3. Webhook: point the vendor at `/api/payments/webhooks/identity`. The WAF
     already exempts `/api/payments/webhooks/`; the gateway forwards only
     `stripe-signature` of the signature headers (`gateway/main.py:34-44`), so
     add the vendor's.
  4. Web: choose the UI from `identityProvider` (Stripe.js with the client
     secret, or open the hosted `url`); not built. The shells may need camera
     permission strings (S-2). Update the CSP.
  5. Data: existing `verified_people` rows and `owners.verified` stay valid.
     The `identities` rows point at Stripe sessions; keep them as history.
     `payment.identity_verified` keeps its name.
  6. Legal: a DPIA (G-B3), explicit consent for biometric data, recorded before
     the check (P-17; keep the `consent_version` wording in step with the
     app's text), the vendor's DPA and its data location.
- **Limits:**
  - The verified name is not compared with the profile (the rest of P-28).
  - The consent is recorded per person, overwritten on each new session, and
    is not in the data export.
  - The threshold is one number of minor units for every currency, so SEK or
    HUF bookings ask sooner (M-2).

---

## 10. Messaging and masking

Renter and owner message each other on a booking. Before acceptance, phone
numbers, emails, links, IBANs and messenger handles are masked. Afterwards
both sides see what was written. Asking to pay outside Cappy is flagged, and
the app warns both sides.

- **Where:** `backend/services/booking/booking/messages.py`: `mask` `:73`,
  `flagged` `:69`, `POST /api/bookings/{id}/messages` `:141` (idempotent,
  blocks enforced, 30 per sender per booking in 10 minutes, the original kept
  in `unmasked`; since `235eeaa` 409 `conversation_closed` once the booking is
  cancelled, declined, expired or `payment_failed`, or completed and past the
  14-day review window: `open_for_messages`, `:115-127`, FL-18),
  `GET /api/bookings/{id}/messages` `:203` (unmasked once the booking is in
  `SHOWS_HANDOVER`). The event `booking.message` becomes a push to the other
  side every time and, since `235eeaa`, an email at most once per
  conversation per 15 minutes (`MESSAGE_EMAIL_EVERY`,
  `notifications/handlers.py:85-113`, `:174-186`; FL-3). Moderation
  can replace a reported message's words (`remove_content`, 13.2). Web:
  `web/src/app/components/Conversation.tsx` (sender warning `:43`, receiver
  banner `:116`).
- **Seam:** module boundary. `mask(text)` and `flagged(text)` are pure
  functions. A moderation API (for example Hive, or a text classifier) would sit
  behind them.
- **Limits:**
  - The phone rule is European-shaped (`+`, `00` or `0` prefixes). NANP numbers
    without a prefix slip through (M-32).
  - English and German phrases only.
  - The per-sender limit is per booking (30 in 10 minutes, `messages.py:39`,
    `:160-175`, P-12).
  - After a cancellation, messages are masked again (`messages.py:106`).

---

## 11. Reviews

After a completed booking the renter rates the listing and owner (stars,
on-time, tags, text), and the owner rates the renter. Reviews are blind: both
are published together once both are in, or when the 14-day window closes.

- **Where:**
  - Rating routes: `POST /api/bookings/{id}/rate` (`booking/routes.py:401`) and
    `/rate-renter` (`:459`).
  - Blind publishing: `publish_reviews` (`booking/repository.py:335`) and the
    sweep `reviews_due` (`:369`).
  - Events: `booking.rated` → catalog review plus the owner's record
    (`catalog/handlers.py:30`), and `booking.renter_rated` → the renter's record
    (`:20`).
  - Reads: `GET /api/listings/{id}/reviews` (`catalog/routes.py:475`) and the
    summary in the listing detail. Tags: `/api/review-tags`
    (`matching/domain/reviews.py`).
  - Web: `web/src/app/components/Reviews.tsx`, `BookingDetail.tsx`.
- **Provider:** none.
- **Limits:** no collusion signals (S-28). No in-app store review prompt (S-27).
  Reviewers are shown as "First L."; deleted accounts as "Former member".
  Moderation can empty a review's text and tags and keep its rating
  (`remove_content`, 13.2).

---

## 12. Notifications (email, push, inbox, settings)

### 12.1 Email

Transactional email for booking changes, payouts, reports and moderation
decisions, in the recipient's language.

- **Where:** `backend/services/notifications/notifications/handlers.py`
  (`messages` `:40`, `moderation_mail` `:133`, `deliver` `:156`). Since
  `235eeaa` `messages` also tells the renter of a failed payment, and the
  owner too when the capture failed after they accepted, and both sides of a
  dispute (`:74-82`, FL-2); message notices are emailed at most once per
  conversation per 15 minutes, checked against the inbox (`_recently_told`,
  `:85-99`, `notify` `:174-186`, FL-3). Texts: `texts.py:12` (EN/DE/FR, with
  French since `235eeaa`: one neutral French for France and Québec,
  « courriel »), chosen by Cognito's `locale` (`language`, `texts.py:202-205`:
  `de…` and `fr…`, anything else English). Amounts are formatted per currency
  and language (`money`, `:251-265`). Sender:
  `Mailer` (`mail.py:37`), `SesMailer` (`:106`, SES v1 `SendEmail`, plain text),
  `LogMailer` (`:124`). Selected in `notifications/main.py:26` by `MAILER`
  (`log` or `ses`; deployed must be `ses`, `settings.py:12,25`) and `MAIL_FROM`.
  Always-emailed kinds are in `prefs.py:61-72` (since `235eeaa` also
  `payment_failed`, `disputed_owner`, `disputed_renter`).
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
     notifications role (`ecs.tf:222`).
  5. Cognito's own emails (codes, resets) still go through SES
     (`identity.tf:47`) unless Cognito is swapped too, so SES may stay.
  6. Local: LocalStack SES today. Use `LogMailer` or the provider's sandbox.
  7. Legal: DPA. Mail is sent from the EU region today.
- **Limits:**
  - Plain text only; no templates or HTML.
  - Three languages, the app's three. The rest are M-17 and M-34.
  - Deadlines are told in `Europe/Berlin` unless the event carries a
    `timeZone` (`texts.py:228`), and listings have none yet (M-15).
  - No marketing mail, so no unsubscribe handling (M-30).

### 12.2 Recipient directory

Who to write to: a person's verified email and locale, looked up at send
time and never copied.

- **Where:** `Directory` (`notifications/mail.py:21`), `CognitoDirectory` (`:41`,
  `AdminGetUser` with a `ListUsers` fallback; only verified emails are used).
  It also signs a person out everywhere (`:76-88`), deletes their Cognito
  user when their account is deleted (`delete_person`, `:90-98`, P-23), and
  gives the email and locale for the data export (`person_of`, `:100-103`,
  D-10). IAM:
  `ecs.tf:223`.
- **Seam:** yes. It is replaced together with identity (1.1).

### 12.3 Push

Every notification that emails (except moderation) is also pushed to the
person's signed-in phones. Chat messages are pushed every time, and emailed
at most once per conversation per 15 minutes.

- **Where:**
  - Devices: `POST/DELETE /api/notifications/devices` (`notifications/routes.py:39`,
    `:79`), at most 10 per person, in the `devices` table (token, platform,
    endpoint, `install_hash`: `tables.py:21-33`). A token registered by
    another person moves only when the request carries the same `installId`
    (a random id per app install, stored hashed) or the row has none; else 409
    `device_taken`. On a move the old endpoint is deleted first
    (`routes.py:40-76`, P-33). Since `235eeaa` every removal (sign-out,
    sign-out-everywhere, deletion, the 10-device cap, a dead endpoint) deletes
    the SNS endpoint first (`drop_devices`, `push.py:85-94`, D-7).
  - Sending: `Pusher` (`push.py:15`), `SnsPusher` (`:41`, SNS Mobile Push
    `CreatePlatformEndpoint` and `Publish` with APNS and FCM v1 payloads carrying a
    `link`; `unregister` is `DeleteEndpoint`), `LogPusher` (`:26`). Selected in
    `notifications/main.py:27-28`: SNS when `PUSH_IOS_APP_ARN` or
    `PUSH_ANDROID_APP_ARN` is set (`settings.py:18-19`, Terraform
    `push_app_arns`, `variables.tf:119`).
  - Dead endpoints are forgotten (`_push`, `handlers.py:226-236`).
  - App side: `enablePush` and `pushSignedOut` (`web/src/native.ts:114`, `:165`,
    with `@capacitor/push-notifications`); registration sends
    `{platform, token, installId}`, a random id made once per install
    (`native.ts:102-111`, `:135`), and registers again after every new sign-in
    (FL-13); a 409 leaves push off on that device. The priming sheet is
    `web/src/app/components/PushPrime.tsx`, and tap-to-open follows the `link`
    (`native.ts:75-79`).
- **Seam:** **yes,** `Pusher.register(platform, token) -> endpoint`,
  `Pusher.send(endpoint, title, body, link) -> alive` and
  `Pusher.unregister(endpoint)`.
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
  4. Infra: remove the SNS platform-endpoint IAM statements (`ecs.tf:225-226`)
     and the platform applications (runbook). Add a secret for the provider key.
  5. Shells: Android needs `google-services.json` (not in the repo;
     `web/android/app/build.gradle:50-55`). iOS has `aps-environment`
     `development` in `web/ios/App/App/App.entitlements`, which must be
     `production` for release.
  6. Legal: APNs, FCM and the new vendor are processors; US transfer (P-19).
- **Limits:** a row registered before the install id (no `install_hash`)
  still moves to whoever registers its token next. No web push.

### 12.4 Inbox (the bell)

A paginated list of everything a person was notified about, with an unread
count, rendered in the reader's language.

- **Where:** `InboxRow` (`notifications/tables.py:36`, text key plus params),
  written by `_keep` (`handlers.py:245`). `GET /api/notifications`
  (`routes.py:132`, uses `Accept-Language`, which the gateway forwards at
  `gateway/main.py:38`) and `POST /api/notifications/read` (`:174`). Screen:
  `web/src/app/screens/Notifications.tsx`. The bell is in `AppShell.tsx`.
- **Provider:** none.

### 12.5 Notification settings

Per category (bookings, messages, payouts, marketing), push and email on or
off. Marketing is off by default. Contract and moderation emails are always
sent.

- **Where:** `notifications/prefs.py` (`DEFAULTS` `:37`, `CATEGORY` `:47`,
  `wanted` `:90`), `GET/PUT /api/notifications/settings` (`routes.py:159`,
  `:164`), table `notification_prefs`. Screen: `Profile.tsx`.
- **Provider:** none.
- **Limits:** there is no consent record for marketing (M-30). The messages
  email switch works since `235eeaa` (FL-3); the Profile text shown before
  the settings load still says "Everything also arrives by email"
  (`Profile.tsx:596`), which is not true of every message.

---

## 13. Trust and safety

### 13.1 Reports (DSA Art. 16)

Anyone can report a listing, profile, message or review with a reason,
details and a good-faith confirmation. People without an account leave an
email. Every report is acknowledged by email.

- **Where:** `POST /api/reports` (`backend/services/catalog/catalog/moderation.py:141`),
  public, idempotent when signed in. Limits: 3 a day per anonymous email, and
  per target a day 5 anonymous and 20 signed-in reports, counted apart so
  anonymous ones never use up the members' cap (`moderation.py:137`,
  `:170-186`, P-7, `f303350`). The event `moderation.report_received` becomes
  an email. Web: `web/src/app/components/Report.tsx`, `sendReport`
  (`repo.ts:720`, with an `Idempotency-Key` per attempt). Signed out, the
  form is on `/legal/report`, where the reporter picks what they report and
  pastes its link or reference (`Legal.tsx`, `Report.tsx` `referenceId`,
  FL-10, `f22f143`).
- **Provider:** none. No CAPTCHA.
- **Limits:** anonymous addresses are still not confirmed; the receipt mail is
  kept on purpose (DSA Art. 16(4)) and bounded by the per-address cap.
  `reporterEmail` travels in events between services but is scrubbed from the
  analytics lake (P-6, `f303350`). A reporter's id, email and words are
  cleared 183 days after the decision, and when they delete their account
  (`catalog/jobs.py:45-60`, D-3); the reporter's export includes their
  reports (D-10).

### 13.2 Moderation queue and decisions (DSA Art. 17)

Staff see open reports oldest first, dismiss, take down a listing, remove a
message or review, or suspend the person, with a structured statement of
reasons. Both sides are told, and every action is audited.

- **Where:** `moderation.py`: queue `:220`, decide `:352`, take-down `:418`,
  suspend `:440`, reinstate `:463`, audit `:478`, statement of reasons
  `:105`. Every one needs a staff account with MFA (1.3). Since `235eeaa`
  (FL-7) `decide` also takes `remove_content` for a message or review report
  (`DecisionIn`, `:101-102`): a review keeps its rating and loses its text and
  tags, a message's words are replaced through booking
  `POST /internal/messages/{id}/remove` (`_remove_content`, `:339-349`), and
  the author is told ("We removed something you wrote"). `suspend` finds the
  person behind any target: the owner of a listing or profile, the author of
  a review, or of a message through booking `GET /internal/messages/{id}`
  (`_affected`, `:318-336`). A take-down or suspension publishes
  `listing.changed` with `by: "staff"`, so booking declines pending requests
  with "The listing was taken down by Cappy" (`booking/handlers.py:114-128`,
  FL-9), and purges the photos from the CDN (3.4). The event
  `moderation.decision` goes to notifications
  (`statement_params`, `notifications/handlers.py:116`). `moderation.owner_suspended`
  goes to booking, which declines the owner's pending requests and blocks new
  bookings by them (`booking/handlers.py:130`). Screen:
  `web/src/app/screens/Admin.tsx`.
- **Provider:** none. There is no automated content classifier. `automated`
  in the statement is always what staff say.
- **Console:** for a message or review report it offers **Remove the
  message / review** and **Suspend the author** (`Admin.tsx:33-42`, `:334`),
  which the server accepts since `235eeaa` (they answered 422 before). It
  also lists held listings and approves them (`getHeldListings`,
  `approveListing`, `repo.ts:748-749`; 13.3).

### 13.3 Held listings (fraud rule)

A new owner's listing above €100 an hour waits for a staff check.

- **Where:** `create_listing` and `update_listing` (`catalog/routes.py:530`,
  `:566`), `REVIEW_ABOVE_CENTS` (`catalog/settings.py:49`, one number of minor
  units for every currency), and admin `GET /api/admin/listings/held` and
  `POST .../approve` (`moderation.py:507`, `:528`). The owner can open their
  held listing (`catalog/routes.py:453-473`, FL-6).
- **Provider:** none.

### 13.4 System notices: reliability and ban evasion

- **Owner reliability (S-18):** booking counts an owner's cancellations and
  no-shows over 12 months (`booking/repository.py:208`). It emits
  `booking.owner_reliability`, which becomes `owners.cancellation_rate`, a
  ranking signal (4.1), shown on the listing. Three failures in 30 days emit
  `moderation.person_flagged`, which joins the queue (`moderation.py:547`).
- **Linked cards (S-17):** payments reads the card fingerprint on
  authorisation (`payments/routes.py:102-110`, `Provider.card_fingerprint`). Booking
  compares it with cards used by suspended accounts
  (`booking/handlers.py:94-110`) and flags the person. On account deletion
  the fingerprint is cleared everywhere, except booking's copy for a
  suspended person (D-5). The booking still goes ahead.
- **Seam:** the fingerprint is behind `Provider.card_fingerprint`. A new payment
  provider must supply a stable per-card fingerprint, or this signal goes dark.
- **Limits:** no bank-account fingerprint, no device fingerprint, no
  duplicate-photo detection (S-20).

### 13.5 Velocity limits and card testing

- **Where:** 10 booking requests a day and at most 3 unpaid bookings
  (`booking/settings.py:27-29`, `routes.py:145-148`). 20 new listings a day
  (`catalog/settings.py:45`). 100 photos a day (`catalog/settings.py:29`).
  30 messages per sender per booking in 10 minutes (`booking/messages.py:39`),
  5 data exports a day and 5 sign-outs-everywhere an hour
  (`catalog/routes.py:377-418`, `rate_hits`; P-12, `f303350`).
- **Edge:** AWS WAF per-IP rate rule, IP reputation, and Bot Control in prod
  (`infra/platform/edge.tf:171`, `:263`; `bot_control`, `variables.tf:107`,
  on in `infra/envs/prod/main.tf:85`). A separate WAF sits on Cognito
  (`identity.tf:124`). Stripe webhooks are exempt from rate and bot rules and
  are protected by their signatures.
- **Seam:** infra only. Swapping the WAF (for example to Cloudflare) is a
  Terraform change plus the webhook exemptions.
- **Limits:** no per-user limits in the gateway (`gateway/settings.py:43-45`);
  the per-person limits live in the services that own the data.

### 13.6 DSA transparency numbers

- **Where:** `GET /api/admin/dsa-stats?month=` (`moderation.py:586`): notices by
  reason and decision, median hours to decision, and active recipients from
  booking `/internal/stats/active-people` (`booking/routes.py:567`). The exact
  count is an Athena query (`docs/analytics.md`).
- **Provider:** none.

---

## 14. Privacy (export, deletion)

### 14.1 Data export (GDPR Art. 15/20)

A member downloads one JSON file with everything held about them.

- **Where:** `GET /api/me/export` (`catalog/routes.py:397`) gathers the
  catalog's part (`repository.py:242`: profile, listings, saved, reviews
  written and about them, photo names, reports filed, moderation decisions)
  and each service's `/internal/people/{id}/export`: booking
  (`booking/routes.py:586`: bookings, messages, evidence with notes, blocks,
  verified and suspended flags, card fingerprints), payments
  (`payments/routes.py:363`: payout account, identity status, invoices with
  recipient fields, payments with charge, refund and payout flags) and
  notifications (`notifications/routes.py:184`: bell items, settings,
  devices, and the Cognito email and locale). Coverage since `235eeaa` (D-10);
  the register `cappy_common/privacy.py` records every table left out and
  why. Web: `exportMyData`
  (`repo.ts:436`). In the store shells it goes to the share sheet
  (`native.ts:184`).
- **Provider data not included:** anything held by Stripe (cards, KYC, ID
  documents), and Cognito's password and MFA data. The export says so only
  implicitly.
- **Limits:** 5 a day per person (`rate_hits`, P-12). Hand-over photos
  appear as `evidence:<name>` references, not files. The ID-check consent and
  decisions on the person's messages or reviews are missing (DATA.md §5.3).
  No CCPA or Law 25 request workflow (P-29).

### 14.2 Account deletion

A member deletes their account in the app or at `/account/delete` (Google
Play). It is refused while bookings are open or a payout is pending, with the
reason and a date.

- **Where:** `DELETE /api/me` (`catalog/routes.py:347`). It checks booking
  `/internal/people/{id}/open` (`booking/routes.py:556`) and payments
  `/internal/people/{id}/open` (`payments/routes.py:351`), then
  `repository.forget` (`catalog/repository.py:189`: listings down with their
  words and photos cleared, every upload handed to the photo sweep, reports
  they filed without the reporter, stored answers deleted, the profile a
  "Former member", reviews anonymised), and ends the person's sessions in
  catalog at once (`routes.py:370-375`). `profile.deleted` goes to:
  - booking: blocks and verification go, messages are redacted, bookings keep
    their row but lose the hand-over details, the owner's name and business,
    notes and (unless suspended) the card fingerprint, evidence loses photos
    and notes, stored answers go (`booking/handlers.py:152-169`, `:38-65`);
  - payments: the Connect link goes, the ID-check session is redacted at the
    provider and the identity row deleted, and card fingerprints are cleared
    (`payments/handlers.py:157-175`);
  - notifications: the Cognito user is deleted (`AdminDeleteUser`), then
    devices with their SNS endpoints, inbox and settings go
    (`notifications/handlers.py:198-206`);
  - and all three stop accepting the person's tokens (`cappy_common/guard.py`).
  All of it is D-1 to D-7 in `235eeaa`, pinned by the register and
  `test_privacy.py` (D-11).
  The app also calls Cognito `DeleteUser` itself, twice at most, as the quick
  path, and signs out whatever happens (`Profile.tsx` `remove`,
  `web/src/data/auth.ts:282`, FL-11). Screens: `Profile.tsx`, `App.tsx:61`
  (`/account/delete`).
- **Provider data:** the Stripe Connect account stays with Stripe, which keeps
  what financial regulation requires. Invoices are kept for the issuer's
  legal period, then purged (8.1).
- **Limits:** CloudFront keeps the person's listing photos until they expire
  from the edge. The `delete_me` docstring (`catalog/routes.py:349-352`) still
  says the app deletes the sign-in and that bookings hold no personal data.

---

## 15. The app shell (PWA and Capacitor)

### 15.1 Web app and PWA

- **Where:** React 19 and Vite. The PWA comes from `vite-plugin-pwa` with
  auto-update (`web/vite.config.ts:64`): the app shell is cached and the API is
  never cached. Routes are in `web/src/app/App.tsx` (signed-out routes `:58-63`,
  signed-in `:154-172`). Every screen but the welcome, sign-in, browse,
  listing and bookings list is a lazy chunk (`App.tsx:25-36`), and so are the
  Stripe pay step and the non-English catalogues (S-15, `f42a4ef`): the entry
  chunk was 144.5 kB gzipped at that commit, and `npm run check:size` fails
  above 170 kB after a build. The welcome screen is shown once per device
  (`device.ts`).
- **Hosting:** S3 plus CloudFront in AWS. Locally the gateway can serve
  `web/dist` (`gateway/main.py:268`).
- **Fonts:** self-hosted through `@fontsource-variable` (`web/src/main.tsx:5-6`).
- **Languages:** English, German and French (`web/src/i18n.ts:10`,
  `Lang = 'en' | 'de' | 'fr'`; catalogues `i18n.de.ts`, `i18n.fr.ts`, one
  French for France and Québec). The device language picks one at first
  start; the switch is on the welcome, sign-in and profile screens. The
  first render waits for the catalogue (`web/src/main.tsx:18-25`). Plurals go
  through `Intl.PluralRules`. Dates, money and units use `locale()`
  (`i18n.ts:51-59`): the app's language with the device's region (`en-US`,
  `fr-CA`, `de-AT`…), else `en-IE` (since `44a5520`: km and 24 h across
  Europe), `fr-FR` or `de-DE`. `npm run check:i18n`
  checks both catalogues have the same keys and placeholders, and that every
  literal `t('…')` and `plural(…)` in the source has an entry. Dev builds
  stretch every string with `?pseudo=1` (U-28). Emails, pushes and the bell
  have French since `235eeaa`; the legal pages have none yet (M-17).
- **Limits:** no Web Vitals (S-23). `npm run check:a11y` is a static check
  (image alt text, 24 px targets) and not a browser axe run (U-30 partly).
  Since `44a5520` CI runs `tsc --noEmit`, the build and every `check:*`
  script (`size`, `i18n`, `flags`, `attempt`, `a11y`), installing with
  `--ignore-scripts` (`.github/workflows/ci.yml:52-61`).

### 15.2 Store shells (Capacitor)

The same build ships in the App Store and Google Play.

- **Where:** `web/capacitor.config.ts` (appId `app.cappy`), `web/ios`,
  `web/android`, and `web/src/native.ts`. Plugins used: `app`, `preferences`,
  `push-notifications`, `filesystem`, `share` (`web/package.json`).
  - Storage: `nativeStore` (`native.ts:13`, Capacitor Preferences) holds the
    refresh token and the device flags.
  - Android back button: `native.ts:70`.
  - iOS Dynamic Type: the root font size follows the reader's text size
    (`native.ts:45-55`, U-27); Android's WebView scales text itself.
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

Universal Links and App Links open `/listing/*`, `/bookings/*`, `/earn*` and
`/pay/*` (the return from a bank's card check) in the app. Notification taps
open their `link`.

- **Where:** the build emits `.well-known/apple-app-site-association` and
  `assetlinks.json` from `VITE_APPLE_TEAM_ID` and `VITE_ANDROID_SHA256`
  (`web/vite.config.ts:25-55`). The `appUrlOpen` listener is at `native.ts:67`.
  The iOS associated domain is `applinks:$(CAPPY_DOMAIN)` (`cappy.app` in the
  Xcode build settings), and release builds sign with
  `web/ios/App/App/App.release.entitlements` (`aps-environment`
  `production`), since `f22f143` (FL-21).
- **Provider:** none (no Branch or Firebase Dynamic Links).

### 15.4 Offline and drafts

- **Offline:** `useOnline` and `OfflineBar` (`web/src/app/components/Offline.tsx`).
  Money actions are disabled offline (`PayStep.tsx:66`). Reads are served from
  the React Query cache. A cold start offline shows the app as the last
  signed-in person, with the offline bar, and refreshes when the network is
  back (`web/src/data/auth.ts:94-140`, `:183`, FL-14).
- **Drafts:** `drafts` (`web/src/app/device.ts:47`, `localStorage`). The listing
  form keeps its whole state (`AddListing.tsx:189,247`). Drafts are cleared on
  sign-out (`device.ts:67`).
- **Retries:** the client honours `Retry-After` and backs off
  (`web/src/data/repo.ts:128`, `:222`), and refreshes once on a 401 (`:96`).
  A 429 without a message says how long to wait.
  Creates keep their `Idempotency-Key` across retries of an unknown outcome
  (5.1, FL-1).
- **Provider:** none.

---

## 16. Operations

### 16.1 Feature flags and rollouts

- **Where:** `FEATURE_FLAGS="name:percent,…"`, one setting for every service
  (`backend/libs/cappy_common/cappy_common/settings.py:111-115`; Terraform
  `feature_flags`, `variables.tf:101`, into every task at `ecs.tf:31`; CD
  reads it from the GitHub environment variable `FEATURE_FLAGS`). They are
  parsed by `flags.py:15` and served in `/api/app-config` as `flags` (100
  means on) and `rollouts` (0 < percent < 100) (`gateway/main.py:210-225`,
  cached by CloudFront for 5 minutes). The app places each user with FNV-1a
  (`web/src/domain/flags.ts`, `useFlag` `repo.ts:408`; check:
  `npm run check:flags`). A service enforces a flag with `flags.enabled`
  (`flags.py:32`), as booking does for `paidCancellationPolicies`. A flag
  the server reads as on or off for everyone is read in the app with
  `useGlobalFlag` (`repo.ts:416-418`, since `44a5520`): only 100 counts, never
  a partial rollout.
- **Seam:** **yes.** Two small modules and one endpoint.
- **To swap it** (for example to LaunchDarkly, Unleash or ConfigCat): keep
  `useFlag(name)` as the web API. Back it with the vendor's SDK, or have the
  gateway fetch flags from the vendor into the same `app-config` shape. Mind
  that the vendor's per-user evaluation breaks the CDN cache of `app-config`,
  and that a client SDK is a new third-party script before consent (§ 25 TDDDG;
  CSP).
- **In use:** `paidCancellationPolicies` (6.2, through `useGlobalFlag`).

### 16.2 Kill switches

Stop new bookings, stop payouts or stop new listings without a deploy.

- **Where:** `ACCEPTING_BOOKINGS` (`booking/settings.py:52`), `PAYOUTS_ON`
  (`payments/settings.py:29`) and `ACCEPTING_LISTINGS` (`catalog/settings.py:41`),
  set from Terraform `switches` (`variables.tf:86`, `ecs.tf:43,47,50`), which
  CD reads from the GitHub environment variable `SWITCHES`
  (`.github/workflows/deploy.yml:73`). How to use them is in `docs/runbook.md`.
- **Seam:** settings. A task restart is needed (new task definition).

### 16.3 Client crash reports

- **Where:** `POST /api/client-errors` (`gateway/main.py:229`): 8 KB at most, 10
  a minute per address, logged with emails and phone numbers replaced
  (`scrub`, `:107-109`), never stored. The address is the hop the nearest
  trusted proxy saw (`client_address`, `:112-119`; `TRUSTED_PROXY_HOPS=2` in
  AWS). It is sent from the `ErrorBoundary`, `window.onerror` and
  `unhandledrejection` (`web/src/app/components/ErrorBoundary.tsx`,
  `web/src/main.tsx:13-14`, `reportClientError` `repo.ts:388`).
- **Seam:** yes. `reportClientError` is the one client call site.
- **To swap it** (for example to Sentry): call the Sentry SDK from
  `reportClientError` (or keep the endpoint and forward from the gateway, which
  avoids a third-party script). Upload source maps per release. No replay or
  device id without consent. Add Sentry's ingest host to the CSP `connect-src`.
  DPA.
- **Limits:** the limit is per task, not shared. Free text other than emails
  and phone numbers is still logged (P-34 partly). No source maps.

### 16.4 Product analytics

- **Where:** every domain event goes SNS → Firehose → S3 (2 years, cold after 90
  days) and can be queried in Athena as `cappy_events`
  (`infra/platform/analytics.tf`, `docs/analytics.md`). On the way a Lambda
  keeps only the envelope and an allowlist of non-identifying fields
  (`infra/platform/analytics/scrub.py`, P-6, `f303350`). There is no client
  SDK.
- **Seam:** infra only (an SNS subscription and the Firehose transform).
- **To swap it** (for example to Segment, Amplitude or BigQuery): add a
  subscriber to the events topic that forwards to the vendor, through the
  same allowlist (`scrub.keep`), since the raw events carry names, emails and
  business details.
- **Limits:** no Web Vitals or client events (S-23).

### 16.5 Logs and traces

- **Where:** JSON logs with request ids (`cappy_common/observability.py`).
  OpenTelemetry over OTLP to an ADOT sidecar and on to X-Ray, when
  `OTEL_ENABLED=true` (`observability.py:148`, `settings.py:118-119`). Trace
  context travels inside events (`events.py:123-125`). Alarms, SLOs and a
  synthetic canary are in `infra/platform/observability.tf`, `synthetics.tf` and
  `docs/slo.md`.
- **Seam:** yes, OTLP. Swap to Datadog, Honeycomb or Grafana by pointing
  `OTEL_ENDPOINT` at their collector, or by changing the sidecar.

### 16.6 Event bus

- **Where:** a transactional outbox per service. `Publisher`, `SnsPublisher`,
  `Consumer` and `SqsConsumer` are in `cappy_common/events.py:210,450,396,476`,
  selected by `EVENT_BUS_URL` (`memory://` or `sns://…`) and `EVENT_QUEUE_URL`
  (`events.py:559-568`). A row that fails to publish 20 times is set aside and
  pages (`outbox-set-aside`, D-14). Queues, DLQs and filters are in
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
| Staff MFA (Cognito `AdminGetUser`) | `cappy_common/auth.py:186-219` | The MFA check behind a directory interface, or an `amr` claim check (the role claim is settings since `235eeaa`) |
| Free-text search (Postgres LIKE/trigram) | `catalog/repository.py:721` | A `SearchIndex` protocol with the current SQL as the default, fed by `listing.changed` |
| Places and geocoding (none exists) | `districts` table, `catalog/repository.py:339` | A `Geocoder` interface when addresses become structured (M-5, M-7, M-8) |
| Tax on the fee (fixed rate) | `payments/invoices.py:93` (`Issuer.tax_rate_bps`) | A `tax_for(owner, market, fee)` function per invoice line (M-12) |
| Stripe webhook event handling | `payments/routes.py:419-460` | Have `Provider.parse_webhook` return neutral events (`authorised`, `account_changed`, `chargeback`) instead of Stripe's event dict, as `IdentityProvider.parse_webhook` already does for ID checks |
| Identity verification UI (Stripe.js modal) | `web/src/app/screens/Listing.tsx:222-244` | Pick the flow from `/payments/config.identityProvider` and open the session's `url` for a hosted provider (the backend seam exists since `235eeaa`) |
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
