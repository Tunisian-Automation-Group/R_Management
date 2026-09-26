# Features and their provider seams

Every feature Cappy has today, where it lives, and what replacing its
provider with another third party takes. It describes the **committed code**,
not the plan: planned work appears only as task ids from
[`TASKS.md`](TASKS.md). Markets are all of Europe, the US and Canada
([GOAL 16](GOAL.md), [ADR 0013](adr/0013-markets.md)). Where the code
assumes one market (German tax, Berlin time, EU-shaped rules), this file
says so. Last synced with the code as of `0a74b1c` (covering `174028c` to
`0a74b1c`: `25e79d3`, synced in its own commit; `faebae7`, the readiness
infrastructure and the chargeback lifecycle; the UX merge `1daf0da`; the V8
backend `933ed14` and web `0a74b1c`). The sync before, at `1cb2d67`, covered
`090c890`, `6c2f2ec`, `73610c4` and `1cb2d67`.

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
| Staff role and staff MFA | Cognito group `admin` (`cognito:groups` claim) by default, and `admin-lead` for leads (since `7444e37`); TOTP MFA checked with Cognito `AdminGetUser` | Role: yes since `235eeaa` (`STAFF_CLAIM`, `STAFF_VALUE`, `STAFF_LEAD_VALUE`, F-3). MFA: no (`StaffMfa` calls Cognito) | S |
| Staff case view, dispute resolutions (four eyes), claims, audit log | In-house (booking's `support.py`, catalog's `moderation_actions`); a member found by email through Cognito `ListUsers` | Email lookup: yes (`People`, `booking/clients.py`, since `7444e37`) | S |
| Dispute offers between the parties, late returns, extensions | In-house (`booking/support.py`, since `7444e37`) | n/a | n/a |
| Profiles, business identity, VAT ID check | In-house (regex, no VIES) | n/a (no provider) | S to add VIES |
| Listings, windows, saved | In-house (Postgres) | n/a | n/a |
| Photo storage | S3 + CloudFront (listing photos, with 400/800/1600 px renditions and a dominant colour since `933ed14`), S3 private prefix (hand-over evidence); Pillow re-encode | Yes (`MediaStore`, public and private instances) | S |
| CDN purge on take-down | CloudFront `CreateInvalidation` | Yes (`Cdn`, `catalog/cdn.py`, since `235eeaa`, F-4) | S |
| Markets (currency, thresholds, open countries) | In-house configuration, `cappy_common/markets.json` (since `747ed6b`, M-2) | n/a (a launch is a config change) | n/a |
| Places, distance, map | Own `districts` table, a point per listing (snapped to about 500 m in public), haversine, own SVG map | No geocoder at all | M (M-7) |
| Free-text search | Postgres `LIKE` + trigram index | No (in `CatalogRepository.search`) | M |
| Matching, ranking, pricing | In-house (`matching/domain`); the weights published at `GET /api/ranking` | n/a | n/a |
| Weekly opening hours | In-house (`catalog/schedule.py`) | n/a | n/a |
| Booking state machine, no double booking | In-house (Postgres exclusion constraint) | n/a | n/a |
| Instant book, cancellation policies, discounts | In-house | n/a | n/a |
| Card authorise, capture, cancel, refund | Stripe PaymentIntents (manual capture); the card form is Stripe's Payment Element in Cappy's tokens, with Apple Pay and Google Pay where the device and domain allow (since `0a74b1c`) | Yes (`payments/provider.py` `Provider`; web: `PayStep.tsx`) | L |
| Owner onboarding and payouts | Stripe Connect Express, transfers | Yes (same `Provider`) | L |
| Webhooks, chargebacks (the whole lifecycle since `faebae7`: hold, evidence, won pays out, lost reverses the transfer) | Stripe events, Disputes API, transfer reversals | Partial (signature check, `submit_dispute_evidence` and `reverse_transfer` behind `Provider`; event handling and statuses are Stripe-shaped) | M |
| Reconciliation sweep | Stripe intent status | Partial (`Provider.intent_status` returns Stripe's words) | S |
| Fee invoices | In-house HTML, German § 14 UStG template; a private owner's address from the payout provider's KYC (`Provider.account_address`, since `42c777c`) | Partial (`Issuer`: zone, rate, label) | M |
| VAT / sales tax, platform tax reporting | None (fixed rate from settings; DAC7 tags only) | No | L (M-11..M-14, M-24..M-27) |
| Identity verification | Stripe Identity (document + selfie) | Backend: yes (`IdentityProvider`, `payments/identity.py`, its own webhook route, since `235eeaa`, F-1). Web: yes since `2257182` (a session's hosted `url` opens; the Stripe.js modal only when `identityProvider` is `stripe`) | M |
| Messaging, contact masking, pay-outside flag | In-house regex | Module boundary (`mask`, `flagged`) | S |
| Inbox of conversations, read receipts, unread badge (since `933ed14`/`0a74b1c`) | In-house (booking's `GET /inbox`, `message_reads`) | n/a | n/a |
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
| Paging and tickets (since `faebae7`) | SNS topics `…-alarms` (page) and `…-tickets`; mail, plus any pager that takes an SNS HTTPS subscription (PagerDuty, Opsgenie, Incident Manager) | Yes (`pager_endpoint`) | S |
| Account security logging (since `faebae7`) | CloudTrail, GuardDuty, Security Hub | Infra only (`account_security` turns it off for an organisation that runs them centrally) | M |
| Backups beyond Aurora PITR, budgets (since `faebae7`) | AWS Backup (locked vault), AWS Budgets, Cost Anomaly Detection | Infra only | M |
| Data export, account deletion | In-house fan-out over `/internal`; deletion also removes the Cognito user (`AdminDeleteUser`), the Stripe Identity session (redact) and SNS endpoints; a register of personal data with a test (`cappy_common/privacy.py`) | n/a | n/a |
| Web app shell, offline cache | vite-plugin-pwa (Workbox) | n/a | S |
| Design tokens, dark mode, motion (since `1daf0da`) | In-house (`web/src/app/theme.css`, `theme.ts`; `check:tokens`, `check:contrast`) | n/a | n/a |
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
- **Errors name every field** (since `42c777c`, V4-20). A 422 `invalid` from
  request validation carries `error.fields`, `[{field, message}]` with the
  path inside the body in the API's camelCase names (`business.vatId`), and
  its `message` is the first of them (`_fields`, `cappy_common/errors.py`);
  any `ApiError` may carry `fields` too (`put_me`'s unknown district does).
  The web keeps them on `ApiError.fields` (`web/src/data/repo.ts`) and shows
  each under its own field in the profile, onboarding and listing forms
  (`serverBusinessErrors` in `BusinessFields.tsx`, `fieldErrors` in
  `AddListing.tsx`). Refusal codes the reader should see in their own
  language are mapped in `CODE_TEXT` (`repo.ts`: `market_not_live`,
  `market_unknown`, `currency_not_in_market`, `location_outside_district`,
  `country_unsupported`, `conversation_closed`, and since `4e86866`
  `district_not_in_country`, `four_eyes`, `needs_lead`, `approval_pending`,
  `invalid_refund`, `own_offer`, `offer_changed`, `not_extendable`,
  `within_grace`, `claim_window`, `claim_exists`, and since `0a74b1c`
  `report_target_unknown`; EN/DE/FR) before the
  server's English message. Error toasts have their own tone (`useToast(message,
  'error')`, `Toast` in `ui.tsx`: no tick, `role="alert"`, 6 s instead of
  2.8 s, V4-4).
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
  sign-out-everywhere or deletion (401 `token_expired`, `auth.py:168-178`,
  `cappy_common/guard.py`, P-24). Since `42c777c` the comparison is exact:
  the token's whole-second `iat` against the exact revocation time, so the
  token that asked for the sign-out, and any issued in the same second, is
  refused at once; a sign-in in that same second is refused too and has to
  sign in again (V4-24; before, both were rounded down and such a token lived
  on for up to 15 minutes). The gateway passes `Authorization` through
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
  (`cappy_common/guard.py:58-77`). Matching, which has no database, asks
  catalog (`GET /internal/revocations/{sub}`, `CatalogRevocations` in
  `matching/clients.py`, cached 30 s); if catalog cannot answer, the request
  is a 5xx, never a 401 that would sign the person out. Notifications then calls
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
  the devices go and the tokens are refused (`mail.py:77`): another device
  that refreshes afterwards carries on locally (GD-4, documented as a
  local-only limit in `docs/runbook.md`, "Local stack only", since
  `42c777c`). A plain **Sign out** revokes the refresh token (`RevokeToken`,
  `web/src/data/cognito.ts`); real Cognito then refuses its access tokens
  too, but cognito-local does not and issues them for 24 hours, so locally
  the old access token works until it expires (V7-28, noted in the runbook
  since `1cb2d67`; sign out everywhere does end it).

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
- **Leads** (since `7444e37`, H-6): a staff member whose claim also holds
  `STAFF_LEAD_VALUE` (`admin-lead` by default, `settings.py`) is a `lead`,
  everyone else `support` (`staff_role`, `auth.py:233-237`). The role picks
  the per-market refund limit a staff member may settle alone
  (`refund_limit_support`, `refund_limit_lead` in `markets.json`, 13.7).
  Since `b5cdd93` Terraform creates the `admin-lead` group beside `admin`
  (`aws_cognito_user_group.admin_lead`, `identity.tf`); membership is granted
  by hand, a lead in both groups (locally `make confirm EMAIL=… LEAD=1`,
  which creates it if missing and adds the account to both, since
  `22b5e0f`). Since `ad9dee9` matching also has staff routes (the preview's
  offers and quote, 13.3), so its task gets the staff MFA check's IAM too
  (`ecs.tf` `local.staff_mfa_check`).
- **Limits:** two roles (support and lead) and, for refunds above a limit,
  four eyes (13.7); nothing else is separated. Turning MFA off takes up to 5
  minutes to bite (the cache).

### 1.4 App version gate

Store builds older than the minimum are asked to update.

- **Where:** `GET /api/app-config` (`backend/services/gateway/gateway/main.py:210`)
  returns `minVersion` and `latestVersion` from `APP_MIN_VERSION` and
  `APP_LATEST_VERSION` (`gateway/settings.py:34-35`), and since `747ed6b`
  `markets`: per country its currency, languages, units, emergency number,
  status and minimum age (`public_markets`, `main.py:232`; nothing about
  entities or tax). Since `2257182` the web reads it: `useMarkets` (every
  market and the live ones, for the country pickers) and `useMarket(country?)`
  (the given country, else the profile's, else the device's region if served,
  else DE; `web/src/data/repo.ts`) give the currency of a new listing, the
  emergency number on the report sheet, the booking page and the help pages,
  and the minimum age at onboarding. Until `app-config` answers, Germany's
  values stand in (`HOME_MARKET`). The app sends
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
  on `owners.country`. Since `747ed6b` (M-2) it
  must be a live market (`live_market`, `routes.py:357`): an unknown country
  is 422 `market_unknown`, a planned one 422 `market_not_live`. Only DE, AT
  and CH are live (`cappy_common/markets.json`). Since `42c777c` a business
  without its details and a malformed VAT ID are field errors checked with
  the rest of the body (`ProfileIn._business_says_who_it_is`,
  `BusinessIn._vat`), and an unknown district names the `district` field
  (V4-20). Since `7444e37` the district must also be in the profile's
  country: 422 `district_not_in_country` on the `district` field otherwise
  (`_district_in`, `catalog/routes.py`), so a Swiss profile (prices in CHF)
  is never in a Berlin district. The seed has had Austrian (Wien, Graz,
  Linz, Salzburg, Innsbruck) and Swiss (Zürich, Genève, Basel, Bern,
  Lausanne) districts since `7444e37`, so both countries can be picked. The
  event `profile.created` is emitted in `put_me`. Public profile:
  `GET /api/owners/{id}`. Screens: `Onboarding.tsx`, `Profile.tsx`. Since
  `2257182` both have a **Country** picker of live markets
  (`CountrySelect.tsx`, names from `Intl.DisplayNames`; onboarding starts at
  the device's region when Cappy serves it) and show only that country's
  districts; the profile keeps a country that stopped being live selectable
  for the person already in it. Both send `country`, and list every missing
  or malformed field at once.
- **After a deletion:** the same sign-in (`sub`) signing up again gets a fresh
  profile: counters reset, `verified` and business cleared, 18+ asked again,
  and `profile.created` emitted; a suspension stays (FL-11,
  `catalog/repository.py:406-415`).
- **Provider:** none. The `owners` table is in the catalog database.
- **Status and limits:**
  - Districts are the only notion of place (see 4.3), plus the profile's
    `country`, which only sets the payout account's country (7.2). There is no
    address or time zone on a person.
  - The minimum age comes from the market since `747ed6b` (`minimum_age`: 18
    everywhere but 19 in CA). Since `2257182` the onboarding tick and its
    error say the chosen market's age ("I am {age} or older"). The check is
    still that one tick, not a date of birth. Age by category is
    M-38. The terms text and store questionnaires are still open (S-5).
  - The response time and rate shown on the profile are measured since
    `61b15b8` (H-1): booking takes, over 90 days, the requests an owner
    answered or let lapse (not system declines or withdrawn ones) and sends
    the median minutes to answer and the answered share on
    `booking.owner_reliability` (`booking/repository.py:214`); catalog stores
    them on `owners.response_mins` and `response_rate`. Both are null under 3
    such requests; the invented 60-minute default is gone (migration 0016).
    ~~The web prints "Replies in ~null min"~~: **fixed in `2257182`** (H-1):
    `responseTime` and `responseRate` (`web/src/app/format.ts`) return null
    while unmeasured and the listing and booking pages then say nothing
    about it; measured, the listing's owner card reads "Replies in ~20 min ·
    Answers 95% of requests" (percentages through `Intl` since `4e86866`,
    `percent` in `format.ts`: "95%" in English, "95 %" in German and
    French; the renter record's decimal and plural follow the locale too,
    V5-17).
  - `Owner.verified` (`cappy_common/models.py:137`) is set by a passed ID
    check since `235eeaa` (F-10): catalog handles `payment.identity_verified`
    (`catalog/handlers.py:84-90`). New profiles get `False`, and deletion
    clears it.

### 2.2 Business identity (traders)

A business owner states its legal name, address, register number and VAT ID.
Renters see it on the listing and at checkout ("your contract is with…").

- **Where:** `BusinessIn` with VAT normalisation and a regex check, a field
  validator since `42c777c` (`_vat`, `catalog/routes.py`: a bad VAT ID is the
  field error `business.vatId`), stored in `owners.business` (JSON,
  `catalog/tables.py:73`). It is copied into the booking snapshot
  (`booking/routes.py:190`) and onto fee invoices, where its address is the
  recipient's (8.1). Web: `web/src/app/components/BusinessFields.tsx` (also
  `TraderNote`); since `2257182` it checks the VAT shape as the server does
  (`vatProblem`), sends it without spaces or dots, and shows each problem
  under its field (`businessErrors`, `serverBusinessErrors`).
  Every seeded business owner has invented trader details since `42c777c`
  (legal name, address, register number, VAT ID, in `seed.json`, V4-16).
- **Provider:** none. A German VAT ID must be `DE` and 9 digits; other EU
  prefixes are checked only by shape. There is no VIES lookup.
- **To add a checker** (VIES, HMRC, Swiss UID, CRA BN): put it behind a
  `validate_vat(country, id)` function called from `BusinessIn._vat`. Make
  it tolerant of VIES downtime (accept and re-check later). Add per-country
  error texts. This is M-33.
- **Web** (since `4e86866`, V5-11): the field is **VAT ID (optional)**
  ("Your EU VAT number, for example DE123456789. No VAT ID, say as a small
  business? Leave it empty."), no longer "VAT / tax ID", because the server
  checks it as a VAT ID; a national tax number has no field.
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
  ownership) is at `:230`; since `747ed6b` it first takes the owner's market,
  which must be live (422 `market_not_live`). Since `7444e37` the listing's
  district must be in the owner's country, and a `country` in the spec must
  be it (422 `district_not_in_country`); since `4e86866` the web's
  **Where is it?** lists only districts of the owner's country (V5-2).
  Categories, including their `dac7` tag, are in
  `backend/libs/cappy_common/cappy_common/categories.py`. Events:
  `listing.changed`. Screens: `AddListing.tsx`, `Earn.tsx`, `Listing.tsx`.
- **Private address:** the address is stored on `listings.address`
  (`catalog/tables.py:93`). Booking fetches it from `/internal/listings/{id}/handover`
  (`routes.py:779`) and shows it only in accepted, active, completed or disputed
  states (`SHOWS_HANDOVER`, `booking/repository.py:75`). Since `42c777c`
  (V4-9) `GET /api/bookings/{id}` reads it live while the booking is
  `accepted` or `active` (`LIVE_HANDOVER`, `booking/routes.py`), so an
  address the owner adds or corrects after accepting reaches the renter;
  once it is over the last copy stands, and if catalog does not answer the
  last copy is shown. Every seeded listing has an invented hand-over address
  (`listingAddresses` in `seed.json`: real streets, made-up numbers, V4-10),
  loaded by `load_seed`.
- **Provider:** none (Postgres).
- **Status and limits:**
  - Prices are integers in minor units of the listing's `currency`, one of
    thirteen ISO 4217 codes (EUR, GBP, CHF, SEK, NOK, DKK, PLN, CZK, HUF, RON,
    ISK since `747ed6b`, USD, CAD; `cappy_common/models.py`), since `235eeaa`
    (M-3). Since `747ed6b` (M-2) a listing without a currency takes its
    owner's market's, and any other currency is 422 `currency_not_in_market`.
    Every answer (listing, quote, booking, payment, invoice) carries it
    upper-case; only the Stripe calls lower-case it (migrations booking 0015
    and payments 0009 upper-cased stored rows). Nothing is converted. The
    price cap is the market's `max_rate_per_hour` (`_check_numbers`,
    `catalog/routes.py:299`). The web formats and inputs money per currency
    (`formatMoney`, `currencySymbol`: `web/src/domain/money.ts`, M-4) and
    gets the currency from the API. Since `2257182` the listing form never
    sends a currency: a new listing shows its owner's market's
    (`useMarket().currency`), an edit the listing's own.
  - **A point per listing** (since `61b15b8`, M-5/M-6): `location` (lat/lng),
    `country` and `postalCode` in the listing's spec (`models.py:164`). A
    point more than 30 km from its district's centre is 422
    `location_outside_district` (`MAX_KM_FROM_DISTRICT`, `routes.py:44`,
    `:268`): the district stays the search bucket. Public answers snap the
    point to the middle of a grid square of about 500 m (`snapped`,
    `SNAP_DEG`, `models.py:174`; `to_listing`, `repository.py:109-133`) and
    drop the postal code; the exact point and postal code go only to the two
    sides of an accepted booking, with the address (`/internal/listings/{id}/handover`,
    `routes.py:815`). Seeded listings stand at their district's centre. No
    geocoder fills it (M-7). Since `2257182` the web's listing form sends
    the district's centre as the point (kept on an edit that keeps the
    district), the district's `country` and an optional **Postal code**
    field; the listing page says "Approximate area" to everyone but the
    owner, and an accepted booking's "Getting in" card shows the address
    with its postal code and an **Open in a map** link to the exact point
    on openstreetmap.org. A listing has a time zone only through its weekly
    hours (`availability.timeZone`); since `7444e37` a booking snapshots it
    as `timeZone`, else the owner's market's `time_zone` (`markets.json`), and
    emails show times in it (M-15 for the rest). The address is free text
    (M-8).
  - **Weekly opening hours** (since `61b15b8`, H-4): an optional
    `availability` (`weekly`: day 1 to 7 with `HH:MM` start and end, up to 21
    rows; `timeZone`, default `Europe/Berlin`) makes the server keep windows
    open eight weeks ahead in the listing's own time zone, one day at a time
    so a DST change keeps the local hours, never overlapping a window
    already there (`catalog/schedule.py`, `apply_schedule` in
    `repository.py`). Changing the schedule replaces the future windows it
    made (`slots.generated`); an edit that leaves it out keeps it, `null`
    removes it. Since `1cb2d67` (V7-11) removing a hand-made window
    (`DELETE /api/listings/{id}/slots/{slot}`) brings the weekly hours it
    stood over back at once (`remove_slot`, `repository.py`); removing a
    generated window closes that time, though the hourly roll still refills
    it (a `ponytail:` note: holiday exceptions, H-4, will fix that). The
    catalog's hourly job rolls schedules on and, for a live
    listing with no free window in the next seven days, emits `listing.idle`
    at most once a week (`keep_schedules_once`, `catalog/jobs.py:66`), which
    notifications sends as "No free time next week" (EN/DE/FR, `bookings`
    category). Since `2257182` the web's listing form offers weekly hours:
    the presets (evenings, while I am at work, weekends, most of the time)
    are now weekly schedules the server keeps, **Set my own weekly hours**
    opens an editor of rows (days, from, until; 15-minute steps, "until"
    may be midnight), sent with the device's time zone, and only **Pick the
    dates myself** still makes windows in the browser. Editing a listing
    that repeats shows "Repeats every week" with **Stop repeating**, which
    sends `availability: null` (the windows it made go, windows added by
    date stay); an edit that picks nothing new leaves the key out.
  - **Held for where it is** (since `22b5e0f`, V5-1): the catalog's hourly
    job `hold_out_of_market_once` (`catalog/jobs.py:123-137`) holds every
    live listing whose district is not in a live market (`market_not_live`)
    or not in its owner's country (`district_not_in_country`, a listing made
    before either was checked): `held_at` and `hold_reason` set, `active`
    false, a warning logged, `listing.changed` `held` sent. `GET
    /me/listings` items and `/admin/listings/held` carry `holdReason`;
    approving one is 409 with that code, and the owner's `PUT` into an open
    market (the checks above passing) releases it. The job runs when
    catalog starts and then about hourly, 500 listings a run. In the demo
    world it holds the 29 seeded listings in Amsterdam, Paris, Lyon, Milan,
    Brescia and Lisbon (on a fresh stack at its first run after the seed,
    so within about an hour of `make up`). Web (`4e86866`): Earn shows **Not live** with why and what to
    do (`holdText`, `format.ts`), the console shows the reason instead of
    **Approve**.
  - **Batch quantity cap** (since `22b5e0f`, V5-22): a batch listing may set
    `maxQuantity` (at least 1); a request above it is not feasible ("takes at
    most N per booking", `matching/domain/feasibility.py`). Categories carry
    a `setupLabel` (freight "Loading", the rest "Setup and programming",
    `cappy_common/categories.py`), which the quote's `extraLabel` is for a
    batch listing. Web (`4e86866`): the form's **Most per booking
    (optional)** field, freight wording (**Vehicle**, **Pallets loaded per
    hour**, "take about … including … to load"; since `9107ad2` also
    **Loading time** and **Loading fee** in place of Setup, V6-15), and
    quantity chips that start at 1 and never pass the cap or the longest
    free window.
  - **A weekly window already under way** is cut to start at the next
    quarter hour instead of being dropped for the day (since `22b5e0f`,
    V5-23, `catalog/schedule.py` `windows`); less than a quarter hour left
    makes nothing.
  - The kill switch `ACCEPTING_LISTINGS` is at `catalog/settings.py:41`.
  - Account deletion clears the listing's title, blurb, instructions, rules,
    photos and address, and the personal parts of its spec, listed since
    `42c777c` in `privacy.LISTING_SPEC` (`cappy_common/privacy.py`):
    `extraLabel` and `machine` are blanked, and the exact `location` and
    `postalCode` are dropped (M-6; `forget`, `repository.py`). A test fails
    for a new personal-looking spec field that is not in the list. The row
    and its numbers stay for bookings and reviews (D-2).

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
  - **Renditions** (since `933ed14`, U-40): each public upload is also stored
    at 400, 800 and 1600 px wide as `<hash>-<w>.webp` (a width the photo does
    not reach is stored at its own size), and its dominant colour
    (`#rrggbb`, `media.color`) is recorded (`media.sizes`, `WIDTHS`;
    `upload` in `catalog/routes.py`). Evidence gets no renditions. The upload
    answers `color`; `GET /api/listings/{id}` adds `photoMeta`, one entry per
    `listing.photos` URL with `w`, `h`, `color` and `widths` (empty for a demo
    photo or one not yet backfilled). Uploads from before are filled in by
    the hourly `make_renditions_once` (`catalog/jobs.py`, 50 a run). The
    orphan sweep deletes and purges a photo's renditions with it. Locally
    `GET /media/<name>?w=` serves a rendition, falling back to the photo.
  - Web (since `0a74b1c`, UX-3): `Photo` builds a `srcset` from `photoMeta`'s
    widths and shows the photo's colour while it loads; Unsplash demo
    photos get a `w=` srcset; every image carries `width`, `height` and
    `sizes`, and the hero keeps `fetchpriority="high"`. In one grid a
    picture is shown once: a later card with the same picture shows its
    category's drawn plate instead (`PhotoGrid`, since `1daf0da`), and so
    does a listing with no photo (`Plate`, `Cover.tsx`).
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
- **Limits:** renditions are made at upload, not at the edge, so a new
  width needs a backfill. The server does not decode HEIC;
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
- **Account deletion** (since `747ed6b`): the hourly photo sweep purges every
  file it deletes from the CDN too (`catalog/jobs.py:44`), so a deleted
  person's photos leave the edge when the sweep reaches them. ~~An account
  deletion does not purge the person's photos~~: fixed in `747ed6b`.

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
- **Ranking:** hand-tuned weights (`W`, `matching/domain/match.py:64`): price
  0.3, soon 0.2, trust 0.3, near 0.2. Trust is cut by the owner's
  cancellation rate. This is explained on the ranking page (`Legal.tsx`,
  G-6). Since `61b15b8` (H-2) `GET /api/ranking` (`matching/routes.py:184`,
  public, cached like the vocabulary, its own CloudFront behaviour in
  `edge.tf`) serves the same `W` with a description of each signal
  (`SIGNALS`, `match.py:68`) and `textSearch: "newest first"`; a test fails
  if the two drift. Since `2257182` the ranking page (`/legal/ranking`,
  `Ranking` in `Legal.tsx`) reads it (`useRanking`, `repo.ts`): each signal
  with its weight as a percentage, its name and description translated by
  key (`SIGNAL`, EN/DE/FR, the server's description where a key is unknown),
  and a line when it cannot load. Browse links to it as **How results are
  ordered** beside the match count and the free-text results (H-3, P2B
  Art. 5).
- **Earliest start** (since `933ed14`): a window requirement searches from
  its own `earliest` when that is later than now (`find_matches`,
  `matching/domain/match.py`), so the web's **When?** day and **From** hour
  narrow the results; before, every search started now.
- **Distance** (since `61b15b8`): from the searched district's centre to the
  listing's own point when it has one, already snapped to about 500 m, else
  its district's centre (`point_of`, `match.py:44`), in matches, offers,
  spotlight and idle-nearby. Candidates are still gathered by district.
- **Starts per day** (since `ad9dee9`, V6-23): `GET /api/listings/{id}/offers`
  takes `perDay` (1 to 100), which caps each day's starts so a busy near day
  cannot use up `limit` and hide the days after it (`offers_for`,
  `matching/domain/availability.py`; days are the listing's own, in its
  weekly hours' zone or its owner's market's, since `090c890`). Since
  `1cb2d67` (V7-1) a day with more starts than the cap is thinned evenly
  (every k-th start), not cut: a 24-hour listing showed only 00:00 to
  13:30 before. Since `9107ad2` the
  listing page asks `limit=500&perDay=28`, its day rail shows two weeks of
  days (was one), and the duration being priced is always one of the chips,
  selected (V6-3).
- **Measured:** `make bench` (since `42c777c`,
  `backend/services/catalog/bench/candidates.py`) builds a throwaway
  database `scale` on the local Postgres with N synthetic listings (100 000
  by default, 3 windows each over the next month), times the candidate
  search (25 km over 7 days, 500 km over 30 days) and two free-text
  searches as the mean of 10 runs after a warm-up, and drops the database.
  Results are kept in `docs/bench.md`, one row per date, commit and
  conditions: at 100k, 14.7 ms and 20.2 ms for the two candidate searches,
  6.1 ms and 1.8 ms for the text searches, with the full stack and a browser
  test running on the same laptop. A laptop is not Aurora: the rows compare
  changes, they do not size production (L-5).
- **Provider:** none.
- **Limits:** a listing without a point is placed at its district's centre,
  and no geocoder sets points (M-7). The
  API works in km; the web shows distances and radius presets in miles for
  US and GB locales and km elsewhere (`formatDistance`, `formatRadius`:
  `web/src/app/format.ts:77-97`), though the presets are still km values
  converted, not round miles (M-18). The unit follows the formatting locale;
  since `2257182` the requirement chip on Browse uses `formatRadius` too
  (it printed "km" for everyone).
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
  not used. Since `ad9dee9` `/api/districts` comes ordered by city, then
  district, and since `9107ad2` `DistrictSelect` labels a district with its
  city ("Flon (Lausanne)"), sorted, unless its name already holds the city or
  it is one of several districts of its own city's metro (Berlin's) (V6-16).
- **Listing points:** since `61b15b8` a listing may carry its own point,
  country and postal code, snapped to about 500 m in every public answer
  (3.1, M-5/M-6). It is stored as JSON in the listing's spec, not as a
  PostGIS `geography(Point)`, and search still walks districts.
- **Seam:** none, and **no provider**: there is no geocoder, no autocomplete and
  no tile service.
- **To add one** (Amazon Location, Google Maps, Mapbox): this is M-7 (and the
  PostGIS part of M-5). Put a `Geocoder` interface in the catalog, called
  when an address is saved, filling `location`, `country` and `postalCode`.
  Store only storable results (`IntendedUse=Storage` on Amazon Location;
  Google's terms restrict caching). Public coordinates are already snapped
  (M-6, `61b15b8`). A tile
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
    currency, stored upper-case like every answer since `747ed6b` (M-3). Matching prices the
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
  - **Money on every booking** (since `1cb2d67`, V7-2/V7-3): every booking
    answer carries `charged`, `refunded` and `ownerShare` in minor units
    (`cappy_common/models.py` `Booking`). The list works them out from the
    booking's own facts (`money_of`, `booking/repository.py`: charged at
    accept, a cancelled booking only if it recorded a refund, the owner's
    share of what was kept). `paidOut` is only on `GET /api/bookings/{id}`,
    which overlays payments' real figures from
    `/internal/bookings/{id}/payment` (`payments_money`): a list cannot know
    whether a payout was held (payouts off, a chargeback), so it leaves it
    out rather than guess (D-24). The web renders the server's figures
    (`moved()`, `web/src/domain/pricing.ts`, since `d4a458a`, falls back to
    the booking's status only for an older answer; checked by
    `npm run check:money`, in CI): **What you agreed** on the booking page
    shows the charge, a `−` refund line, the fee and the owner's share of
    what stayed, "Refunded" when everything came back and "Nothing: hold
    released" when nothing was charged; **Past** in Bookings shows the net
    (the renter's cost after a refund, the owner's share) instead of the
    list price. Since `0a74b1c` (V8-1) a request that is only held
    (`awaiting_payment` or `requested`, `charged` 0) shows its **Total**, and
    to the owner the **Service fee** and **You receive**, with "Held on your
    card, charged when {name} accepts." (renter) or "Their card is held and
    charged when you accept." (owner); "Nothing: hold released" only once it
    is declined, withdrawn or lapsed. Since `0a74b1c` (V8-2) **Earn** and
    **Profile** add up the same figures: earned is the owner's share of
    completed and cancelled bookings (a renter no-show pays the owner),
    spent is `charged − refunded`, no longer the list prices.
  - **One price summary** (since `1daf0da`, UX-23, `PriceSummary.tsx`): the
    listing's price card and the confirm sheet show the same lines (the
    booking page's **What you agreed** keeps its own rows, with the fee
    named the same way, **Service fee · 15%**, and **You receive**): rate ×
    duration, extras, discount, then **Total** with
    "Includes the service fee of {fee}" to the renter, or **Renter pays**,
    **Service fee** `−` and **You receive** to the owner; the renter never
    sees the owner's net. The cancellation policy is a dated line ("Free
    cancellation until Sat 3 Oct, 10:00", `policyLine`, `format.ts`), and the
    **Book and pay** button carries the amount ("Book and pay · €16.00").
  - **Decline reasons as codes** (since `933ed14`, V8-3): the owner's four
    chips go as `reasonCode` (`already_promised`, `need_it_myself`,
    `needs_repair`, `short_notice`; `POST /bookings/{id}/decline` takes
    `{reasonCode}` or their own words as `{reason}`), system reasons are
    `taken_down`, `owner_removed`, `suspended`, `parent_cancelled`
    (`cappy_common/reasons.py`). Every booking answer adds
    `declineReasonCode` when the stored reason is one of them; the web words
    it in the reader's language by code (`REASON_TEXT`, `repo.ts`, since
    `0a74b1c`, V8-4/V8-5), and mails and the bell translate chips like the
    system reasons (`PHRASES`, `notifications/texts.py`). An owner's own
    words are quoted as written. A confirmed extension cancelled with its
    booking now says why on its page too ("Reason: The booking it extends
    was cancelled.").
  - **A repeated action is success** (since `73610c4`, V7-6): when accept,
    start, complete or cancel answers 409, the web reads the booking again,
    and if it is already where the action takes it, that is the answer
    (`actOnBooking`, `repo.ts`): a second **Accept** is quiet, not an error.
  - **Declined by Cappy** (since `73610c4`, V7-14): a request the system
    declined gets a headline that does not blame the owner (`SYSTEM_DECLINE`,
    `BookingDetail.tsx`): "Cappy removed this listing", "The listing was
    removed", "The booking this extended was cancelled", "Cappy stopped this
    request"; the reason line stays under it.
  - Screens: `Listing.tsx`, `Bookings.tsx`, `BookingDetail.tsx`, `Earn.tsx`.
- **Provider:** none (Postgres). Money moves through section 7.
- **Settings:** `booking/settings.py`: `PAYMENT_TIMEOUT_MINUTES` 30,
  `ANSWER_WITHIN_HOURS` 24, `AUTO_COMPLETE_AFTER_HOURS` 48,
  `START_EARLY_MINUTES` 30, `MAX_UNPAID`, `MAX_REQUESTS_PER_DAY`, and the kill
  switch `ACCEPTING_BOOKINGS` (`:52`).
- **Soonest start:** matching never offers a start sooner than
  `MIN_LEAD_MINUTES` (120) from now; locally compose sets 5 so every flow can
  be walked in minutes, and since `61b15b8` deployed settings refuse under 60
  (`matching/settings.py`). Booking likewise refuses `START_EARLY_MINUTES`
  above 60 and `AUTO_COMPLETE_AFTER_HOURS` under 24 when deployed.
- **Limits:** ~~one set of thresholds in minor units for every currency~~:
  per market since `747ed6b` (M-2, `markets.json`). Cross-cell bookings are not
  refused (M-23). ~~No extension or late return (S-12)~~: both since
  `7444e37` (5.6). No 3DS return into the store shells (U-7).
- **Retries (FL-1, `f42a4ef`):** every create in the web (booking, listing,
  message, rating, evidence, report) takes its `Idempotency-Key` from
  `attemptKeys` (`web/src/domain/attempt.ts`, `useAttemptKey` `repo.ts:554-556`):
  the same body keeps its key after a 5xx, a timeout or a lost connection, and
  gets a new one after a success, a 4xx or a changed body
  (`npm run check:attempt`).

### 5.2 Cancellation, no-shows, disputes

Either side can cancel before the start, with a refund preview. Either side
can report a no-show in the first two hours. The renter can dispute once the
window has started, and since `42c777c` at any time once the booking is
`active` (handed over early, V4-3). Cancel is never open from `active`: the
renter has the item, so a refund must not happen without staff. Since
`7444e37` the two sides first get 72 hours (`DISPUTE_OFFER_MINUTES`, 10
minutes locally since `b5cdd93`) to settle it themselves (5.5),
then staff decide: pay the owner, refund the renter in full, or refund part,
with a reason (13.7).

- **Where:** `_transition` (`booking/routes.py:291`, no-show windows
  `:310-323`), refund preview `GET /api/bookings/{id}/cancellation` (`:442`,
  with `charged`: false before the accept, when cancelling only releases the
  hold; FL-8, `235eeaa`), and since `7444e37` opening a dispute writes its
  `booking_disputes` row (`routes.py` `_transition`); settling it is in
  `booking/support.py` (5.5, 13.7). Screens: `BookingDetail.tsx`,
  `BookingExtras.tsx`, `AdminCases.tsx`.
  Since `2257182` the cancel sheet fetches the preview for every status and
  words itself by `charged` (a hold released versus money back), and a
  refused dispute keeps the sheet open with what was typed and an error
  toast (V4-4).
- **Provider:** none. The refund is carried as `refundAmount` on
  `booking.status_changed` and executed by payments (7.1). Every settlement
  goes through one `settle` (`booking/support.py:266-285`): refunding it all
  cancels the booking with `refund_amount` = `amount`; less completes it with
  `refund_amount` the part refunded (payments refunds that and pays the owner
  their share of the rest); paying the owner completes it with none. A
  cancellation before the accept records none (`routes.py:228-231`;
  `cancellation.py:31-36` returns 0 when nothing was charged).
- **Notifications:** a dispute tells the owner ("A problem was reported") and
  the renter ("We received your report"), since `235eeaa` (FL-2). Since
  `22b5e0f` (V5-7) its end tells both sides how it ended and what happens to
  the money (`booking.notice`, 12.1), and no "cancelled" or "How was …?"
  follows a dispute. Web (`4e86866`): a decided dispute shows **The reported
  problem was decided** on both sides' booking page (`DisputeDecided`), and
  a disputed booking's sticky button is **Get help with this booking**, its
  **Getting in** address stays shown (V5-32). Since `9107ad2` (V6-1) the
  decided banner reads **You agreed on the reported problem** when the
  parties settled it, and shows staff's note ("From Cappy’s team: …") when
  staff did. A no-show and an owner cancelling a confirmed booking tell both
  sides the money and how to contest (12.1, `ad9dee9`). Payments records a
  renter no-show (nothing back, the owner paid) as `transferred` (7.1).
- **Extensions end with their booking** (since `ad9dee9`, V6-22): cancelling
  a booking, a no-show too, declines its waiting extension ("The booking it
  extends was cancelled", EN/DE/FR; nothing was charged) and cancels a
  confirmed one with a full refund (`_end_extensions`, `booking/routes.py`).
  Since `1cb2d67` (V7-12) the cancelled one carries the same reason, and both
  sides are told why and what comes back (`extension_cancelled_renter`,
  `extension_cancelled_owner`, 12.1).
- **Limits:** ~~no dispute negotiation between the parties or deadlines
  (S-21)~~: since `7444e37` (5.5). No owner damage claim (S-8), which needs a
  saved card or deposit first (S-9); a late return can be claimed but is not
  collected (5.6).

### 5.5 Dispute offers and escalation (S-21, since `7444e37`)

Either side of a disputed booking offers how much of the price goes back to
the renter; the other accepts it and the dispute is settled at once, with no
staff. Each offer gives the other side 72 hours; when a deadline passes with
no agreement, the dispute goes to staff. Since `b5cdd93` the window is the
booking setting `dispute_offer_minutes` (`DISPUTE_OFFER_MINUTES`, 72 hours;
local compose sets 10, and a deployed service refuses under 72 hours,
`unsafe_reasons`).

- **Where:** `booking/support.py`: `GET /api/bookings/{id}/dispute`
  (`:296`), `POST …/dispute/offer` `{refundAmount}` (`:307`, 0 to the price;
  a new offer replaces the one on the table and restarts the window; emits
  `booking.dispute_offer` to the other side), `POST …/dispute/accept`
  `{refundAmount}` (`:345`, idempotent; the amount is sent back so nobody
  accepts an offer that changed: 409 `offer_changed`; your own offer is 403
  `own_offer`). Accepting records a `booking_resolutions` row (`role`
  `parties`, reason `agreement`) and settles (5.2). Booking's sweep marks
  disputes past `respond_by` escalated (`escalate_due`, `:389`,
  `booking/jobs.py:48-50`) and tells both sides ("We are deciding now").
  Staff see escalated disputes first (13.7). The parties can still agree
  after escalation, until staff decide.
- **Web** (`4e86866`): `DisputeOffers` in `BookingExtras.tsx`, under the
  disputed booking's banner: **Settle it between you**, the offer on the
  table ("{name} offers … back to the renter", "Of {total}. The owner is paid
  the rest."), **Accept {amount}**, **Make an offer** / **Make another
  offer** in a sheet, polled every 15 s. Since `9107ad2` (V6-5) no web text
  names a fixed 72 hours: the toast after an offer reads "Offer sent. {name}
  can answer until {day time}" from the server's `respondBy`, the escalated
  card "You did not agree in time…", and the owner reads "Of {total}. You
  are paid the rest." (V6-13).
- **Provider:** none.

### 5.6 Late returns and extensions (S-12, since `7444e37`)

- **Late return:** the owner reports it within 24 hours after the booked end
  (`LATE_RETURN_CLAIM_HOURS`, since `b5cdd93` a setting, refused under 24
  deployed; locally `LATE_RETURN_EARLY_MINUTES=100000` opens it long before
  the end, refused above 0 deployed; each booking answer carries
  `lateReturnFrom`, which the web follows instead of its own rule)
  (`POST /api/bookings/{id}/late-return` `{minutesLate, note?}`,
  `support.py:790`; `active`, `completed` or `disputed` only; one per
  booking). The claim is the extra time after 30 minutes' grace at the
  listing's hourly rate, rounded up to the quarter hour, plus a fee of one
  hour's rate capped at the market's `late_fee_cap` (`late_return_amount`,
  `:778`); within the grace it is 422 `within_grace`, outside the 24 hours
  409 `claim_window`, a second one 409 `claim_exists`. The renter is told
  (`claim_filed`). Staff confirm or reject it in the case view
  (`POST /api/admin/claims/{id}/decide`, `:847`), and both sides hear the
  decision. **Nothing is charged**: collecting needs a saved card (S-9), and
  a claim does not hold the owner's own payout. `GET /api/bookings/{id}/claims`
  lists them for either side. Web: `LateReturn` in `BookingExtras.tsx`, on
  the owner's booking page ("Came back late? Report it within 24 hours after
  the end. The first 30 minutes are free."). Since `73610c4` (V7-15) the
  renter's booking page shows the claim too, with its amount and Cappy's
  decision, and how to answer it: while it is open, "The owner says it came
  back late. Not so? Tell Cappy with “Get help with this booking” below…",
  once decided, "Questions about this decision? …"; only the owner can
  report one.
- **Extend:** the renter asks for more time straight after, while the
  booking is `accepted` or `active` and before its end, for a time booking
  (`POST /api/bookings/{id}/extend` `{hours}`, up to 24, `:881`). It makes a
  new booking of the same listing by the same renter (`bookings.extends_id`),
  priced and paid like any booking, instant if the listing is instant book,
  else a request the owner answers; matching skips the lead time and finds
  whichever idle slot holds the window (`extension`, 409 `not_extendable`
  when the time after is not free). Web: `Extend` in `BookingExtras.tsx`
  (1, 2 or 4 hours, **Book {duration} more and pay**), then the new
  booking's page. Since `9107ad2` (V6-4) the sheet offers only lengths the
  listing takes (from its minimum, up to its maximum), and matching's "not
  feasible: …" answers read as one translated sentence. Since `ad9dee9`
  every booking answer carries `extendsId`, and the extension's page links
  to the booking it extends ("This extends your booking before it."); an
  extension ends with its booking (5.2). Since `73610c4` (V7-7) an instant
  book extension's toast reads **Extended** (it answers `awaiting_payment`
  first, so the listing's instant book setting decides), else **Asked for
  more time**. Since `1cb2d67` the owner's notice of an extension request
  is its own kind, `requested_extension` ("Extension request: …", with the
  price, 12.1).
- **Provider:** none.

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
  the report window ("at the latest 48 hours after it ends") shown (U-33);
  on a completed booking that sentence gives way to "This booking is
  complete. Something still wrong? Get help with this booking below." Since
  `2257182` each pick adds to the photos chosen so far (a phone's camera
  returns one photo per pick, V4-13), up to 12, and each preview has a
  remove button; when a prompted sheet closes, focus goes to the photos
  panel (V4-22). Since `73610c4` (V7-22) photos taken from the hand-back
  question (**Handed back and all fine?** → **Add check-out photos first**)
  bring the question back once they are saved, instead of leaving the
  renter on the page.
- **Seam:** storage goes through the catalog's private `MediaStore` (3.3).
- **Limits:** evidence saved before `f303350` keeps its public URLs.

### 5.4 Blocks

A member blocks another: no messages and no new bookings between them, in
either direction.

- **Where:** `PUT/DELETE/GET /api/me/blocks` (`booking/messages.py:227-246`),
  enforced in `create_booking` (`booking/routes.py:156`) and `send`
  (`messages.py:141`). A report on a message offers **Block {name} too**
  right after it is sent (`Report.tsx`, U-13).
- **Web** (since `73610c4`, V7-5): a conversation with someone blocked shows
  no composer: "You blocked {name}, so no messages can be sent." with
  **Unblock** (`DELETE /api/me/blocks/{id}`, `Conversation.tsx`), or, when
  the server refuses with 403 because they blocked you, "Messages to {name}
  cannot be sent." The server's "you cannot message this person" reads as a
  translated sentence (`MESSAGE_TEXT`, `repo.ts`).
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
  `AddListing.tsx`. The booking page's first step reads **Booked**, not
  "Requested", for an instant booking (`2257182`, V4-23), and since
  `2257182` the English and German terms say the card is charged at once
  for an instant booking (legal copy for counsel).
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
- **Limits:** one fee for every market and category. `markets.json` (M-2,
  `747ed6b`) has no fee field, so a per-market fee is still open.

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
    transfers (7.2), and since `7444e37` on a completed that carries
    `refundAmount` (a dispute settled in part) it refunds that part and
    transfers the owner's share of the rest. Since `22b5e0f` a payment of
    which only part was refunded ends `partially_refunded`, `refunded` only
    when all of it went back, and since `b5cdd93` a cancellation with
    nothing refunded and the owner paid (a renter no-show) is `transferred`;
    `refunded_amount` and `paid_out_amount` record what moved (migration
    `0010_moved_amounts`, which also backfilled old no-shows; a partial
    refund from before it shows 0). The events it emits are `payment.captured`,
    `payment.refunded`, `payment.failed` and `payment.payout_sent` (since
    `22b5e0f` with the booking's `title`, `windowStart` and `timeZone`, for
    the notice).
  - Staff case view (since `7444e37`, H-9): `GET /internal/bookings/{id}/payment`
    (`payments/routes.py:358`) answers where a booking's money stands
    (status, amount, owner net, a chargeback, and since `b5cdd93`
    `captured`, `refunded` and `paidOut` as amounts in minor units, no longer
    flags).
  - Webhooks: `POST /api/payments/webhooks/stripe` (`payments/routes.py:419`),
    deduplicated by Stripe event id in `processed_events`. Since `747ed6b` the
    gateway forwards a signature header only to its own route
    (`WEBHOOK_SIGNATURES`, `gateway/main.py:47`: `stripe-signature` to
    `/payments/webhooks/stripe` and `/payments/webhooks/identity`); no other
    route receives it.
    `payment_intent.amount_capturable_updated` marks the payment authorised,
    which emits `payment.authorised` with the card fingerprint.
  - Reconciliation: `payments/jobs.py:29` looks up intents still `created`
    after 10 minutes, every 5 minutes.
- **Seam:** **yes,** `Provider` (`backend/services/payments/payments/provider.py:39`):
  `create_intent`, `client_secret`, `intent_status`, `capture`, `cancel`,
  `refund`, `transfer`, `card_fingerprint`, `create_account(owner_id,
  country)`, `onboarding_link`, `account_status`, `account_address` (since
  `42c777c`, the address the provider verified, for invoices, 8.1),
  `parse_webhook`, `aclose`,
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
     exemptions and the route with its signature header to
     `WEBHOOK_SIGNATURES` (`gateway/main.py:47`), one line.
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
    in the owner's country with the full service agreement, which would let a
    German platform pay US and Canadian accounts (`provider.py:160-175`, M-9);
    since `747ed6b` those countries are refused until their markets go live.
    A client per platform is M-10.
  - Charges are in the listing's currency (M-3, `235eeaa`), stored and
    answered upper-case and lower-cased only in the Stripe calls
    (`provider.py`, `747ed6b`); nothing is converted, and payout currency and
    FX are M-39.
  - No saved card or deposit (S-9). No 3DS return into the shells (U-7).
  - The kill switch is `PAYOUTS_ON` (7.2).

### 7.2 Owner onboarding and payouts

An owner sets up payouts on a Stripe-hosted page and is paid their share when
a booking completes, or their share of what was kept after a late
cancellation.

- **Where:**
  - `POST /api/payments/connect/onboarding` (`payments/routes.py:228`, Express
    account plus account link). Since `235eeaa` it takes `{"country": "CA"}`
    (default `DE`): the account is created in that country. Since `747ed6b`
    owners are paid only where Cappy is open: a country that is not a live
    market in `markets.json` (today anything but DE, AT, CH) gets 422
    `country_unsupported` (`routes.py:236`; `PAYOUT_COUNTRIES` is gone). Stripe fixes an account's country at creation.
    ~~The web sends no country, so every account is German~~: **fixed in
    `2257182`** (M-9): `startPayouts(country)` sends the profile's country
    (`Earn.tsx`), and `country_unsupported` reads in the app's language
    (`CODE_TEXT`).
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

A card holder's dispute with their bank. With separate charges and
transfers the platform carries it, so since `faebae7` (R2-3; runbook "A
chargeback") payments follows it to the end.

- **Where:** every `charge.dispute.*` webhook goes to `_chargeback`
  (`payments/routes.py:502-533`), which records the dispute's id, status and
  evidence deadline each time (Stripe sends them out of order):
  - **opened**: `chargeback_at` is set and `CHARGEBACK` is logged (the
    `chargeback` alarm opens a ticket, `observability.tf:167-190`). A
    completion that arrives while it is open is kept in `held_payout`, not
    dropped (`payments/handlers.py:178-181`).
  - **won** or `warning_closed`: the hold ends and a held payout is paid out
    with its fee invoice, once (`pay_out`, `handlers.py:64-94`).
  - **lost**: status `charged_back`; an owner already paid gives their share
    back through a transfer reversal (`recovered_amount`), and what their
    balance cannot cover is recorded as `owner_owes` (`_chargeback_lost`,
    `:536-552`).
  - **Staff** (admin, with MFA; gateway routes `/admin/payments/chargebacks`
    and `/admin/payments/{id}/dispute-evidence` to payments):
    `GET /api/admin/payments/chargebacks` lists open ones, soonest evidence
    deadline first, then lost ones still owed (`bookingId`, `disputeId`,
    `status`, `evidenceDueAt`, `amount`, `currency`, `paidOut`, `recovered`,
    `ownerOwes`); `POST /api/admin/payments/{bookingId}/dispute-evidence
    {text, links}` submits the text (20 to 20 000 characters) and links to
    Stripe, sets `under_review` and writes a `submit_chargeback_evidence`
    `staff.action` to the audit log; 409 once it is closed.
- **Seam:** partial. `Provider.submit_dispute_evidence` (Stripe:
  `disputes.update` with `uncategorized_text`, submitted) and
  `Provider.reverse_transfer` (Stripe: `transfers.reversals.create`,
  idempotency key `reversal-<booking>`) (`payments/provider.py`); the fake
  provider records both. Event names and statuses are Stripe's.
- **To swap it:** the new provider's dispute events mapped onto the same
  statuses, and the two provider methods.
- **Limits:** evidence is text and links only; photos are attached as files
  in the Stripe dashboard (ponytail in `provider.py`). `owner_owes` is
  recorded, not collected: nothing takes it from the next payout yet, and no
  console screen shows the chargebacks list (the API only).

---

## 8. Invoices and tax

### 8.1 Fee invoices to owners

Each payout (or kept late-cancellation fee) issues an invoice for Cappy's
fee. Numbers have no gaps per year, and an invoice never changes once issued.

- **Where:** `issue` (`backend/services/payments/payments/invoices.py:65`,
  under a row lock on `invoice_counters`), `GET /api/payments/invoices` (`:165`,
  with a `description` line) and `GET /api/payments/invoices/{number}` (`:174`,
  printable HTML with § 14 (4) UStG fields). Since `ad9dee9` (V6-21) the
  printable invoice is in the reader's language, from the app's
  `Accept-Language` (EN, DE or FR; German without one; `LABELS`, `_lang`,
  `_money` in `invoices.py`): the service is named by the listing ("Platform
  fee for {title}"), the booking id is a separate "Booking reference" line,
  and the German issuer's VAT ID and tax number are on it in every language
  ("Tax number (Steuernummer)"). Since `1cb2d67` (V7-10) it follows the
  reader's typography too: French puts a no-break space before `:` and `%`,
  English writes "19%" and German "19 %"; the tax is "VAT" in English and
  "TVA" in French (the `INVOICE_TAX_LABEL` in German); dates read
  `dd.mm.yyyy` in German, `m/d/yyyy` for `en-US` and `dd/mm/yyyy` otherwise,
  and a service period of one day is one date. Locally both issuer lines
  show (`LEGAL_VAT_ID` defaults to "DE000000000 (local)", which a deployed
  service refuses). Tables `invoices` and
  `invoice_counters` (`payments/tables.py:64-94`). Screen: `Earn.tsx`; since
  `2257182` its list line is built in the app ("Service fee · title ·
  dates", dates in the reader's locale) instead of the server's
  `description`, which carries a German date (V4-8).
- **Recipient address** (since `42c777c`, V4-7, § 14 (4) Nr. 1 UStG): a
  trader's business address; otherwise the address the payout provider
  verified for the owner, asked for when the invoice is issued
  (`Provider.account_address`, `payments/handlers.py` `_address`, passed to
  `issue` as `verified_address`). `StripeProvider` reads the connected
  account's company or individual address into one line; `FakeProvider`
  answers "Musterstraße 1, 10115 Berlin, DE (test)". Best effort: a slow or
  failing provider leaves the address out rather than holding the invoice
  (valid under § 33 UStDV up to €250 gross).
- **Seam:** partial. `Issuer` (`invoices.py:34`) makes the time zone, tax rate,
  label and retention period data (`INVOICE_TIME_ZONE`, `INVOICE_TAX_RATE_BPS`,
  `INVOICE_TAX_LABEL`, `INVOICE_RETENTION_YEARS`, `payments/settings.py:37-40`).
  The issuer's name, address and tax ids are `LEGAL_*` (`:32-35`, Terraform
  `legal`, required deployed).
- **Retention** (since `235eeaa`, D-9): `purge_invoices_once`
  (`payments/jobs.py:61-77`, daily) deletes invoices once the issuer's period
  (10 years by default) has run from the end of the year of issue
  (`docs/retention.md`).
  The template, its three languages and the number series are code.
- **To swap it** (for example to an invoicing service or Stripe Invoicing): call
  it from `issue` and store its invoice id on `invoices`. Keep the local number
  series if the provider cannot guarantee gapless per-entity numbering. Keep the
  legal retention (GoBD) and the purge after it.
- **Limits:**
  - One issuing entity for everyone. The per-market entity, template and series
    are M-13.
  - Dates are in `Europe/Berlin` by default.
  - ~~A private owner's invoice carries only their name~~: **fixed in
    `42c777c`**, it carries the provider-verified address (above). The
    address is copied onto the invoice, so a new provider must answer
    `account_address` or private owners' invoices go without one.
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
booking above its market's threshold (€300 in DE and AT, CHF 280 in CH), or in
categories configured for it.

- **Where:**
  - Gate: `create_booking` returns 403 `verification_required` when the total
    is above the listing owner's market's `id_check_above` (`markets.json`,
    in that currency's minor units; since `747ed6b`, `VERIFY_ABOVE_CENTS` is
    gone) or the category is in `VERIFY_CATEGORIES` (`booking/routes.py:162`,
    `booking/settings.py`) and the person is not in `verified_people`.
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
  - Web: the sheet needs the consent box ticked; `verify` (`Listing.tsx`)
    sends `{consent: true}` (`startIdentity`, `web/src/data/repo.ts`). Since
    `2257182` (F-1) a session that answers a hosted `url` opens it in a new
    window; otherwise, when `identityProvider` is `stripe` (or absent), it
    loads Stripe.js on demand and calls `stripe.verifyIdentity(clientSecret)`.
    It then polls for the webhook's result, up to a minute (two for a hosted
    page), stops on `failed` with "The ID check did not go through", and
    retries the booking with the same attempt once verified.
- **Seam:** backend **yes** since `235eeaa` (F-1): `IdentityProvider`
  (`payments/identity.py:48-58`: `name`, `verifies_immediately`,
  `start_session`, `parse_webhook`, `redact`), with `StripeIdentity` (`:78`)
  and `FakeIdentity` (`:115`, a started check is a passed check), chosen by
  `make_identity` (`:132`) from `IDENTITY_PROVIDER` (`payments/settings.py:24`:
  `stripe` or `fake`; empty follows `PAYMENTS_PROVIDER`; `fake` refused
  deployed, `:50-51`). Routes and handlers see only `IdentitySession` and
  `IdentityResult`. `/payments/config` names the provider (`identityProvider`).
  Web: **yes** since `2257182`: the hosted `url` or the Stripe.js modal, as
  above.
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
     already exempts `/api/payments/webhooks/`; the gateway forwards a
     signature header only to the route named in `WEBHOOK_SIGNATURES`
     (`gateway/main.py:47`, `747ed6b`), so add the vendor's header there.
  4. Web: a hosted flow needs nothing more, since the app opens the
     session's `url` (`2257182`); an embedded SDK would be a branch in
     `verify`. The shells may need camera permission strings (S-2). Update
     the CSP.
  5. Data: existing `verified_people` rows and `owners.verified` stay valid.
     The `identities` rows point at Stripe sessions; keep them as history.
     `payment.identity_verified` keeps its name.
  6. Legal: a DPIA (G-B3), explicit consent for biometric data, recorded before
     the check (P-17; keep the `consent_version` wording in step with the
     app's text), the vendor's DPA and its data location.
- **Limits:**
  - The verified name is not compared with the profile (the rest of P-28).
  - The consent is recorded per person and overwritten on each new session.
    ~~It is not in the data export~~: `consentAt` and `consentVersion` are,
    since `747ed6b` (`payments/routes.py:381`).
  - ~~One threshold for every currency~~: per market since `747ed6b` (M-2).
    It is the owner's market, not the renter's.

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
  `web/src/app/components/Conversation.tsx` (sender warning, receiver
  banner). Since `2257182` the app closes the composer on a completed booking
  past its 14-day review window too, and on a 409 `conversation_closed`
  closes it with the reason; a closed conversation shows no "No messages
  yet" invitation (FL-18, V4-18). Since `4e86866` the thread is keyed by the
  booking's status (`useMessages(bookingId, status)`), so accepting,
  cancelling or any other change reads it afresh and masking follows at once
  (V5-5); the meta line under a bubble is a `<div>`, so the report sheet is
  no longer inside a `<p>` (V5-15). Since `1daf0da` the chat scrolls inside
  its own box, not the page.
- **Inbox** (UX-12; screen since `1daf0da`, served by the API since
  `933ed14`/`0a74b1c`): `GET /api/inbox?cursor=&limit=`
  (`booking/inbox.py`) lists every conversation the person has, as renter
  or owner (the owner only once the card is held), newest message first:
  `bookingId`, `otherName` (from the booking snapshot), `listingTitle`,
  `photo`, `status`, `lastMessage` (`body`, `at`, `mine`; masked as the
  thread is) and `unread`, plus a top-level `unread` for the dock badge.
  `POST /api/inbox/{bookingId}/read` (204, 404 for a non-party) records when
  the person opened it (`message_reads`); unread is the other side's
  messages after that. The web's **Inbox** tab (`Inbox.tsx`, dock order
  Explore · Bookings · Inbox · Earn · You) asks for 50 threads, every 30 s
  and on focus, with **All** / **Unread**; a row opens the booking at
  `#messages`, and opening a thread whose last message is the other side's
  marks it read (`Conversation.tsx`), on every device.
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
  - The inbox shows the first 50 threads; older ones (`next`) have no
    "more" button yet.

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
  - Web: `web/src/app/components/Reviews.tsx`, `BookingDetail.tsx`. Since
    `4e86866` the confirmation depends on whether the other side has rated
    (V5-6): the first rater reads "Thanks. {name} will see it once they have
    rated too.", the second "Review posted on …" (renter) or "Thanks. Both
    ratings are published now." (owner).
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
  dispute (`:74-82`, FL-2); since `7444e37` the other side of a dispute
  offer (`dispute_offer`, with the deadline), and since `22b5e0f` every
  `booking.notice` (`:66-79`, V5-7) to whom it names: `dispute_refunded`,
  `dispute_partial`, `dispute_owner_paid` ("Settled: …", both sides, with the
  amount and "You agreed a settlement:" or "Cappy decided:"),
  `dispute_escalated` (both), `claim_filed` (the renter), `claim_confirmed`
  and `claim_rejected` (both); the settlements and claim decisions are always
  emailed (`ALWAYS_EMAILED`, `prefs.py:70`). A booking leaving `disputed`
  sends no status mail of its own (`:91-94`). Since `22b5e0f` the payout
  notice names the listing and its start ("Your share for Table saw, Sat 3
  Oct, 10:00…", V5-13, never the booking id) and a decline carries "Reason:
  …" when the owner gave one (V5-16); message notices are emailed at most once per
  conversation per 15 minutes, checked against the inbox (`_recently_told`,
  `:85-99`, `notify` `:174-186`, FL-3). Texts: `texts.py:12` (EN/DE/FR, with
  French since `235eeaa`: one neutral French for France and Québec,
  « courriel »), chosen by the reader's remembered app locale, else Cognito's
  `locale` (below; `language`, `texts.py:202-205`:
  `de…` and `fr…`, anything else English). Amounts are formatted per currency
  and language (`money`, `:251-265`). Times (`when`, `texts.py:255`) are
  24-hour for German, French and European English, and since `42c777c`
  12-hour ("Sat, Sep 26, 2:00 PM") for an `en-US` or `en-CA` locale; since
  `2257182` the app sends the full locale (language plus the device's
  region) as `Accept-Language` and as the Cognito `locale`, so this reaches
  emails, pushes and the bell. Since `7444e37` times read in the listing's
  time zone (`timeZone` on booking's events), not always Berlin. Sender:
  `Mailer` (`mail.py:37`), `SesMailer` (`:106`, SES v1 `SendEmail`, plain text),
  `LogMailer` (`:124`). Selected in `notifications/main.py:26` by `MAILER`
  (`log` or `ses`; deployed must be `ses`, `settings.py:12,25`) and `MAIL_FROM`.
  Always-emailed kinds are in `prefs.py:61-72` (since `235eeaa` also
  `payment_failed`, `disputed_owner`, `disputed_renter`). Since `61b15b8`
  `listing.idle` becomes `listing_idle` ("No free time next week: …", in the
  `bookings` category, linking to `/earn/edit/<id>`; 3.1). Money formats ISK
  with no decimals, like HUF (`747ed6b`).
- **Whose language** (since `ad9dee9`, V6-6): every email is written in the
  reader's own locale, never the triggering person's. The bell remembers the
  app's `Accept-Language` per person (`seen_locale`, `prefs.py`, in
  `notification_prefs.locale`, migration `0008_person_locale`, written only
  when it changes); `deliver` uses it before Cognito's `locale`, which stays
  the fallback for someone who never opened the app. The data export carries
  it as `appLocale`.
- **Server words and typography** (since `e2e77ab`, V5-16/18/19): words the
  server makes up that reach a reader as params (a system decline reason,
  the default DSA clause, the fallback title "your booking") are told in the
  reader's language (`PHRASES`, `phrase`, `texts.py`); a person's own words
  stay as written. A decline reason is its own paragraph with one full stop
  (`_reason`). French text gets a no-break space (U+00A0) before `:` and,
  since `ad9dee9` (V6-17), a narrow no-break space (U+202F) before `; ? !`
  (not inside a URL or a time), and never two full stops (`french`), and
  every text says « la personne locataire ». `tests/test_texts_every_kind.py`
  renders every kind in EN, DE and FR and fails on a missing kind, different
  placeholders, English left in a translation, an unfilled placeholder, two
  full stops, or the wrong space before French punctuation. Since `1cb2d67`
  (V7-24) people's own words (an owner's decline reason, staff's note) are
  quoted as written, never re-typeset (`quoted` in `render`), and a reason
  ending in `!` or `?` gets no extra full stop.
- **Money and time in request mails** (since `1cb2d67`, V7-23): `requested`
  names the price ("Someone wants to book {title} for €15.00…") and the
  booked start, `accepted` adds "You paid …" and "The hand-over address is
  in the app." (`for_amount`, `paid`, EN/DE/FR). New kinds, all `bookings`:
  `requested_extension` to the owner ("Extension request: …", with the
  price); `extension_cancelled_renter` and `extension_cancelled_owner`
  ("Extension cancelled: …", why and the refund; always emailed, V7-12);
  and `dispute_refunded_renter`, `dispute_partial_renter`,
  `dispute_owner_paid_renter`, which the renter gets instead of the
  third-person settlement text (`RENTER_READS`, `handlers.py`; always
  emailed). Booking's notices carry `requesterId` for that
  (`booking/support.py` `notice`) and status events `extendsId`.
- **The staff note** (since `b5cdd93`): a dispute settled by staff carries
  their note to both parties in the "Settled" notice, as its own paragraph
  under "From Cappy's team:" (`_note`, EN/DE/FR); an item stored before notes
  existed still renders. Since `ad9dee9` (V6-1) the bell shows it too (12.4).
- **No-shows and owner cancellations** (since `ad9dee9`, V6-11): a no-show
  cancellation (`noShow` on the event) tells both sides who was reported,
  the money and how to contest: the owner missing gives the renter
  `no_show_owner_renter` ("Refunded: …", the full price) and the owner
  `no_show_owner_owner` ("Reported as a no-show: …", it counts against their
  reliability, contest through Get help); the renter missing gives the owner
  `no_show_renter_owner` ("No-show recorded: …", paid as for a late
  cancellation) and the renter `no_show_renter_renter` ("Reported as a
  no-show: …", nothing refunded, contest through Get help). An owner
  cancelling a confirmed booking gives the renter `owner_cancelled`
  ("Cancelled by the owner: …", with the amount back). All five are
  `bookings` and always emailed. The escalation notice says "no agreement in
  time" rather than "within 72 hours", since the window is a setting (5.5).
- **Second person to the reader** (since `933ed14`, V8-9): owner-facing
  settlement and claim mails say "you": `dispute_refunded` "…and you are not
  paid for this booking", `dispute_partial` "…and you are paid the rest",
  `dispute_owner_paid` "you are paid in full", `claim_confirmed` "you are
  owed {amount}". The renter gets `dispute_offer_renter` ("you get {amount}
  back") instead of `dispute_offer` (booking's `booking.dispute_offer` now
  carries `requesterId`) and `claim_confirmed_renter` instead of the
  owner's text. `claim_filed` tells the renter to contest "through Get help
  on the booking", the same route as the page (V8-10). A test refuses third
  person to the reader (`test_texts_every_kind.py`).
- **What happened, not "declined"** (since `933ed14`): a decline nobody made
  (`by: system`: take-down, removal, suspension, the extended booking ended)
  is `declined_system` ("Could not go ahead: …", V8-17); an accepted
  extension is `extension_confirmed` ("Extension confirmed: …") and an
  instant one tells the owner `instant_extended` ("Extended: …") instead of
  `instant_booked` (V8-18). The owner's decline chips reach the renter
  translated (`PHRASES`, V8-3).
- **A signed-out reporter's language** (since `933ed14`, V8-12): the report
  keeps the form's `Accept-Language` (`reports.reporter_locale`), and
  `report_received` and the outcome mails are written in it (`_locale` on
  the message).
- **A deleted renter leaves the owner's bell** (since `933ed14`, D-27): on
  `profile.deleted` the owner's request notices that named them lose the
  name (`_unname`, `handlers.py`); the email already sent stays.
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
  An item's `body` is the text's first paragraph, except a decision about the
  reader's content or account (`taken_down`, `suspended`,
  `content_removed`), which carries the whole statement of reasons (since
  `22b5e0f`, V5-31, `summary`, `texts.py:315-321`); the web keeps its line
  breaks (`4e86866`). Since `ad9dee9` (V6-1) a settlement's item keeps
  staff's "From Cappy's team: …" paragraph after the first one, and since
  `1cb2d67` (V7-4) a decline keeps its "Reason: …" paragraph. Reading the
  bell also remembers the app's locale for that person's emails (12.1).
  This is the bell (**Notifications**, its badge on the **You** tab); the
  conversations have their own **Inbox** tab since `1daf0da` (section 10).
  Since `933ed14` (D-27) a deleted renter's name is taken out of the
  owner's items that named them.
- **Retention** (since `747ed6b`): items older than `INBOX_RETENTION_DAYS`
  (365) are deleted by an hourly loop (`expire_inbox_once`,
  `notifications/jobs.py:16`; `docs/retention.md`).
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
  email switch works since `235eeaa` (FL-3). ~~The Profile text says
  "Everything also arrives by email"~~: **fixed in `2257182`**: it says
  booking changes always arrive by email and messages at most one every 15
  minutes per conversation, and a line under the table says booking
  confirmations and changes arrive by email whatever is chosen.

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
  FL-10, `f22f143`). Since `2257182` the sheet's "If someone is in danger,
  call {number} first" and the reporting page use the market's emergency
  number (112, 911…), not a fixed 112. Since `4e86866` (V5-12) the device's
  region counts only when Cappy is live there (`useMarket`, `repo.ts`), so a
  signed-out reader with an en-US browser gets 112 (the first live market),
  not 911. The reason select starts at **Choose a reason**, not "Fraud"
  (V5-32). Since `1cb2d67` the two refusals carry codes: 429
  `reports_today` ("We already have your reports from today; we will be in
  touch.", the anonymous per-email cap) and 429 `reported_enough` ("This has
  been reported many times today; it is already being looked at."). The
  web reads both codes in `CODE_TEXT`, in English, German and French
  (`d4a458a`). Since `933ed14` (V8-19) a report of something that does not
  exist is refused before it reaches staff: 404 `report_target_unknown`
  (the web: "We could not find that. Paste its link from the app."); a
  message is checked with booking, and if booking cannot answer, the report
  is taken. A signed-out reporter's mails are in the form's language
  (V8-12, 12.1).
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
  the author is told ("We removed something you wrote"). Since `747ed6b`
  every recorded decision names whom it is about (`moderation_actions.person_id`:
  the listing's owner, a message's or review's author), so that person's
  export finds it. `suspend` finds the
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
- **Names, not ids** (since `1cb2d67`/`73610c4`, V7-19/V7-26): the queue's
  items carry `targetLabel` (an owner's name, a listing's title) and, for a
  review, `targetText` (`_labelled`, `moderation.py`). The console names the
  target from `targetLabel` (`d4a458a`; no lookups of its own), a listing
  report links to the staff view `/admin/listing/{id}`, and the decision
  sheet opens with what was reported (reason, target, the reporter's
  details) and quotes a reported review's `targetText`.
- **Console:** for a message or review report it offers **Remove the
  message / review** and **Suspend the author** (`Admin.tsx:33-42`, `:334`),
  which the server accepts since `235eeaa` (they answered 422 before). It
  also lists held listings and approves them (`getHeldListings`,
  `approveListing`, `repo.ts`; 13.3). Since `2257182` the decision sheet
  opens fresh for each report (at Dismiss, with an empty statement: it is
  keyed by the report, V4-2), decisions and audit entries read in words
  ("Taken down", "Refunded the buyer"; `DONE_LABEL`, V4-15). Since
  `4e86866` the console's **Act directly** has only take down, suspend and
  reinstate: money decisions moved to the case page (13.7), and the audit
  log is the paged one of 13.7.
- **Earlier decisions attributed** (since `42c777c`): migration catalog
  `0018_decisions_on_reviews` sets `person_id` on review decisions recorded
  before `747ed6b` from the review's author, and the hourly job
  `attribute_decisions_once` (`catalog/jobs.py`, 100 rows a run) asks
  booking who wrote each such message (`message_author`); a message booking
  no longer knows stays unattributed. The job is marked to be dropped once
  no such rows remain.

### 13.3 Held listings (fraud rule)

A new owner's listing above its market's threshold (€100 an hour in DE and
AT, CHF 95 in CH) waits for a staff check.

- **Where:** `create_listing` and `update_listing` (`catalog/routes.py:583`,
  `:623`), the owner's market's `held_listing_above` (`markets.json`, since
  `747ed6b`; `REVIEW_ABOVE_CENTS` is gone), and admin `GET /api/admin/listings/held` (each with its
  `currency`) and `POST .../approve` (`moderation.py:568-605`). The owner can open their
  held listing (`catalog/routes.py:453-473`, FL-6). Since `22b5e0f` a
  listing is also held for where it is (`hold_reason`, 3.1), which staff
  cannot approve (409). Since `4e86866` the console's held card shows the
  owner's name, jobs done and year joined, the price in the listing's
  currency where the answer has one, and the hold reason in place of
  **Approve** (V5-4); the title no longer links to the listing page, which
  staff cannot open while it is held.
- **The staff preview** (since `e2e77ab`/`eaeb485`, V5-4): `GET
  /api/admin/listings/{id}` (catalog `staff_listing`, `moderation.py`) answers
  any listing, live, held, paused, taken down or deleted, as its public
  detail (`detail_of`, shared with the listing page) plus `state`,
  `holdReason` and `heldAt`; the public page still answers 404 to everyone
  but the owner. Since `ad9dee9` (V6-2) it also carries `handover` (address,
  instructions, point, postal code) and up to 20 `reviews`, and matching
  answers staff's own `GET /api/admin/listings/{id}/offers?hours=&perDay=`
  (the next 28 days) and `POST /api/admin/quote` with held listings included
  (`admin` router in `matching/routes.py`, `require_admin`; catalog's
  internal `listing-context` takes `staff=true`; the gateway routes both to
  matching). Web: `/admin/listing/:id` (`AdminListing` in `AdminCases.tsx`,
  reached by **Look at it** on a held card and **Open the listing (staff
  view)** on a case) renders the listing page read-only under a **Staff
  view · {state}** banner, with **Approve** on an ordinary hold (never on a
  hold for where it is). Since `9107ad2` it prices and lists free times
  through the staff endpoints, shows the **Hand-over address** and the
  reviews, hides **Report** and **Block**, and shows no duration or start
  times for a listing nobody can book (paused, taken down, deleted, or held
  for where it is).
- **Provider:** none.

### 13.4 System notices: reliability and ban evasion

- **Owner reliability (S-18):** booking counts an owner's cancellations and
  no-shows over 12 months (`booking/repository.py:208`). It emits
  `booking.owner_reliability`, which becomes `owners.cancellation_rate`, a
  ranking signal (4.1), shown on the listing. Since `61b15b8` the same event
  also carries the owner's measured response time and rate (H-1, 2.1); each
  event carries one of the two, and catalog leaves the other as it was. Three failures in 30 days emit
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

### 13.7 Staff case view, resolutions (four eyes) and the audit log (since `7444e37`)

- **Cases (H-9):** `GET /api/admin/bookings` (`booking/support.py:666`) finds
  bookings by `booking` id, by `member` (an id, or an email looked up in
  Cognito with `ListUsers`: the `People` seam, `CognitoPeople`,
  `booking/clients.py`), by `status` (`disputed`: escalated ones first) or
  with open claims (`claims=open`), most recently changed first, paged. Each
  row has the dispute (with the offer on the table), whether a resolution
  waits for approval and the open claims. `GET /api/admin/bookings/{id}/case`
  (`:710`) answers everything on one page: the booking, the timeline of
  transitions, the whole conversation as written (what masking hid too),
  the hand-over photos as short-lived links, the payment (7.1: `captured`,
  `refunded` and `paidOut` as amounts in minor units, payments' own
  statuses), the dispute, the resolutions and the claims. Opening a case, and reading a booking's
  evidence as staff, is logged (`read_case`, `read_evidence`). Since
  `e2e77ab` each timeline entry carries `actorKind`: `person` (a party, `by`
  their id), `staff` (`by` the staff id) or `system` (a payment result or a
  sweep, `by` always `cappy`, never a service name).
- **Resolutions (H-6):** `POST /api/admin/bookings/{id}/resolve`
  `{outcome: pay_owner | refund_buyer | partial, refundAmount?, reasonCode,
  note}` (`:471`, idempotent; the answer is `{resolution, booking}` since
  `7444e37`). A refund within the staff member's limit for the booking's
  market and role (`refund_limit_support` 25 000 or `refund_limit_lead`
  250 000 cents in DE and AT) settles at once (5.2), and the staff note goes
  to both parties in the settled notice, as written; above it the resolution
  waits as `pending_approval` and nothing moves. `GET /api/admin/resolutions`
  lists them oldest first; `POST /api/admin/resolutions/{id}/approve` settles
  it (someone other than the proposer, 403 `four_eyes`; a non-lead only
  within their own limit, else 403 `needs_lead`) and `/reject` leaves the
  booking in dispute. A second resolution while one waits is 409
  `approval_pending`. Since `e2e77ab` `POST
  /api/admin/resolutions/{id}/withdraw` lets the proposer (only them, else
  403 `not_yours`; only a waiting one, else 409) take it back as `withdrawn`
  (audited, `withdraw_resolution`), so the case can be decided again and one
  staff member alone never stalls it; `GET /api/admin/resolutions?status=`
  accepts `withdrawn`. Since `ad9dee9` (V6-10) its items also carry `title`,
  `requesterId`, `ownerId` and `ownerName`. The settled dispute
  (`GET /api/bookings/{id}/dispute` and the case's `dispute`) carries
  `outcome`, `refunded`, `settledBy` (`staff` or `agreement`) and
  `staffNote` (V6-1). The internal twin (`POST /internal/bookings/{id}/resolve`,
  support tooling) applies the support limit and needs `by`.
- **Claims:** `POST /api/admin/claims/{id}/decide` `{decision: confirm |
  reject, note}` (5.6).
- **Audit log (H-7):** every staff action in any service is one row of
  catalog's `moderation_actions`: moderation writes there directly, booking
  sends `staff.action` events (resolve, propose, approve, reject, withdraw,
  claim decisions, case and evidence reads) that catalog stores once each
  (`on_staff_action`, `catalog/moderation.py:538`). `GET /api/admin/audit`
  `?target=&actor=&cursor=` (`:488`) is paged, newest first, with the person
  and request id; nothing updates or deletes a row. Since `ad9dee9` (V6-9)
  booking's lines carry `details` (`bookingId`, `listingTitle`, `currency`
  and, as they apply, `outcome`, `amount`, `reasonCode`, `resolutionId`,
  `claimKind`, `claimId`), stored in `moderation_actions.details` (migration
  `0021_audit_details`), and the `statement` is only what staff wrote (empty
  for a read), never machine text. A case or evidence read repeated by the
  same person within the same minute is one line: booking sends a `dedupe`
  key and catalog derives the row id from it. Since `1cb2d67` (V7-13) a
  `read_case` or `read_evidence` within 60 s of the same staff member's
  last read of the same target is dropped, so a refetch that crosses a
  calendar minute no longer makes a second line. Since `933ed14` (V8-11)
  `GET /api/admin/audit` adds `targetLabel` (the owner's name or the
  listing's title) and `personName` to each line's `details` when it reads
  the log, so older lines get them too and a renamed listing reads as it is
  now; a claim decision takes `noteCode` (`from_record` or
  `not_supported`) for Cappy's own words, and `note` is only what staff
  typed. Since `faebae7` payments sends `submit_chargeback_evidence`
  (7.3).
- **Web** (`4e86866`): `web/src/app/screens/AdminCases.tsx`. The console
  (`/admin`) opens with **Cases** (disputed or all; member id or email,
  booking id, only with open claims; **Next page**), **Waiting for approval**
  (approve or reject with a "Why" of at least 5 characters) and, at the end,
  the paged **Audit log** in words ("Resolved a dispute", "Opened a case",
  "Looked at hand-over photos"; filter by target and staff id; **Older**).
  The case page `/admin/case/:id` shows the dispute banner (escalated or
  not, the offer), the people by name, **Decide the dispute** (refund in
  full, refund part with an amount, pay the owner; a reason and at least 10
  characters of "What you found"), the refund decisions with who proposed
  and approved them, the claims with **Confirm** and **Reject**, the
  timeline, the conversation as written, the hand-over photos and the
  payment. Since `eaeb485`: **Withdraw my proposal** on the proposer's own
  waiting proposal (the case page and **Waiting for approval**, where the
  proposer gets it instead of **Approve** and **Reject**); **Open the
  listing (staff view)** (13.3); timeline steps by a party read renter or
  owner, by staff "you" or "staff {id}", by the system **Cappy
  (automatic)**; the dispute banner only while the booking is disputed.
  Since `9107ad2`: while a proposal waits, a **Decide** card stands in for
  the form ("A proposal is waiting for a second staff member: … Nothing
  else can be decided until it is approved, rejected or withdrawn.", with
  **Withdraw my proposal** for the proposer); the section is **Decisions**;
  approval cards name the listing and owner; the audit log renders
  `details` in words (listing · outcome · money · reason, then the note;
  rows from before `details` have their old machine line read into words,
  and bare echoes such as "withdrew rs_…" are dropped); the case is fetched
  once per opening (no refetch on focus); case cards show the offer and
  "Escalated" only while disputed, and "1 open claim" in the singular.
  Since `0a74b1c`: audit lines name the listing, owner or person
  (`listingTitle`, `targetLabel`, `personName`; "this booking" or "(no longer
  here)" as the fallback, never a raw id), a claim's statement is worded by
  its code in the reader's language ("Confirmed from the booking record",
  "Not supported by the booking record"), and "Confirming records the claim;
  nothing is charged to the renter yet." shows only while a claim is open
  (V8-15). The staff listing view says "Durations it takes" and "Start
  times" instead of speaking to a renter (V8-13).
- **Provider:** none; the email lookup is Cognito behind `People`.
- **Limits:** staff appear in the log and the console as the first 8
  characters of their id. Leads are the `admin-lead` group, filled by hand
  (1.3).

---

## 14. Privacy (export, deletion)

### 14.1 Data export (GDPR Art. 15/20)

A member downloads one JSON file with everything held about them.

- **Where:** `GET /api/me/export` (`catalog/routes.py:397`) gathers the
  catalog's part (`repository.py:242`: profile, listings, saved, reviews
  written and about them, photo names, reports filed, moderation decisions)
  and each service's `/internal/people/{id}/export`: booking
  (`booking/routes.py:596`: bookings, messages, evidence with notes, blocks,
  verified and suspended flags, card fingerprints, and since `7444e37` the
  disputes they opened and the claims they made; since `1cb2d67`, V7-16,
  also `claimsAboutMe`, owners' claims against them as a renter, and
  `renterRatingsAboutMe`, how owners rated them once the reviews are
  published, never a blind rating before), payments
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
- **Since `747ed6b`:** hand-over photos come as booking links signed for a
  day (`EXPORT_LINK_TTL`, `booking/routes.py:597-625`) instead of
  `evidence:<name>` references; payments adds the ID-check `consentAt` and
  `consentVersion`; catalog's moderation decisions include those about the
  person's messages and reviews (`person_id`, `repository.py:278`). ~~Decisions
  recorded before `747ed6b` on messages and reviews stay unattributed~~:
  **fixed in `42c777c`** by migration 0018 (reviews) and the hourly
  `attribute_decisions_once` (messages), 13.2.
- **Web** (since `2257182`, V4-5): on a desktop browser the export
  downloads as `cappy-my-data.json`; only a touch-first device
  (`pointer: coarse`) hands it to the share sheet.
- **Limits:** 5 a day per person (`rate_hits`, P-12). ~~Hand-over photos as
  references; consent and message or review decisions missing~~: fixed in
  `747ed6b`. No CCPA or Law 25 request workflow (P-29).

### 14.2 Account deletion

A member deletes their account in the app or at `/account/delete` (Google
Play). It is refused while bookings are open or a payout is pending, with the
reason and a date.

- **Where:** `DELETE /api/me` (`catalog/routes.py:347`). It checks booking
  `/internal/people/{id}/open` (`booking/routes.py:556`) and payments
  `/internal/people/{id}/open` (`payments/routes.py:351`), then
  `repository.forget` (`catalog/repository.py:189`: listings down with their
  words, spec free text blanked and exact point and postal code dropped
  (`privacy.LISTING_SPEC`, `42c777c`) and photos cleared, every upload handed to the photo sweep, reports
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
- **Limits:** ~~CloudFront keeps the person's listing photos until they
  expire~~: the photo sweep purges them from the CDN since `747ed6b` (3.4).
  ~~The `delete_me` docstring is out of date~~: rewritten in `747ed6b`.

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
  `web/dist` (`gateway/main.py:268`). Since `faebae7` a deploy keeps the
  previous release's hashed files for 30 days, so a tab opened before a
  release still loads its lazy chunks (R2-9; reloading once on
  `vite:preloadError` is still open), and a release is only a commit whose
  CI passed on `main`; a rollback is a deploy run naming the previous sha
  (INFRA §5).
- **Release build guard** (since `faebae7`, R2-1, `releaseProblems` in
  `web/vite.config.ts`): with `VITE_RELEASE=1` (the deploy sets it) the
  build refuses to run without `VITE_LEGAL_COMPANY`, `VITE_LEGAL_ADDRESS`
  and `VITE_LEGAL_EMAIL` (what the Impressum, privacy policy and DSA contact
  point show), with an email that is not an address, or with a malformed
  `VITE_ANDROID_SHA256` or `VITE_APPLE_TEAM_ID`. CD fills them from the
  `LEGAL` and `APPS` environment variables through Terraform's
  `web_config`. Local and CI builds leave `VITE_RELEASE` unset.
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
  literal `t('…')` and `plural(…)` in the source has an entry; since
  `090c890` it also enforces French typography in the catalogue (U+00A0
  before `:`, U+202F before `; ? !`; URLs, `{placeholders}` and clock times
  left out), and since `73610c4` (V7-9) over the French prose of the legal
  pages in `Legal.tsx` too, which were fixed to narrow spaces. Since
  `73610c4` the German catalogue names people neutrally ("die vermietende
  Person", "die mietende Person", the emails' words too since D-25; "Neu auf
  Cappy") instead of "der Anbieter"
  and "der Mieter" (V7-25); since `0a74b1c` (V8-8) none is left anywhere
  ("Anbieter" on result cards, Earn, the console, the renter-rating notes),
  and `check:i18n` refuses "Anbieter" and "Mieter" in the German catalogue
  and in the German prose of `Help.tsx` and `Legal.tsx`. Dev builds
  stretch every string with `?pseudo=1` (U-28). Emails, pushes and the bell
  have French since `235eeaa`; since `2257182` so do the legal pages
  (privacy, terms, withdrawal with the EU model form, ranking, reporting,
  accessibility; the Impressum page is titled "Mentions légales"), the help
  articles (`Help.tsx`) and the account deletion page (M-17 for FR). Since
  `2257182` the full `locale()` goes to the server (`Accept-Language` on
  every call and upload, the Cognito `locale` at sign-in, sign-up and on a
  language switch), and times use the locale's own clock (`clock`,
  `clockTime` in `format.ts`: "5:00 PM" without a leading zero for en-US,
  V4-19). The English privacy policy lists messages, hand-over photos,
  reports, ID checks and push like the German since `2257182`.
- **Look and feel** (since `1daf0da`, from `docs/research/2026-09-ui-ux-review.md`):
  - **Tokens** (UX-4/5): a nine-step type scale as Tailwind utilities
    (`text-caption` … `text-display`), radii `xs`/`s`/`m`/`l`, motion
    durations (`--dur-instant` 100 ms to `--dur-xlong` 500 ms) and easings,
    and colour roles (focus is a blue ink, errors a red apart from the action
    crimson, badges and money their own) in `web/src/app/theme.css`.
    `npm run check:tokens` (`web/scripts/check-tokens.ts`, in CI) fails on a
    literal text size, radius, hex or rgb colour, named Tailwind colour or
    inline font size outside the tokens; the few left are counted in
    `scripts/tokens-allowlist.json`, and the count may only go down.
    `npm run check:contrast` (since `0a74b1c`, `scripts/check-contrast.ts`,
    in CI) measures every text colour on the backgrounds it is used on, in
    both themes, against WCAG 2.2 AA (4.5:1 text, 3:1 large text and UI).
  - **Dark mode** (UX-36): **Appearance** in Profile (System, Light, Dark;
    per device, `cappy.theme.v1` in `localStorage`, `theme.ts`); the colour
    roles swap under `data-theme="dark"`; `public/theme-init.js` sets it
    before the first paint (a same-origin script the CSP allows), and the
    `theme-color` meta follows. Other tabs follow a change.
  - **Type**: Bodoni Moda only for words at 28 px and up; prices, times,
    ratings and user-written titles in Archivo with tabular figures.
  - **Motion** (UX-8): entries decelerate, exits accelerate at 2/3 of the
    entry time; press states; skeletons after 300 ms, and detail pages load
    as layout-shaped skeletons; since `0a74b1c` on a phone a drill-down
    slides in (push) and back out (pop) and moving between dock tabs is a
    crossfade (view transitions, `nav.ts`); reduced motion keeps short fades.
  - **Sheets** (UX-9, `Sheet` in `ui.tsx`): on a phone a sheet drags between
    a large and a medium height and closes when dragged down (30 % or a
    flick); its grabber is a button that changes the height; from 768 px it
    is a centred dialog. The phone dock steps aside on listing, booking,
    add/edit listing and staff detail screens (UX-13).
  - **Gallery** (UX-1/2, `Gallery.tsx`): a swipe strip with "n / N" on a
    phone, a mosaic with **Show all {n} photos** on a wide screen, and a
    full-screen viewer (arrows, keys, swipe, pinch).
  - **Welcome** (UX-30): example rentals with prices under the promise
    (examples, not live listings), and the primary button in ivory on the
    green plate.
  - **Card form** (UX-24, `PayStep.tsx`): Stripe's Payment Element takes
    Cappy's tokens in light and dark (the Appearance API, read from the
    page) inside an enclosed panel headed "Card details go to Stripe, never
    to Cappy"; since `0a74b1c` it offers Apple Pay and Google Pay where the
    device and domain allow (`wallets: auto`). Apple Pay needs the domain
    registered in Stripe first; the separate Express Checkout Element is not
    used.
  - **Desktop buy box** (UX-20, since `0a74b1c`): from 768 px the listing's
    booking box has **Day**, **Starts** and **Duration** selects on the same
    state as the chips.
  - **When** in search (UX-15): the filter sheet's **When?** (**Any time**,
    then each day of the search window, at most 14) and, with a day,
    **From** (**Any hour**, or 08:00 to 20:00 in two-hour steps), kept in the URL as `on=YYYY-MM-DD` and `at=H`; results
    are priced for that day and, since the matcher honours `earliest`
    (`933ed14`), start no earlier than the hour.
- **Large text** (since `9107ad2`, V6-7): the dock watches a 1rem probe, so
  a text-size change after load (Dynamic Type, a text zoom) switches it to
  icons only, and the listing's host card wraps its rating column, so 200 %
  text in French at 390 px no longer scrolls sideways. Enter in the Explore
  search puts the keyboard away on touch screens only; with a mouse and
  keyboard the field keeps focus (V6-20). Since `73610c4` (V7-8, V7-27)
  Profile's notification settings are rows that wrap (each with **Push** and
  **Email** checkboxes), not a fixed table, so 200 % text in French fits a
  390 px phone; the language switch and the listing's category chip wrap
  instead of cutting. Since `0a74b1c` long one-word headings hyphenate and
  wrap at 200 % (V8-6), and the listing's category label wraps (V8-14).
- **Small words** (since `73610c4`): a countdown in its last minute reads
  "in under a minute", never "in 0 min" (`relative`, `format.ts`, V7-21); a
  radius under 16 km in miles keeps one decimal ("0.6 mi", V7-17); Browse's
  empty window search says "in the next 24 hours" for one day, "in the next
  {n} days" otherwise; the listing plate's "free from" time is in the
  reader's own clock (5:30 PM in Toronto) and on the half hour a start
  really exists at, after a lead time of 5 minutes on the dev server and
  120 in builds (`VITE_MIN_LEAD_MINUTES`, `Cover.tsx`, V7-20). A business
  owner goes by their whole name on the listing page (V7-26), and staff
  previewing a listing read it as its owner does ("apply to bookings with
  it", free and sold hours, "the renter gets everything back").
- **Limits:** no Web Vitals (S-23). `npm run check:a11y` is a static check
  (image alt text, 24 px targets) and not a browser axe run (U-30 partly).
  Since `44a5520` CI runs `tsc --noEmit`, the build and every `check:*`
  script (`size`, `i18n`, `flags`, `attempt`, `a11y`, `money` since
  `73610c4`, `contrast` since `0a74b1c`, `tokens` since `7051660`),
  installing with `--ignore-scripts` (`.github/workflows/ci.yml:58-72`).
  axe-core is not installed (UX-35), nor the Capacitor status-bar,
  splash-screen and keyboard plugins (UX-37); both need a network install.

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
  (`appLinks`, `web/vite.config.ts:26-64`); since `faebae7` each file only
  when its value is set (no placeholder files), from the `APPS` environment
  variable in CD. The `appUrlOpen` listener is at `native.ts:67`.
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
  (`.github/workflows/deploy.yml:109`). How to use them is in `docs/runbook.md`.
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
  (`infra/platform/analytics/scrub.py`, P-6, `f303350`). Since `747ed6b` a
  status change made by support (`by: "support:<who>"`) arrives as `by:
  "staff"`, so no staff name or id reaches the lake (`scrub.py:35`). Since
  `b5cdd93` a `staff.action` keeps only `action`, `targetType` and `at`
  (`STAFF_ACTION_FIELDS`): who acted, about whom, and the note stay in the
  audit log. There is no client SDK.
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
  `docs/slo.md`. Since `7444e37` (T-35c) each access line of a request in an
  SLO journey names it (`journey`: `browse`, `book`, `answer`,
  `observability.py`), which the per-journey burn alarms count. Since
  `faebae7` (R2-6) alarms have two severities: a page (`…-alarms` topic:
  5xx rate, dead letters, the canary, the fast burns, root-account use,
  high GuardDuty findings) goes to the alarm mailbox and to the pager set in
  `pager_endpoint`; everything else is a ticket (`…-tickets` topic, mail).
  Severity, on-call and the incident and postmortem templates are in
  `docs/runbook.md` and `docs/incidents/`.
- **Seam:** yes, OTLP. The pager is any service that takes an SNS HTTPS
  subscription (PagerDuty, Opsgenie, AWS Incident Manager): set its URL as
  the `PAGER_ENDPOINT` secret. Swap to Datadog, Honeycomb or Grafana by pointing
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
| Places and geocoding (none exists) | `districts` table, `catalog/repository.py:339`; listing points are whatever the owner sends (`61b15b8`), which the web sets to the district's centre (`AddListing.tsx`, `2257182`) | A `Geocoder` interface when addresses become structured, filling `location`, `country`, `postalCode` (M-7, M-8, F-6) |
| Tax on the fee (fixed rate) | `payments/invoices.py:93` (`Issuer.tax_rate_bps`) | A `tax_for(owner, market, fee)` function per invoice line (M-12) |
| Stripe webhook event handling | `payments/routes.py:419-460` | Have `Provider.parse_webhook` return neutral events (`authorised`, `account_changed`, `chargeback`) instead of Stripe's event dict, as `IdentityProvider.parse_webhook` already does for ID checks |
| ~~Identity verification UI (Stripe.js modal)~~ | Fixed in `2257182`: `verify` in `Listing.tsx` opens a hosted `url` or the Stripe.js modal by `identityProvider` (section 9) | Done |
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
