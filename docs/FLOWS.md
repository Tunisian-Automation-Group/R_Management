# Cappy flows

How the app works from the user's side today, with the system steps under
each flow. The same React app runs on the web (a PWA) and inside the
Capacitor shells for the App Store and Google Play (ADR 0012). Where the two
behave differently, the flow says so.

This file describes the **committed code**. It was written against commit
`ac716b5` on `prod-readiness` and last synced with `c454c92` (the code as of
`7ef9b2c`: `44a5520` and `235eeaa` since the previous sync). Numbers come from the code, and each has its
source file next to it. If the code and this file disagree, the code wins, and
this file needs fixing (see the last section).

Conventions:

- API paths are relative to `/api`, which the gateway routes by an allow-list
  (`backend/services/gateway/gateway/routing.py`). Every service checks the
  Cognito access token itself.
- **Event** means an outbox row that is relayed over SNS/SQS (ADR 0003).
  Almost every booking change is one event, `booking.status_changed`, with
  `from`, `to` and `by`.
- **Email** is SES and **push** is SNS Mobile Push (APNs/FCM), both sent by
  the notifications service. The **bell** is the in-app notification centre
  (`/notifications`). What goes where is decided in
  `notifications/handlers.py` and `notifications/prefs.py`, and is covered in
  [Notifications and their settings](#19-notifications-and-their-settings).
- "Renter" and "buyer" both mean the requester. "Owner" means the host.

## Contents

0. [The numbers](#0-the-numbers)
1. [First run and welcome](#1-first-run-and-welcome)
2. [Sign-up and confirmation code](#2-sign-up-and-confirmation-code)
3. [Sign-in, session refresh and sign-out](#3-sign-in-session-refresh-and-sign-out)
4. [Onboarding: profile, 18+, business identity, rent / earn / both](#4-onboarding-profile-18-business-identity-rent--earn--both)
5. [Browse and search](#5-browse-and-search)
6. [The listing page](#6-the-listing-page)
7. [Book: request and instant book](#7-book-request-and-instant-book)
8. [Payment](#8-payment)
9. [The owner accepting or declining](#9-the-owner-accepting-or-declining)
10. [Hand-over, start and complete](#10-hand-over-start-and-complete)
11. [No-show](#11-no-show)
12. [Cancel, withdraw and refund](#12-cancel-withdraw-and-refund)
13. [Dispute and staff resolution](#13-dispute-and-staff-resolution)
14. [Reviews, both sides, blind](#14-reviews-both-sides-blind)
15. [Messaging and masking](#15-messaging-and-masking)
16. [The ID check](#16-the-id-check)
17. [Becoming an owner and creating a listing](#17-becoming-an-owner-and-creating-a-listing)
18. [Payouts and invoices](#18-payouts-and-invoices)
19. [Notifications and their settings](#19-notifications-and-their-settings)
20. [Reporting and moderation (DSA)](#20-reporting-and-moderation-dsa)
21. [Data export and account deletion](#21-data-export-and-account-deletion)
22. [The store apps](#22-the-store-apps)
23. [Known gaps between code, UI and docs](#23-known-gaps-between-code-ui-and-docs)
24. [How to keep this file true](#24-how-to-keep-this-file-true)

The booking lifecycle diagram is in [section 7](#the-booking-lifecycle).

---

## 0. The numbers

| What | Value | Where |
|---|---|---|
| Soonest bookable start | now + 120 min | `matching/settings.py` `min_lead_minutes` |
| Time to pay before the window is released | 30 min | `booking/settings.py` `payment_timeout_minutes` |
| Time the owner has to answer | 24 h, and never past the window's start | `booking/settings.py` `answer_within_hours`, `booking/handlers.py` `answer_deadline` |
| Hand-over can be marked from | 30 min before the start | `booking/settings.py` `start_early_minutes` |
| No-show: renter reports owner | from the start until start + 2 h | `booking/routes.py` `NO_SHOW_REPORTABLE` |
| No-show: owner reports renter | from start + 30 min until start + 2 h | `booking/routes.py` `NO_SHOW_GRACE` |
| Auto-complete (owner paid) | 48 h after the window ends, from `accepted` or `active` | `booking/settings.py` `auto_complete_after_hours` |
| Review window (both sides) | 14 days after the window ends | `booking/repository.py` `REVIEW_WINDOW` |
| Booking sweeps (expire, auto-complete, publish reviews) | every 30 s per replica, jittered | `booking/settings.py` `sweep_seconds` |
| Stripe reconciliation | intents still `created` after 10 min, checked about every 300 s | `payments/jobs.py` |
| Unpaid bookings one person may have at once | 3 | `booking/settings.py` `max_unpaid` |
| Booking requests per person per 24 h | 10 | `booking/settings.py` `max_requests_per_day` |
| ID check needed | booking total above 30 000 minor units of the listing's currency (EUR 300 for a euro listing); no categories | `booking/settings.py` `verify_above_cents`, `verify_categories` |
| Paid cancellation policies | **off**: every cancellation refunds in full, unless the feature flag `paidCancellationPolicies` is at 100 | `booking/settings.py` `paid_cancellation_policies`, `FEATURE_FLAGS` |
| Platform fee | 15 %, inside the total | `matching/domain/pricing.py`, `web/src/domain/pricing.ts` |
| New listings per owner per 24 h | 20 | `catalog/settings.py` `max_listings_per_day` |
| Listing held for a staff check | owner with 0 completed jobs and a rate above 10 000 minor units an hour (EUR 100) | `catalog/settings.py` `review_above_cents` |
| Photos | 12 per listing, 12 MB each, 100 uploads per person per day; shrunk on the device to 2048 px | `catalog/routes.py`, `catalog/settings.py`, `web/src/app/photos.ts` |
| Hand-over photo links | valid 15 min; the app re-reads the list every 10 min | `booking/messages.py` `LINK_TTL`, `web/src/data/repo.ts` `useEvidence` |
| Owner reliability | cancels and no-shows over 12 months, shown after 5 accepted bookings; 3 in 30 days flags the owner to staff | `booking/repository.py` |
| Access and id token | 15 min; the app refreshes 60 s before expiry | `infra/platform/identity.tf`, `web/src/data/auth.ts` |
| A session ended elsewhere stops working | at once in catalog; in booking, payments and notifications when the event arrives (seconds), then within 30 s on every replica; matching at token expiry | `cappy_common/guard.py` `Revocations` |
| Staff MFA check | cached 5 min per staff account | `cappy_common/auth.py` `StaffMfa` |
| Refresh token | 30 days, revocable | `infra/platform/identity.tf` |
| Password | at least 12 characters, nothing else required | `infra/platform/identity.tf`, `Login.tsx` |
| Resend a code | every 30 s | `Login.tsx` |
| Reports | 3 per anonymous email per 24 h; per target per 24 h, 5 anonymous and 20 signed-in, counted apart | `catalog/moderation.py` |
| Messages | 30 per sender per booking in 10 min | `booking/messages.py` `MESSAGES_PER_WINDOW` |
| A conversation closes | when the booking is cancelled, declined, expired or `payment_failed`, or 14 days after a completed booking's window | `booking/messages.py` `open_for_messages` |
| Message emails | at most one per conversation per 15 min (every message is pushed) | `notifications/handlers.py` `MESSAGE_EMAIL_EVERY` |
| Reporter's details on a report | cleared 183 days after the decision | `catalog/jobs.py` `REPORTER_KEPT` |
| Stored answers to retried creates | 24 h | `cappy_common/idempotency.py` `KEEP` |
| Fee invoices kept | 10 years from the end of the year of issue, then deleted | `payments/settings.py` `invoice_retention_years`, `payments/jobs.py` |
| Data exports | 5 per person per 24 h | `catalog/routes.py` `export_me` |
| Sign out everywhere | 5 per person per hour | `catalog/routes.py` `sign_out_everywhere` |
| Push devices per person | 10 (newest kept) | `notifications/routes.py` `MAX_DEVICES` |
| Client polling | booking page 2.5 s while `awaiting_payment` or `requested`; booking lists 4 s while one is; messages 5 s; bell 60 s | `web/src/data/repo.ts` |
| App config (forced update) | cached 5 min at the CDN, 10 min in the app | `gateway/main.py`, `repo.ts` |

---

## 1. First run and welcome

**Who and where.** Anyone opening Cappy on a device for the first time, at
`/`. Web and app behave the same.

1. The app restores device flags (`web/src/app/device.ts`: localStorage on the
   web, Capacitor Preferences in the shells) and any stored refresh token.
   Until that is done it renders nothing, so a signed-in person never sees the
   welcome flash (`App.tsx` `Shell`).
2. Signed out, `Gate` decides. On a **first run** (no `welcomeSeen`, no
   `signedInBefore`, and the app was opened at `/`) it redirects to
   `/welcome`.
3. `/welcome` (`Welcome.tsx`) shows what Cappy is, three value points, a
   language switch (English, Deutsch, Français; the first language follows
   the device, else English), and two buttons: **Create an account**
   (`/login?mode=up`) and **I have an account** (`/login`). There are links to
   Impressum, privacy, terms and help. No listings, prices or people are shown
   (GOAL 13). Opening the page sets `welcomeSeen`.
4. After that, a signed-out device skips the welcome and goes to `/login`.
   Once anyone signs in, `signedInBefore` and `welcomeSeen` are both set
   (`auth.ts` `adopt`).

**Edge cases**

- *Deep link while signed out* (for example `/listing/l1` from a shared link
  or an App Link). Any path other than `/` skips the welcome. The person lands
  on `/login?next=/listing/l1` and returns there after signing in.
- *Public pages.* `/welcome`, `/login`, `/legal/*`, `/account/delete` and
  `/help`, `/help/*` render signed out. Every other path redirects.
- *Signed in and opening `/welcome`.* Redirects to `/`.
- *Storage blocked* (private mode). Flags are kept for this visit only, so the
  welcome can show again next time.

---

## 2. Sign-up and confirmation code

**Who and where.** A new person, on `/login?mode=up` (from the welcome or the
Sign in / Create account switch). Web and app are the same; the app talks to
Cognito directly over its JSON API (`web/src/data/auth.ts`).

1. The person enters an email and a password. The form checks the email's
   shape and that the password has at least 12 characters, the same rule as
   the user pool.
2. `SignUp` goes to Cognito with the `email` and `locale` (the app's current
   language) attributes. Cognito emails a six-digit code ("Your Cappy
   verification code is …", sent through SES).
3. The screen switches to **Check your email**. Typing or pasting six digits
   submits by itself. **Send a new code** is enabled after 30 s
   (`ResendConfirmationCode`).
4. `ConfirmSignUp`, then an immediate `InitiateAuth` (`USER_PASSWORD_AUTH`)
   with the password still in memory, and the person is signed in and sent to
   `next` (default `/`).
5. With no Cappy profile yet, the app shows onboarding
   ([section 4](#4-onboarding-profile-18-business-identity-rent--earn--both)).

**Edge cases**

- *Email already registered.* Cognito's `UsernameExistsException` is shown as
  "There is already an account with that email. Sign in instead."
- *Wrong or expired code.* "That code is not right…" or "That code has
  expired. Ask for a new one." (the code's lifetime is Cognito's default).
- *Too many attempts.* "Too many attempts. Wait a few minutes and try again."
- *App closed before confirming.* The password is gone from memory. The next
  sign-in gets `UserNotConfirmedException`, the app resends the code and goes
  back to the code step. Confirming then signs in with the password just
  typed.
- *Offline.* "Cannot reach the sign-in service. Check your connection."
- *Forgot password.* **Forgot your password?** sends `ForgotPassword` and then
  always goes on to the code step, whether or not the address has an account,
  so nobody can probe which emails are registered. `ConfirmForgotPassword`
  with the code and a new password of 12 or more characters signs the person
  in and shows "Password changed".
- *Demo buttons.* Local builds only: `local/bootstrap.py` writes
  `VITE_DEMO_ACCOUNTS` for the local stack, which is also the only place the
  demo accounts exist. No deploy sets it (ADR 0010).

---

## 3. Sign-in, session refresh and sign-out

**Who and where.** A member on `/login` (tab **Sign in**), then everywhere.

### Sign-in

1. Email and password go to `InitiateAuth` (`USER_PASSWORD_AUTH`).
2. On success the app keeps the access and id tokens **in memory only**. The
   refresh token is stored in localStorage on the web, or in Capacitor
   Preferences in the shells (mirrored in memory so reads stay synchronous).
3. `adopt` works out the session: `sub`, `email`, and `staff` if the access
   token has the `admin` group. That flag only changes what the UI shows;
   staff calls are checked by the server.
4. `updateLocale` writes the current language to Cognito's `locale`
   attribute, so emails and pushes arrive in that language.
5. The person goes to `next`.

A wrong password shows "That email and password do not match." The sign-in
screen has the language switch too.

**Two-step sign-in.** An account with an authenticator app (TOTP) gets
`SOFTWARE_TOKEN_MFA` from Cognito. The screen switches to **Two-step
sign-in** ("Enter the six-digit code your authenticator app shows for
Cappy"); six digits submit by themselves (`RespondToAuthChallenge`). A wrong
code says "Use the newest code your authenticator app shows"; a timed-out step
says "Sign in again". Any other challenge still shows "This account needs a
step this app does not support yet." Only staff can turn MFA on, from the
console ([section 13](#13-dispute-and-staff-resolution)); members have no
setting for it.

### Staying signed in

- **Cold start.** If a refresh token is stored, `REFRESH_TOKEN_AUTH` runs
  before the first screen renders.
- **Before every API call** (`repo.ts` `send`), `accessToken()` refreshes if
  the token has less than 60 s left. Concurrent refreshes share one request.
- **A 401 from the API** triggers one refresh and one retry. If the fresh
  token is refused too with `token_expired` (this session was ended by
  sign-out-everywhere or a deleted account), the app ends the session in
  every tab and shows sign-in (`repo.ts` `send`, `auth.ts` `endSession`).
- **The refresh fails for good** (revoked, expired after 30 days, the user
  deleted). The app forgets the session. `Member` gives way to `Gate`, which
  sends the person to `/login?next=<where they were>`. Drafts survive this
  (see below).
- **The refresh fails because the device is offline.** The refresh token is
  kept, and the person is not signed out. At a cold start offline the app
  opens as the last signed-in person (kept under `cappy.session.v1`) with the
  offline bar, and refreshes when the network comes back.

**Drafts that outlive an expired session.** Message drafts and the add or edit
listing form are saved under `cappy.draft.*` in localStorage (`device.ts`
`drafts`). They are cleared only by a deliberate sign-out.

### Other tabs (web only)

Tabs follow the account id under `cappy.who.v1`, never the refresh token
(`auth.ts` `announce`).

- *Another tab signs out.* This tab drops its tokens and shows the sign-in
  screen.
- *Another tab signs in as someone else.* This tab reloads, so no data from
  the old account stays on screen or in the cache.
- *This tab was signed out and another tab signs in.* This tab refreshes from
  the shared refresh token and follows.

The shells have a single web view, so none of this applies there.

### Sign-out (this device)

On the Profile screen, **Sign out** (also on the onboarding screen):

1. In a shell, `DELETE /notifications/devices/{token}`, so this device stops
   getting this person's pushes.
2. Drafts are cleared, the tokens are forgotten, and the query cache is
   cleared (from Profile).
3. Cognito `RevokeToken` revokes this device's refresh token. If that fails
   offline, the token is already gone from the device.
4. The person lands on `/`, which, now signed out, goes to `/login`.

### Sign out everywhere

On the Profile screen, **Sign out everywhere**, then confirm:

1. `POST /me/sign-out-everywhere` (catalog service; at most 5 an hour, else
   429 with the reason) records that every token issued until now is void,
   and publishes `person.signed_out`. Catalog refuses those tokens at once;
   booking, payments and notifications as soon as the event reaches them.
   Notifications then calls Cognito `AdminUserGlobalSignOut` and deletes
   **every** push device of the account. If the call fails, the device stays
   signed in and the person sees "Your other devices could not be signed
   out…", so they can try again.
2. Then the same steps as a normal sign-out, with Cognito `GlobalSignOut` in
   place of `RevokeToken`.
3. Other devices stop getting pushes within seconds. Their next API call gets
   401 `token_expired`, the refresh fails too, and they are signed out. Only
   matching (browse and search results) still accepts their access token
   until it expires, at most 15 min.

```mermaid
sequenceDiagram
  participant A as App
  participant C as Cognito
  participant API as Cappy API
  A->>C: InitiateAuth USER_PASSWORD_AUTH
  C-->>A: access + id (15 min), refresh (30 days)
  A->>API: request with Bearer access
  Note over A: under 60 s left
  A->>C: InitiateAuth REFRESH_TOKEN_AUTH
  C-->>A: new access + id
  API-->>A: 401 (revoked early, or token_expired)
  A->>C: refresh once, retry once
  C-->>A: NotAuthorized
  Note over A: forget session in every tab, go to /login?next=...
```

---

## 4. Onboarding: profile, 18+, business identity, rent / earn / both

**Who and where.** A signed-in person without a Cappy profile. `GET /me`
returns no `owner`, and `Member` then shows `Onboarding` **in place of every
route**. The URL stays as it was, so a deep link opens its screen once the
profile exists. Web and app are the same.

1. **Your name** (at least 2 characters; the server allows 2 to 80).
2. **You are**: a person or a business. A business must give its legal name
   (at least 2 characters) and address (at least 8), and may give a register
   number and a VAT ID (`BusinessFields.tsx`). The server normalises the VAT
   ID and checks it: `DE` plus 9 digits, or another EU country's pattern
   (`catalog/routes.py` `BusinessIn`). Renters see these details on the
   listing and at checkout, because EU consumer law requires it.
3. **Where are you?**: a district from `GET /districts`. Listings live there
   and searches start there.
4. **What brings you to Cappy?**: Renting, Earning or Both (default Both). It
   is kept on the device (`intent`) and only decides where the person lands:
   **Earning** goes to `/earn` once, and the rest stay where they are. Nothing
   is locked by it.
5. **I am 18 or older**, which is required. The client refuses without it,
   and so does the server: `upsert_profile` raises "Cappy is for people aged
   18 or over…" for a new profile without `adult`.
6. Accepting the terms and privacy policy is stated in words next to the
   button ("By continuing you accept the Terms…").
7. `PUT /me` creates the profile, and the catalog publishes `profile.created`.
   The app reloads `/me` and the product appears. The server also takes a
   `country` (ISO code, default `DE`), which sets the payout account's
   country ([section 18](#18-payouts-and-invoices)); the app does not send it
   yet.

Editing later (Profile, **Edit profile**) uses the same `PUT /me`. It changes
the name, kind, district and business details. The track record is never
touched by an edit.

**Edge cases**

- *Double submit.* `PUT /me` is idempotent (one profile per `sub`).
- *Unknown district.* 422 "unknown district".
- *Sign out* is offered on this screen, for someone who signed in to the wrong
  account.
- *Signing up again after deleting the account* with the same sign-in. The
  person sees onboarding again, must confirm 18+ again, and gets a fresh
  profile: no ratings, jobs, badge or business details come back. A
  suspension does stay.

---

## 5. Browse and search

**Who and where.** Members only, on `/` (the **Explore** tab). The server
agrees: the catalog router depends on `require_principal`. Web and app are
the same. The phone layout has a bottom dock; the desktop has a header.

1. The search starts at the person's home district (`/me.homeDistrict`) until
   they pick another district or city (`CapacityMap`, `DistrictSelect`).
2. **Free in the next 24 hours**:
   `GET /browse/spotlight?district&maxKm&withinHours=24&limit=60` (matching).
   It shows a rail of covers and the same set on the map.
3. **Free text**: `GET /search?q&metro&limit=30` (catalog, trigram index). It
   needs at least 3 characters ("Type at least 3 letters to search.").
4. **What do you need?**: groups and categories. Choosing a category builds a
   *requirement*: hours or a batch quantity, district, radius and the next N
   days. `POST /matches {requirement, sort, limit: 50}` returns bookable
   slots, sorted by best match, cheapest, soonest or nearest. The sort is kept
   in the URL (`?sort=`). The filters sheet changes hours or quantity and the
   radius. The results can be shown as a list or on a map.
5. Matching never offers a start sooner than **now + 120 min**, never the
   person's own listings, and, when deployed, only owners Stripe can pay
   (`REQUIRE_PAYABLE_OWNERS` must be true outside local, per
   `catalog/settings.py`).
6. Tapping a result opens `/listing/{id}`, carrying the chosen slot and start
   in the query string.

**Edge cases**

- *Nothing fits.* "No idle capacity fits that", with **Widen to 90 km** (or
  "56 mi" in a miles locale) and **Allow 3 weeks**.
- *Distances* read in km (and m under 1 km), or in miles where the formatting
  locale's region is the US or the UK; under 300 m it says "Nearby"
  (`format.ts` `formatDistance`, `formatRadius`). An English reader whose
  device has no English region of its own is formatted as `en-IE`, so reads
  km (since `44a5520`).
- *Service down.* "Cappy is not reachable right now", with a retry button.
- *Overload.* The gateway sheds reads first: browsing gets 80 % of in-flight
  capacity and writes keep the rest (`gateway/main.py` `Admission`). A shed
  request gets a 503 with `Retry-After`, and the client never retries sooner
  than that.
- *Offline.* What is cached stays on screen, with the offline bar ([section
  22](#22-the-store-apps)).

---

## 6. The listing page

**Who and where.** Members, on `/listing/{id}`. Web and app are the same. On
the phone, the price and button sit in a bottom bar; on the desktop, in a side
panel.

What the page shows, and the calls behind it:

- The listing, its owner, district, upcoming windows and review summary:
  `GET /listings/{id}`. Reviews: `GET /listings/{id}/reviews?limit=100`.
- **How long / how many**: duration chips between the listing's minimum and
  maximum hours, or batch quantities.
- **Pick a start**: `POST /quote` prices it and says how many hours it takes,
  then `GET /listings/{id}/offers?hours` lists the starts that fit around what
  is already booked. The day comes first, then the time. The page
  pre-selects the slot from the results, else the soonest.
- **Price**: the base, extras, any discount and the total, under which the
  bar says "Total, incl. {fee} service fee". The 15 % fee is inside the total,
  and the owner's share is shown. Amounts are formatted for the reader's
  locale in the listing's currency, which the API sends on listings, quotes
  and bookings since `235eeaa` (`domain/money.ts` `formatMoney`). Nothing is
  converted.
- **The host**: name, verified shield, track record, cancellation rate (if
  there is one), response time, and whether they are a business or a private
  person (consumer rights differ). A business shows its legal identity
  (`TraderNote`).
- **Cancellation policy**: while paid policies are off, every listing shows
  as flexible (`format.ts` `policyInForce` with the flag
  `paidCancellationPolicies`, read with `useGlobalFlag`: only 100 % counts,
  as on the server, since `44a5520`).
- House rules, **Report** (listing and owner), **Block** (owner), and the
  **heart**, which saves the listing (`PUT` or `DELETE /saved/{id}`, retried
  on a blip, shown at once).

**Edge cases**

- *Your own listing.* A banner, "This is your listing", and no book button.
- *Paused, removed, taken down or held listing.* `GET /listings/{id}` returns
  404 and the page shows "not found". The owner can still open their own
  held or paused listing (since `235eeaa`).
- *Nothing free that long.* An empty state with **Try {min hours}** or a
  smaller batch.
- *Offline.* The **Request** / **Book** button is disabled.

---

## 7. Book: request and instant book

**Who and where.** A member on a listing page. **Request** (or **Book** with
a lightning icon for instant book) opens a confirm sheet. Web and app are the
same.

1. **The confirm sheet** shows when, how long, where, "You pay", "{owner}
   receives", the cancellation policy and the trader's identity. For a
   request it says "Nothing is charged yet: your card is held… {owner} has to
   accept first." For instant book it says "Confirmed as soon as your card is
   held." The final button always reads **Book and pay** (§ 312j BGB).
2. `POST /bookings {requirement, listingId, slotId, start, end}` with an
   `Idempotency-Key` per attempt (`Listing.tsx` `attempt`,
   `domain/attempt.ts`): a retry of the same request after a 5xx, a timeout
   or a lost connection sends the same key; a success, a 4xx or another slot
   makes a new one.
3. **Booking** (`booking/routes.py` `create_booking`):
   - refuses if bookings are paused (kill switch `ACCEPTING_BOOKINGS`, 503);
   - replays the first booking if the same key comes again (and refuses the
     key if it was used for a different body);
   - refuses more than 3 unpaid bookings, or more than 10 requests in 24 h
     (429);
   - asks matching to price the window and confirm it is free. The price is
     never taken from the client;
   - refuses your own listing, anyone blocked either way ("this listing is not
     available to you"), and a suspended account;
   - asks for the ID check if the total is above 30 000 minor units (EUR 300)
     ([section 16](#16-the-id-check));
   - inserts the booking as `awaiting_payment` in the listing's currency,
     holding the window.
     `expires_at` is now + 30 min. An advisory lock per listing and a Postgres
     exclusion constraint (ADR 0004) make a second overlapping booking fail
     with 409 "that window was just taken; pick another";
   - publishes `booking.status_changed` (`null` to `awaiting_payment`);
   - asks payments for the PaymentIntent ([section 8](#8-payment)).
4. **The app.** With Stripe it shows the card form in the same sheet. With the
   fake provider (local), the card is "authorised" the moment the intent
   exists, and the app goes straight on.
5. **After the card is held**, `payment.authorised` reaches booking:
   - **request**: `awaiting_payment` to `requested`, with `expires_at` =
     min(now + 24 h, window start);
   - **instant book** (the listing's `instantBook`, snapshotted on the
     booking): `awaiting_payment` to `accepted`. Payments then captures at
     once ([section 9](#9-the-owner-accepting-or-declining)).
6. The app shows "Request sent to {owner}" or "Booked", offers push the first
   time ([section 22](#22-the-store-apps)), and opens `/bookings/{id}`. The
   page polls every 2.5 s while the booking is `awaiting_payment` or
   `requested`.
7. **What the other side sees.**
   - Request: the owner gets "New request: {title}. Answer by {deadline}…"
     (email, push, bell), a badge on **Earn** and the request card in the
     Earn inbox.
   - Instant book: the renter gets "Confirmed" and the owner gets "New
     booking: {title} was booked instantly" (email, push, bell). Both emails
     are sent whatever the settings.

The owner does not see the booking at all until the card is held: the
server leaves `awaiting_payment` bookings, and payments that failed before
the owner saw them, out of **I'm hosting** and answers 404 for them
(since `235eeaa`). The app's "Authorising payment" label for owners is no
longer reached.

**Edge cases**

- *Double tap or flaky network.* The same `Idempotency-Key` returns the same
  booking and the same PaymentIntent. The button is disabled while sending.
- *The window was just taken.* 409. The app shows the message, reloads the
  starts and makes a new key.
- *Payments refuses for good* (4xx, for example "this owner has not finished
  setting up payments yet"). The booking moves to `payment_failed`, the
  window is free, and the message is shown. The booking stays in the
  renter's list as "Payment failed", and the renter gets "Payment failed:
  {title}… Nothing was taken." (email, always).
- *Payments down or slow* (5xx or timeout). The booking **stays**
  `awaiting_payment` and the app says "we could not start the payment, and
  you have not been charged; try again". A retry sends the same key, so it
  gets the booking already made and a new try at its PaymentIntent (fixed in
  `f42a4ef`). The expiry sweep releases the window after 30 min if nobody
  pays.
- *Closing the sheet half way.* The booking stays `awaiting_payment` and can
  be paid from its own page. **Bookings** shows it under "Next up: Finish
  paying so the owner is asked".
- *Suspended account.* 403 "your account is suspended; see the email we sent
  you".
- *Listing taken down or removed before the owner answers.* Booking gets
  `listing.changed` (`removed`) and moves `awaiting_payment` and `requested`
  bookings to `declined`, with the reason "The listing was removed by its
  owner", or "The listing was taken down by Cappy" when staff took it down
  (since `235eeaa`). Payments releases the hold, and the renter gets
  "Declined… Nothing was charged". The app shows the reason in English in
  every language ([gaps](#23-known-gaps-between-code-ui-and-docs)).
  Accepted bookings stand: the owner still owes them, and the hand-over
  address is still served for a removed listing.
- *Owner suspended.* Their live listings are taken down, which declines
  pending requests as above. When the *renter* is suspended, their own
  pending requests are declined with the reason "The account was suspended".
- *Card seen on a suspended account.* The booking goes ahead, and staff get a
  `linked_to_suspended` notice in the report queue (S-17).
- *Offline.* Every booking button is disabled.

### The booking lifecycle

```mermaid
stateDiagram-v2
  [*] --> awaiting_payment: POST /bookings
  awaiting_payment --> requested: card held (request)
  awaiting_payment --> accepted: card held (instant book)
  awaiting_payment --> payment_failed: payments refuses (4xx)
  awaiting_payment --> expired: unpaid after 30 min
  awaiting_payment --> cancelled: cancel (either side)
  awaiting_payment --> declined: listing removed or renter suspended
  requested --> accepted: owner accepts (card captured)
  requested --> declined: owner declines, listing removed or renter suspended
  requested --> expired: no answer by min(24 h, start)
  requested --> cancelled: cancel before start (either side)
  accepted --> active: hand-over marked (either side, from start - 30 min)
  accepted --> cancelled: cancel before start, or no-show (start to start + 2 h)
  accepted --> payment_failed: capture declined
  accepted --> disputed: renter reports a problem (after start)
  accepted --> completed: nobody acted, end + 48 h
  active --> completed: renter confirms, or end + 48 h
  active --> disputed: renter reports a problem
  disputed --> completed: staff pay the owner
  disputed --> cancelled: staff refund the renter
  completed --> [*]
  cancelled --> [*]
  declined --> [*]
  expired --> [*]
  payment_failed --> [*]
```

- A booking **holds** its window in `awaiting_payment`, `requested`,
  `accepted`, `active`, `completed` and `disputed`. Only bookings that never
  happened release it (`state.py` `HOLDING`).
- **Open** bookings, which block account deletion, are `awaiting_payment`,
  `requested`, `accepted`, `active` and `disputed` (`state.py` `OPEN`).
- Every change is one `booking.status_changed` event and one audit row
  (`TransitionRow`). Payments and notifications act on the event.

---

## 8. Payment

**Who and where.** The renter, inside the confirm sheet or on
`/bookings/{id}` while the booking is `awaiting_payment`. Stripe's Payment
Element runs in the web view in the shells too; no in-app purchase is needed
for real-world rentals (ADR 0012).

```mermaid
sequenceDiagram
  participant R as Renter app
  participant B as booking
  participant M as matching
  participant P as payments
  participant S as Stripe
  participant N as notifications
  R->>B: POST /bookings (Idempotency-Key)
  B->>M: price and check the window
  B->>B: insert awaiting_payment, window held
  B->>P: POST /internal/intents
  P->>S: PaymentIntent, capture_method=manual, key intent-{booking}
  B-->>R: 201 booking + clientSecret
  R->>S: confirmPayment (card, SCA/3DS)
  S-->>P: webhook amount_capturable_updated
  P->>B: payment.authorised (card fingerprint)
  B->>B: requested (or accepted if instant)
  B->>N: booking.status_changed
  N-->>R: bell (and email/push to the owner)
```

1. `GET /payments/config` tells the app whether the provider is `stripe` or
   `fake`, plus the publishable key. Stripe.js loads only when someone reaches
   the card step (`@stripe/stripe-js/pure`, no third-party script before
   then).
2. Payments creates the PaymentIntent with `capture_method: manual`,
   `automatic_payment_methods`, `transfer_group` = the booking and
   idempotency key `intent-{bookingId}`, so a retried booking gets the same
   intent. No database connection is held while Stripe answers.
3. The renter enters the card, under "Cappy holds your payment and pays the
   owner only once the booking has happened…". `confirmPayment` runs with
   `redirect: 'if_required'`. A bank check (SCA/3DS) appears inside Stripe's
   element. Only methods that leave the page come back, to
   `/pay/return?booking={id}` on Cappy's own domain, which forwards to
   `/bookings/{id}` and says "The payment did not go through" if Stripe's
   `redirect_status` is `failed`. In the store apps `/pay/*` is an app link,
   so the bank hands back to the app. The card form (and Stripe.js) is a
   separate chunk, fetched only here.
4. The card is **authorised, not charged**. Stripe sends
   `payment_intent.amount_capturable_updated`. The webhook is
   signature-checked and handled once per Stripe event id. Payments marks the
   payment `authorised`, reads the card fingerprint (a fraud signal only) and
   publishes `payment.authorised`.
5. Booking moves the booking on ([section 7](#7-book-request-and-instant-book),
   step 5).
6. **Capture** happens when the booking becomes `accepted` (the owner accepts,
   or instant book). **Release** happens on `declined`, `cancelled`, `expired`
   or `payment_failed` while not captured. **Refund** happens on `cancelled`
   after capture. **Transfer** to the owner happens on `completed`
   (`payments/handlers.py`).

**Edge cases**

- *Card declined at entry.* Stripe's element shows the reason under "Payment
  not authorised". The booking stays `awaiting_payment` and the renter can
  try another card in the same form or later from the booking page
  (`GET /bookings/{id}/payment` returns the same intent). After 30 min the
  booking expires, payments cancels the intent, and nobody is emailed (an
  expiry from `awaiting_payment` notifies no one).
- *3DS abandoned.* The same as a decline: nothing is authorised, and the
  booking lapses after 30 min.
- *The webhook never arrives.* The reconciliation loop looks up intents still
  `created` after 10 min (about every 300 s). If Stripe says
  `requires_capture`, it publishes `payment.authorised`; if `canceled`, it
  marks the payment cancelled.
- *Card-hold expiry.* Not a live risk today. The longest a hold waits for
  capture is 30 min to pay plus at most 24 h for the owner, because capture
  happens at accept, not at the start. Stripe's authorisation window is
  longer than that.
- *Capture declined after accept* (a reversed hold, a closed account).
  Payments publishes `payment.failed` (`stage: capture`). Booking moves
  `accepted` to `payment_failed` and the window is free. Nothing was taken.
  Both sides get "Payment failed: {title}… the booking is off" (email,
  always, since `235eeaa`).
- *Chargeback* (`charge.dispute.created`). Payments stamps `chargeback_at`
  and logs an error line that the chargeback alarm pages on. A later
  `completed` does **not** pay the owner out; the money waits for a person.
- *Payment result for a booking that already moved on* (cancelled while the
  card was being entered). `system_status` ignores it, and payments voids the
  authorisation when it sees the cancel.
- *Just paid, and the page still shows `awaiting_payment`.* The booking page
  says "Confirming your payment…", hides the card form, and re-reads the
  booking every 2 s for up to a minute until the webhook lands.

---

## 9. The owner accepting or declining

**Who and where.** The owner. The request card is in the **Earn** inbox, and
the booking page is `/bookings/{id}` (from the email, push, bell or the
**I'm hosting** list). Web and app are the same.

The owner sees the renter's name and renter record ("renter rating"), what
they want and for how long, their own share, the window, when the request was
made, and "Answer {when}, or the request lapses".

### Accept

1. `POST /bookings/{id}/accept`. Only the owner can, only from `requested`,
   and only before `expires_at`.
2. The booking becomes `accepted`, `expires_at` is cleared, and
   `booking.status_changed` goes out. The owner's reliability figures are
   recomputed (`owner.reliability` event).
3. Payments **captures** the card and publishes `payment.captured`.
4. The renter gets "Confirmed: {title}" (email, whatever the settings, plus
   push and bell).
5. Both sides now see **Getting in**: the hand-over address and instructions,
   fetched from the catalog (`SHOWS_HANDOVER` = `accepted`, `active`,
   `completed`, `disputed`). Contact details in messages are unmasked.

### Decline

1. The owner picks a reason from four chips ("Already promised it to
   someone", "Turns out I need it then", "It needs a repair first", "Too short
   notice for me"). The server needs a non-empty reason of up to 500
   characters.
2. `POST /bookings/{id}/decline {reason}`. The booking becomes `declined`.
3. Payments releases the hold.
4. The renter gets "Declined: {title}. Nothing was charged." (email, always)
   and sees the reason on the booking.
5. The Earn sheet says whether the hours go back on the market (the listing
   is live) or not (the listing is paused or removed).

### The owner does not answer

At `expires_at`, which is min(request time + 24 h, window start), the sweep
moves the booking to `expired`. Payments releases the hold, and the renter
gets "Expired: {title}… Nothing was charged." (email, always). The owner gets
nothing. A late tap on Accept gets 409 "this request has lapsed", even before
the sweep has run.

**Edge cases**

- *Double tap on Accept.* The second call gets 409 ("cannot accept a booking
  that is accepted"). Buttons are disabled while busy.
- *Capture declined.* See [section 8](#8-payment).
- *Listing paused while a request waits.* Pausing does not touch pending
  requests; the owner can still accept.
- *Offline.* Accept and Decline are disabled.

---

## 10. Hand-over, start and complete

**Who and where.** Both sides, on `/bookings/{id}` of an `accepted` booking.

### Start (the hand-over)

1. From **30 min before the start** (`canStartFrom`, sent by the server),
   either side can press **I have handed it over** (owner) or **I have
   collected it** (renter). Before that the button reads "Hand-over opens
   {when}".
2. `POST /bookings/{id}/start`. The booking becomes `active`. No
   notification goes out; the other side sees it on the page.
3. The app offers **check-in photos** at once. Before that, while the
   booking is `accepted`, both sides see a safety card: meet at the address in
   the booking, take check-in photos together, keep messages and payments on
   Cappy, and call the local emergency number first if unsafe, with a link to
   **How we keep you safe**.

### Hand-over photos (evidence)

- Check-in photos can be added while the booking is `accepted` or `active`.
  Check-out photos can be added while it is `active`, `completed` or
  `disputed` (`booking/messages.py`, mirrored in `Evidence.tsx`).
- Each photo is shrunk on the device and uploaded privately
  (`POST /uploads?purpose=evidence`, which answers a reference, not a URL),
  with "Uploading {n} of {total} · {pct} %" on the button; then
  `POST /bookings/{id}/evidence {stage, photos (1 to 12), note (up to 1000)}`.
  A retried save does not upload the photos again and sends the same key. The
  catalog confirms the photos are the sender's own private uploads and marks
  them kept, so the unused-upload sweep never deletes them.
- Both sides, and staff with MFA, see all evidence. Each photo is a link
  signed for 15 minutes and served by booking, never a public CDN address;
  the app re-reads the list every 10 minutes, and when a link has lapsed.
  Staff look at it first in a dispute.
- The panel shows when each photo was uploaded, and says: "Found damage or a
  problem? Report it before the booking is marked complete, at the latest 48
  hours after it ends." 

### Complete

1. Only the **renter** completes, from `active`: **Mark as handed back**, then
   the sheet "Handed back and all fine?", offering **Yes, it is done**, **Add
   check-out photos first** or **Not yet**.
2. `POST /bookings/{id}/complete`. The booking becomes `completed`.
3. Payments transfers the owner's share ([section 18](#18-payouts-and-invoices)).
   The owner gets "You have been paid {amount}" (email, push, bell).
4. The renter gets "How was {title}?" (email, push, bell), and the rating
   sheet opens at once ([section 14](#14-reviews-both-sides-blind)).

### Auto-complete

48 h after the window ends, the sweep completes any booking still `accepted`
or `active`, and the owner is paid. That covers renters who never press the
button and bookings where nobody marked the hand-over. A **disputed** booking
never auto-completes.

The owner has no button while the booking is `active`; completing is the
renter's word, or the sweep's.

---

## 11. No-show

**Who and where.** Either side, on `/bookings/{id}` of an **accepted**
booking whose hand-over nobody marked (S-11).

| Who reports | About | When | Result |
|---|---|---|---|
| Renter | the owner did not come | from the start until start + 2 h | cancelled, full refund, counts against the owner |
| Owner | the renter did not come | from start + 30 min until start + 2 h | cancelled, **no** refund, the owner is paid their share |

1. **{name} did not show up**, then confirm. The sheet says what happens to
   the money.
2. `POST /bookings/{id}/no-show`. The server checks the window (409 outside
   it, with the exact rule in the message), then sets `no_show` (`owner` or
   `renter`) and `refund_amount` (the full amount, or 0).
3. The booking becomes `cancelled`.
   - Owner missing: payments refunds everything and publishes
     `payment.refunded`.
   - Renter missing: nothing is refunded. The owner's share of what was kept
     is transferred and a fee invoice issued, unless payouts are switched off
     or there is a chargeback, in which case the event waits on its queue.
4. The other side gets the generic "Cancelled: {title}" email (always sent).
   Both see a banner: "Reported: … did not show up".
5. An owner's no-show counts in their reliability rate. Three cancels or
   no-shows in 30 days put them in the staff queue (`reliability` notice).

After 2 h the no-show button disappears. From then on the renter's route is
**Report a problem** (a dispute), and a booking left `accepted` completes by
itself 48 h after the end.

---

## 12. Cancel, withdraw and refund

**Who and where.** Either side, on `/bookings/{id}`. For the renter the
button reads **Withdraw from this booking**, because before the start it is
also their EU right of withdrawal (see `/legal/withdrawal`). For the owner it
reads **Cancel booking**.

**The rules** (`booking/state.py`, `booking/routes.py`,
`booking/cancellation.py`):

- Allowed from `awaiting_payment`, `requested` and `accepted`, by either side.
- **Only before the window starts.** After that the server answers 409 "the
  booked time has started; report a problem instead of cancelling", and the
  renter sees **Report a problem** in place of the button.
- **How much comes back.** Paid policies are off
  (the feature flag `paidCancellationPolicies` is not at 100 in
  `FEATURE_FLAGS`), so every cancellation is treated as
  *flexible*: a full refund. The code for the others is in place for when
  counsel confirms them (G-B2):

  | Policy | Renter cancels | Owner cancels |
  |---|---|---|
  | flexible | full until the start | full |
  | moderate | full until 24 h before, then half | full |
  | strict | full until 7 days before, half until 24 h, then nothing | full |

  Nothing has been charged before the owner accepts, so a cancel then only
  releases the hold. Since `235eeaa` the server records no refund for it,
  and `GET /bookings/{id}/cancellation` answers `charged: false` and
  `refundAmount: 0`.

**Steps**

1. For an `accepted` booking the sheet fetches
   `GET /bookings/{id}/cancellation` (what cancelling now would refund) and
   shows "You get back …".
2. `POST /bookings/{id}/cancel`. The booking becomes `cancelled`, with
   `refund_amount` set when the card was charged (`accepted`).
3. Payments: not yet captured means the hold is cancelled. Captured means a
   refund of `refund_amount` (full or partial) and `payment.refunded`. With a
   partial refund, the owner's share of what was kept is transferred and
   invoiced.
4. The other side gets "Cancelled: {title}" (email always, plus push and
   bell). The window is free again.
5. An owner cancelling an `accepted` booking counts in their reliability rate
   and can flag them to staff.

**Edge cases**

- *Payment still being entered.* Cancelling from `awaiting_payment` voids the
  intent. A late `payment.authorised` is ignored.
- *Double tap.* The second call gets 409 ("cannot cancel a booking that is
  cancelled").
- *Offline.* The button is disabled.

---

## 13. Dispute and staff resolution

**Who and where.** The renter, on `/bookings/{id}`, once the booked time has
started, from `accepted` or `active`: **Report a problem**. The owner cannot
open a dispute. Staff resolve in the console at `/admin`, which only staff
accounts can use (the token's staff claim: the Cognito `admin` group by
default, `STAFF_CLAIM` and `STAFF_VALUE`); the server checks every call, and
wherever it is deployed also that the staff account has an authenticator app
(TOTP MFA). Without one every staff call answers 403 `mfa_required`, and the
console shows **Set up two-step sign-in** instead of the queue: **Start**
gives an `otpauth://` link ("Open in your authenticator app") and the key to
type; the first six-digit code turns MFA on, and from then on every sign-in
asks for a code ([section 3](#3-sign-in-session-refresh-and-sign-out)).
Locally MFA is not required (cognito-local has none).

1. The renter says what went wrong (1 to 500 characters).
   `POST /bookings/{id}/dispute {reason}`. The server refuses before the
   start ("nothing to report before the booked time; cancel instead").
2. The booking becomes `disputed`. The captured money stays with Cappy: no
   payout, and **no auto-complete**.
3. The renter sees "Under review: … The payment is on hold" and gets "We
   received your report: {title}". The owner sees "{renter} reported a
   problem… Your payout is on hold" and gets "A problem was reported:
   {title}… Your payout waits while we look at it" (both emailed always,
   plus push and bell, since `235eeaa`).
4. Staff open the console's **Act directly** section, pick **Resolve dispute:
   pay the owner** or **refund the buyer**, and enter the booking id. That calls
   `POST /admin/bookings/{id}/resolve {outcome}`; support tooling can also
   call `POST /internal/bookings/{id}/resolve` (runbook). There is no list of
   disputed bookings in the console yet.
   - `pay_owner`: `disputed` to `completed`. The owner's share is transferred
     and invoiced, the owner gets "You have been paid", and the renter gets
     "How was {title}?".
   - `refund_buyer`: `disputed` to `cancelled`. There is no `refund_amount`,
     so payments refunds in full. The renter gets "Cancelled: {title}"; the
     owner gets no email.
5. The transition is recorded as `by = support:{staff sub}`.

Evidence photos (`GET /bookings/{id}/evidence` works for staff with MFA,
not only the two sides) and the message thread are what staff look at. Card
chargebacks are a separate path ([section 8](#8-payment)).

```mermaid
sequenceDiagram
  participant R as Renter
  participant B as booking
  participant St as Staff console
  participant P as payments
  R->>B: POST /bookings/{id}/dispute
  B->>B: accepted/active -> disputed (payout held)
  St->>B: POST /admin/bookings/{id}/resolve
  alt pay_owner
    B->>P: status_changed to completed
    P->>P: transfer owner share, issue fee invoice
  else refund_buyer
    B->>P: status_changed to cancelled
    P->>P: refund in full
  end
```

---

## 14. Reviews, both sides, blind

**Who and where.** Both sides of a **completed** booking, on
`/bookings/{id}`. The renter's **Bookings** tab badge counts completed
bookings they have not rated.

- **The renter rates the owner**: on time or late, 1 to 5 stars for the thing
  itself, any of the review tags, and an optional note (400 characters in the
  app; the server keeps 1000). `POST /bookings/{id}/rate` with an
  `Idempotency-Key` per form.
- **The owner rates the renter**: 1 to 5 stars. `POST /bookings/{id}/rate-renter`,
  also with a key. Only owners see renter ratings, as a renter record on
  requests.
- Each side rates **once**, only while the booking is `completed`, and only
  **within 14 days of the window's end** (409 "reviews close 14 days after the
  booked time").

**Blind.** Neither side sees the other's rating until both are in or the
window closes (`to_booking` hides it). Then `publish_reviews`:

- publishes `booking.rated`. The catalog adds the review to the listing (the
  author shown as "Ada L."), dated at the window's end or the rating time,
  whichever came first, and moves the owner's record, which also moves their
  ranking;
- publishes `booking.renter_rated`. The catalog moves the renter's record.

When only one rating came in, the booking sweep publishes it once the 14 days
are over. A redelivered `booking.rated` is counted once (review id
`rv_{booking}`).

---

## 15. Messaging and masking

**Who and where.** Both sides, in **Messages with {name}** on
`/bookings/{id}`. The panel is hidden while the booking is `awaiting_payment`,
and read-only once it is declined, cancelled, expired or `payment_failed`.
The server agrees since `235eeaa`: a message to such a booking, or to a
completed one more than 14 days after its window, gets 409
`conversation_closed` ("this booking is closed; its conversation is
read-only"). The app does not handle that code, and still offers the
composer on an old completed booking
([gaps](#23-known-gaps-between-code-ui-and-docs)).

1. `POST /bookings/{id}/messages {body}` (1 to 2000 characters) with an
   `Idempotency-Key` per attempt (kept while the outcome is unknown). At most
   30 messages per sender per booking in 10 minutes; the 31st gets 429 "that
   is a lot of messages in a few minutes; wait a little". `GET` returns the conversation oldest first;
   the app polls every 5 s and on focus.
2. **Masking** (`booking/messages.py`). Until the booking is `accepted`,
   emails (including "bob at gmail dot com"), links and bare domains, phone
   numbers (7 or more digits), messenger handles and IBANs are replaced with
   "[shared once the booking is accepted]". Dates and times are never masked.
   The original is kept, and shown to both sides once the booking is
   `accepted`, `active`, `completed` or `disputed`. If an accepted booking is
   later cancelled, the details hide again. The app draws the placeholder as
   "contact hidden until accepted".
3. **Paying outside Cappy.** A message that asks for it (PayPal, bank
   transfer, cash, "Überweisung"…) is not blocked. It is flagged and logged.
   The sender sees "Keep payments on Cappy…", and the reader sees a warning
   with the advice to report it.
4. The recipient gets a **push** ("New message: {title}") and a bell item for
   every message, and, since `235eeaa`, an **email** at most once per
   conversation per 15 minutes, per the Messages setting. The email carries
   the title and a link, never the text.
5. **Report** is on every message from the other side; once it is sent, the
   sheet offers **Block {name} too**. **Block** (on the booking page or the
   listing) stops messages and new bookings both ways
   (`PUT /me/blocks/{person}`). The booking itself stands. Unblocking is on
   the Profile screen.
6. Drafts are saved per booking and survive an expired session.
7. Staff can remove a reported message: its words become "[removed by Cappy:
   it broke our rules]" for both sides ([section 20](#20-reporting-and-moderation-dsa)).

---

## 16. The ID check

**Who and where.** A renter whose booking total is **above 30 000 minor
units** of the listing's currency (EUR 300). There
are no categories in the list today. It starts from the listing page, when
`POST /bookings` answers 403 `verification_required`. The check is done once
per person.

1. The sheet **Check your ID once** explains it: a photo of an ID document
   and a selfie, checked by Stripe on Cappy's behalf, about two minutes. An
   explicit consent tick is required before it can start (biometric data,
   P-18).
2. `POST /payments/identity/session {consent: true}` starts or continues a
   session with the ID-check provider, Stripe Identity today (behind
   `IdentityProvider` since `235eeaa`). The server refuses without the
   consent (422 `consent_required`) and records when it was given and which
   wording (`identity-2026-09`). It answers a `clientSecret` (Stripe) or a
   `url` (a hosted provider). The app always opens Stripe's modal
   (`stripe.verifyIdentity(clientSecret)`); it does not read
   `identityProvider` from `/payments/config` yet.
3. The result comes by webhook: Stripe's `identity.verification_session.*`
   events at the payments webhook (`verified`; `requires_input` → needs
   input; `canceled` → failed), or another provider's at
   `/payments/webhooks/identity`. It counts only for the person's current
   session. On `verified`, payments publishes `payment.identity_verified`;
   booking records the person as verified, and the profile shows the
   verified badge (since `235eeaa`).
4. The app polls `GET /payments/identity` every 2 s for up to 60 s, then
   retries the **same booking attempt, with the same key**.
5. If Stripe is still processing: "Your ID check is still being processed.
   Try booking again in a few minutes."

With the fake provider (local) the check passes at once. Refusing the consent
means this booking cannot go ahead. An account deletion forgets the
verification and has the provider erase the document and selfie (since
`235eeaa`).

---

## 17. Becoming an owner and creating a listing

**Who and where.** Any member. Every account can both rent and earn. The way
in is the **Earn** tab (`/earn`; "List your first thing" when empty) or
**List something you own** on the Profile screen. Both lead to `/earn/new`.

1. **Pick a category.** The category fixes the mode: `window` (book hours) or
   `batch` (a quantity, priced by throughput).
2. **The details** (`AddListing.tsx`): title (up to 120 characters), blurb (up
   to 500), district, the **hand-over address** (private until a booking is
   accepted), rate, minimum and maximum hours or throughput and setup, extras
   (money inputs show the currency's own symbol), up to 12 photos (each shrunk
   on the device to 2048 px, then `POST /uploads`, which re-encodes to WebP;
   each tile shows its progress, and a failed one keeps its reason and a
   **Retry**; a HEIC photo the browser cannot read is refused with "Take a
   screenshot of it, or on the iPhone set Camera → Formats → Most
   Compatible"), house rules (up to 12), instructions (up to 2000), the
   free windows, **Instant book** and the **cancellation policy**. A
   non-flexible policy is marked as not in force yet.
3. The form is saved as a draft as it is typed, and offers "Your unsaved
   changes are back" with **Discard**.
4. **Publish**: `POST /listings {listing, slots, address}` with an
   `Idempotency-Key` per attempt (the slots start at the next quarter hour, so
   a retry sends the same body). The catalog checks: the listings
   kill switch (503), that a profile exists (403), that the account is not
   suspended (403), 20 listings a day (429), every field and number within
   bounds, category and mode matching, a known district, and that every photo
   is the owner's own upload. It then publishes `listing.changed`
   (`created`).
5. The app says "{title} is live" (or, when the server held it, "{title} is
   saved and waiting for a quick check before people can book it"), goes to
   `/earn`, and offers push the first time.

### Held listings

If the owner has **no completed jobs** and the rate is **above EUR 100/h**,
the listing is **held**: it exists, but nobody else can see or book it until
staff approve it (`POST /admin/listings/{id}/approve`, which publishes
`listing.changed` `approved`). Raising the price of a listing past that line
before the first completed job holds it again. The owner's Earn card shows
"Waiting for a quick check". An edit that holds it says so too. Staff see the
held listings in the console (`GET /admin/listings/held`) and approve them
there.

### Managing listings (Earn)

- **Edit** (`/earn/edit/{id}`): `PUT /listings/{id}`, plus removing and adding
  windows. The mode and category cannot change.
- **Pause / Resume**: `POST /listings/{id}/pause` or `/resume`. A paused
  listing is not offered, and pending requests stay.
- **Remove** (confirmed): `DELETE /listings/{id}` is a soft delete.
  `listing.changed` (`removed`) declines pending requests and releases their
  holds. Confirmed bookings stand.
- **View as a guest** opens the public page, also for a held or paused
  listing (since `235eeaa`).
- The Earn screen also shows idle hours this week and their value, hours sold,
  earned (completed) and "to come" (accepted or active), what is coming up,
  invoices, and the owner's record.

**Payouts must be set up before anyone can pay the owner** ([section 18](#18-payouts-and-invoices)).
Deployed, the catalog hides listings of owners Stripe cannot pay yet.

---

## 18. Payouts and invoices

**Who and where.** Owners, on the **Earn** tab.

### Setting up payouts (Stripe Connect)

1. While Stripe cannot pay the owner, Earn shows **Set up payouts to take
   bookings** (or **Continue setup**).
2. `POST /payments/connect/onboarding` creates the connected account if there
   is none and returns a Stripe-hosted onboarding link. The app navigates to
   it. Cappy never sees identity or bank details. Since `235eeaa` the call
   takes `{country}` and creates the account there; a country outside the
   EEA, Switzerland, the UK, the US and Canada gets 422 `country_unsupported`.
   The app sends none, so the account is German.
3. Stripe sends the owner back to `{WEB_BASE_URL}/earn?payments=done` (or
   `?payments=retry`). `/earn` is an App Link path, so in the store apps the
   return opens the app.
4. `GET /payments/connect/status` asks Stripe directly while payouts are not
   enabled, so the result shows without waiting for a webhook. Earn shows
   "Stripe is checking your details" in the meantime.
5. `account.updated` webhooks keep it current. Payments re-reads the account
   from Stripe, because webhooks arrive out of order. When the "can be paid"
   state changes, it publishes `payment.payouts_ready` (with `asOf`) and the
   catalog shows or hides the owner's listings.

Locally, the fake provider makes every owner payable on their first booking.

### Being paid

- **When**: the booking becomes `completed` (the renter confirms, the sweep
  after 48 h, or staff `pay_owner`), or a late cancellation or renter
  no-show leaves money with the owner.
- **What**: a Stripe transfer of the owner's share (`ownerNet`, the total
  less the 15 % fee) against the booking's charge, with idempotency keys from
  the booking. Then `payment.payout_sent`, and the owner gets "You have been
  paid {amount}" (email, push, bell).
- **Held**: the payouts kill switch (`PAYOUTS_ON=false`) leaves the event on
  its queue, retried with backoff, and nothing is lost. A chargeback holds the
  payout for a person. A disputed booking is never paid until resolved.

### Invoices

- For every payout, payments issues an invoice for **Cappy's fee** to the
  owner, once per booking, numbered per year in the issuer's time zone. VAT
  is treated as included, at 19 % German USt by default (`payments/invoices.py`,
  `Issuer`).
- Invoices are kept 10 years from the end of the year of issue (the
  issuer's setting), then deleted (since `235eeaa`).
- `GET /payments/invoices` lists them on Earn. Tapping one fetches
  `GET /payments/invoices/{number}` (HTML, which needs the token). The web
  opens it in a new tab; the store apps hand it to the share sheet to print,
  save or mail.

---

## 19. Notifications and their settings

**Where.** The bell is `/notifications`. On a phone it is on the **You** tab
with an unread badge; on a desktop, in the header. The settings are on the
Profile screen under **Notifications**.

### What goes out

| Booking change | To | Text key | Email | Push | Bell |
|---|---|---|---|---|---|
| to `requested` | owner | "New request: … Answer by {deadline}" | per setting | per setting | yes |
| to `accepted` | renter | "Confirmed: …" | **always** | per setting | yes |
| instant book (`awaiting_payment` to `accepted`) | owner | "New booking: … booked instantly" | **always** | per setting | yes |
| to `declined` | renter | "Declined: … Nothing was charged." | **always** | per setting | yes |
| to `cancelled` | the side that did not cancel (the renter when staff or the system did) | "Cancelled: …" | **always** | per setting | yes |
| to `expired` from `requested` | renter | "Expired: … Nothing was charged." | **always** | per setting | yes |
| to `completed` | renter | "How was …? Rate it" | per setting | per setting | yes |
| to `payment_failed` | renter; the owner too when it failed after they accepted | "Payment failed: … Nothing was taken." | **always** | per setting | yes |
| to `disputed` | owner | "A problem was reported: … Your payout waits" | **always** | per setting | yes |
| to `disputed` | renter | "We received your report: …" | **always** | per setting | yes |
| payout sent | owner | "You have been paid {amount}" | per setting | per setting | yes |
| new message | recipient | "New message: …" | per setting, at most once per conversation per 15 min | per setting | yes |
| report received | reporter | "We received your report" | always | never | yes, if signed in |
| moderation decision | person affected, reporter | statement of reasons / outcome | always | never | yes, if signed in |

The `payment_failed`, `disputed` and message emails are new in `235eeaa`
(FL-2, FL-3). Nothing goes out for `active` or an expiry from
`awaiting_payment`. The moderation decision texts include "We removed
something you wrote" for a removed message or review.

- **Language**: each person's Cognito `locale`: German for any `de…`, French
  for any `fr…` (one neutral French for France and Québec, since `235eeaa`),
  English otherwise. The bell re-renders each item in the language it is read
  in, with the same three languages. Amounts are written in the booking's
  currency in the reader's format.
- **Times** in emails are told in Europe/Berlin (`texts.py`
  `DEFAULT_TIME_ZONE`), because listings carry no time zone yet.
- **Emails** only go to a verified address.
- **Pushes** go to every registered device of the person. A device that has
  gone is forgotten.
- Delivery is at least once. A crash after sending can send the same email
  twice, but never loses one. Bell items are keyed by event, person and text,
  so they are kept once.

### Settings

`GET` / `PUT /notifications/settings`: push and email for each of Bookings and
requests, Messages, Payouts, and News and offers. Marketing is off by
default; Cappy sends none. The toggles are saved as they are flipped, and roll
back on an error. The bell always gets everything. The emails marked
**always** above go out whatever the setting: they are the durable record of
a contract or of money (§ 312f BGB), or the law requires them (DSA).

### The bell

`GET /notifications` shows the newest first, in the app's language
(`Accept-Language`), with an unread count. The app polls every 60 s and on
focus. Opening the screen marks what is on it read after 1.5 s; **Mark all as
read** is also there. Tapping an item opens its screen inside the app. Links
that point off the app are never followed.

### In the store apps

On a phone the Profile screen also shows whether push is on. If it is off,
iOS gets **Turn on in Settings**, which opens the app's own page in Settings,
and Android gets the path to follow by hand. If the app has not asked yet,
there is **Turn on notifications**. The timing of the first ask is in
[section 22](#22-the-store-apps).

---

## 20. Reporting and moderation (DSA)

**Who and where.** Any member can report a **listing** (on its page), a
**person** (the owner card, or the other party on a booking), a **message**
(on each message) or a **review**. Anyone signed out can report from
`/legal/report` ("Report content"): they pick what they are reporting and
paste its link or reference, and leave an email so they can hear back (DSA
Art. 16).

### Reporting

1. **Report** opens a sheet: a reason (illegal, fraud, unsafe, counterfeit,
   spam, offensive, privacy, other), details of at least 10 characters, an
   email when signed out, and the **good-faith statement**, which is required
   (Art. 16(2)(d)).
2. `POST /reports`, with an `Idempotency-Key` per attempt. Signed in, the
   reporter hears back at their own verified address, never one they type.
   Limits: 3 reports a day per anonymous email; about any one target, 5
   anonymous and 20 signed-in reports a day, counted apart so strangers cannot
   use up the members' share.
3. The report is stored as `open`, and `moderation.report_received` goes out.
   The reporter gets "We received your report", with the reference (email,
   plus the bell if signed in). The sheet shows the reference too, and after a
   message report offers **Block {name} too**.

### Staff decide (`/admin`)

1. **The queue**: `GET /admin/reports?status=open`, oldest first. It also
   holds notices the system raised: `reliability` (an owner with 3 cancels or
   no-shows in 30 days) and `linked_to_suspended` (a card a suspended account
   used). There is one open notice per person and reason.
2. **Decide**: `POST /admin/reports/{id}/decide {action, statement (at least
   20 characters), ground (law or terms), clause, automated}`.
   - `dismiss`: nobody is restricted. The reporter gets "we found no breach".
   - `take_down` (listings only): the listing is hidden (`moderated_at`),
     `listing.changed` (`removed`, by staff) declines its pending requests with
     "The listing was taken down by Cappy", and its photos are purged from
     the CDN.
   - `remove_content` (messages and reviews, since `235eeaa`): a message's
     words become "[removed by Cappy: it broke our rules]"; a review loses
     its text and tags and keeps its stars. The author is told; the account
     is not otherwise restricted. The console calls it **Remove the message /
     review**. A listing is refused (422): it is taken down instead.
   - `suspend`: the person behind the target (a listing's or profile's
     owner, a review's or message's author, since `235eeaa`) is marked
     suspended, all their live listings are taken down, and
     `moderation.owner_suspended` goes out. Booking then refuses their new
     bookings and declines their own pending requests; the catalog refuses
     their new listings. The console calls it **Suspend the author** for a
     message or review.
3. **The statement of reasons** (Art. 17): the person affected gets "We
   removed your listing", "We removed something you wrote" or "We suspended
   your account", with the facts, the
   ground, whether it was automated, and how to contest it (reply within
   6 months, out-of-court settlement under Art. 21, or the courts). The
   reporter gets the outcome (Art. 16(5)).
4. **Direct actions** without a report: take down a listing, suspend or
   reinstate an owner, and resolve a dispute. A reinstated owner can list and
   book again, but their listings stay down.
5. Everything is written to the audit log (`GET /admin/audit`). The DSA
   transparency figures for a month come from `GET /admin/dsa-stats?month=`.
6. Six months after a decision (183 days) the report forgets who made it:
   their id, email and words go; the case and the decision stay (since
   `235eeaa`).

**While suspended**: accepted bookings stand on both sides (the owner still
owes them), sign-in still works, and messages still work.

**Signed out**: `/legal/report` explains reporting and carries the form
(since `f22f143`).

---

## 21. Data export and account deletion

**Who and where.** Any member, on the Profile screen under **Your data**. The
public page `/account/delete` explains the steps for Google Play and for
people who cannot sign in.

### Download my data (GDPR Art. 15/20)

1. `GET /me/export`, at most 5 a day (429 after that: "you have downloaded
   your data several times today; try again tomorrow"). The catalog gathers
   its own data (profile, listings, saved listings, reviews written and
   reviews about them, uploads, reports they filed, moderation decisions
   about their listings and profile), then asks booking (bookings, messages
   sent with the original unmasked text, evidence with its notes, who they
   blocked, the verified and suspended flags, their card fingerprints),
   payments (payout link, ID-check status, invoices with the recipient
   details, payments with whether they were charged, refunded and paid out;
   never card details) and notifications (bell items, settings, devices, and
   the sign-in's email and language). The additions are from `235eeaa`. It
   returns one JSON file, `cappy-my-data.json`. Hand-over photos appear as
   `evidence:…` references, not pictures.
2. The web downloads the file (or uses the share sheet on phones that cannot
   save a download). The store apps write it to the cache and open the share
   sheet.

### Delete account

1. **Delete account** opens a sheet explaining what goes and what is kept.
2. `DELETE /me`. The catalog asks booking for **open bookings** (see
   [section 7](#the-booking-lifecycle)) and payments for **pending payouts**
   (captured money not yet paid out to this person). If there are any, it
   answers 409 `open_obligations` with the counts and `until`, the end of the
   last open window. The sheet shows "finish or cancel your open bookings, and
   wait for your payouts, before deleting your account. You can delete your
   account from {date}."
3. Otherwise the catalog **forgets** the person: listings are soft-deleted
   and lose their title, description, instructions, rules, photos and
   address; every photo they uploaded is deleted within the hour; saved
   listings, the payable flag and stored answers are removed; reports they
   filed lose their name, email and words; the profile becomes an anonymous
   "Former member" without its badge or business; and reviews they wrote are
   re-signed "Former member". Their tokens stop working in catalog at once.
   It then publishes `profile.deleted`, which leads to (each service also
   stops accepting their tokens):
   - booking: blocks and the verified flag deleted, and their messages
     replaced with "[removed: the account was deleted]". Bookings stay as
     financial records, without the hand-over address and instructions, the
     owner's name and business, notes, and (unless suspended) the card
     fingerprint; their hand-over photos and notes go;
   - payments: the payout link deleted, the ID-check session erased at the
     provider and its record deleted, and card fingerprints cleared. The
     Stripe account itself stays with Stripe;
   - notifications: the Cognito user deleted (`AdminDeleteUser`: the sign-in
     and the email go), then devices (with their push endpoints), bell items
     and settings.

   The redactions are new in `235eeaa` (D-1 to D-7).
4. The app also calls Cognito `DeleteUser` itself (twice at most, the quick
   path; failures are ignored because the server finishes it), then signs out
   in every tab, clears the cache and shows "Your account is deleted".

**Edge cases**

- *Open bookings, on either side, including `disputed`.* Refused, as in
  step 2. The person has to finish, cancel or wait.
- *The app's `DeleteUser` fails after step 3* (offline, or the server was
  first). The person is signed out anyway and never lands in onboarding; the
  server deletes the sign-in when `profile.deleted` reaches notifications.
- *What the sheet promises.* "Your sign-in, profile and saved listings are
  deleted", listings taken down and names removed from reviews; bookings,
  payments and invoices kept without the name for up to ten years. It does not
  mention photos, which are now deleted too (since `235eeaa`).
- *Signing up again later with the same sign-in* starts from nothing
  ([section 4](#4-onboarding-profile-18-business-identity-rent--earn--both)).
- *Session expired.* "Sign in again to delete your account."

---

## 22. The store apps

The iOS and Android apps are Capacitor shells around the same build
(`web/capacitor.config.ts`, app id `app.cappy`). They call the public API at
`VITE_API_URL`. Media paths are resolved against the API's origin.

### Welcome and sign-in

These work as on the web ([sections 1 to 3](#1-first-run-and-welcome)). The
refresh token and device flags are kept in Capacitor Preferences (the
platform's app storage), because iOS can purge a web view's localStorage.

### Push permission timing (U-4)

- The OS is **never asked at sign-in**. After sign-in the app only
  re-registers if permission was already granted
  (`enablePush(accessToken)` in `Member`).
- The first moment it asks is right after the **first booking request** or the
  **first published listing**. `PushPrime` shows a sheet first ("Get told when
  it matters"), then **Turn on notifications** or **Not now**. It is asked
  once per device (`pushAsked`), and only if the OS would still ask.
- Once granted, `PushNotifications.register()` returns the APNs or FCM token,
  and the app sends `POST /notifications/devices {platform, token, installId}`
  (`installId` is a random id the app makes once per install). The server
  creates an SNS platform endpoint. A token moves to whoever signs in on that
  device next only with the same `installId`: the old endpoint is deleted
  first, so none of the previous person's pushes reach it. A different
  install gets 409 `device_taken`, and the app leaves push off there. At most
  10 devices are kept per person.
- After any sign-out, or a session ended elsewhere, the next account to sign
  in on the device registers afresh (FL-13).
- Sign-out removes this device's token (`DELETE /notifications/devices/{token}`).
  Sign out everywhere removes all of them. Since `235eeaa` each removal also
  deletes the device's SNS endpoint.
- The Profile screen shows the permission state and a way to turn it on
  ([section 19](#19-notifications-and-their-settings)).

### Deep links

- **Universal Links (iOS) and App Links (Android)** for `/listing/*`,
  `/bookings/*`, `/earn*` and `/pay/*`. The web build writes
  `/.well-known/apple-app-site-association` and `/.well-known/assetlinks.json`
  from `VITE_APPLE_TEAM_ID` and `VITE_ANDROID_SHA256`. Unset, they carry
  placeholders and verify nothing. The Android intent filter uses
  `${appLinkHost}`; the iOS entitlements say `applinks:$(CAPPY_DOMAIN)`
  (`cappy.app` in the Xcode build settings).
- An opened link (`appUrlOpen`) or a tapped push (`data.link`) is turned into
  an in-app path and routed like a tap.
- Signed out, a deep link goes to `/login?next=<path>` and returns there
  after sign-in. It never shows the welcome.

### The Android back button (U-5)

In order: close the top sheet, if one is open (`sheets.ts`); else go back one
screen, if there is history and this is not `/`; else minimise the app (not
kill it), as native apps do.

### Offline (U-11)

- A bar above the dock: "You are offline. What you see may be out of date;
  paying, booking and sending wait until you are back." This is the same on
  the web.
- What is cached stays readable. Every button that moves money or sends
  something is disabled while offline: book, pay, accept, decline, start,
  complete, cancel, dispute, no-show, send, rate and block.
- The service worker (web) caches the app shell only, never the API.
- API calls that fail on the network say "Cannot reach Cappy. Check your
  connection and try again." Reads retry twice with backoff; 4xx answers are
  never retried.
- A cold start offline opens the app as the last signed-in person, with the
  offline bar, and signs in for real once the network is back.

### Forced update

At start the app reads `GET /app-config` (`minVersion`, `latestVersion`,
`flags`, `rollouts`). Every API call carries `X-App-Version`. A **store
build** below `minVersion` shows only **Update Cappy** ("This version of the
app is too old to talk to Cappy safely…") and a link to its own store
(`VITE_APP_STORE_URL` / `VITE_PLAY_STORE_URL`). The web is always the current
build and is never gated. An older backend without `/app-config` does not
block the app. `latestVersion` is read but nothing shows a soft "update
available" today.

### Other differences from the web

- **Data export and invoices** go to the share sheet: there are no downloads
  or tabs in a shell.
- **Stripe payouts onboarding** leaves the app for Stripe, and comes back
  through the `/earn` App Link. A bank's card check comes back through the
  `/pay/*` App Link ([section 8](#8-payment)).
- **Text size**: on iOS the app follows the reader's Dynamic Type setting,
  also when it changes while the app is in the background; Android's WebView
  scales text by itself.
- **Camera and photos**: the iOS usage strings cover listing and hand-over
  photos.
- **Crash reports** from both go to `POST /client-errors`: the message, stack,
  route, version and platform, and nothing that identifies the person. The
  gateway replaces emails and phone numbers before logging.

---

## 23. Known gaps between code, UI and docs

Found while writing this file. Each is a place where the code, the UI and the
docs say different things. They are listed so they are not mistaken for
intended behaviour. Each keeps the number of its `FL-` task in
[`TASKS.md`](TASKS.md).

Items marked **fixed** are kept, struck through, with the commit that fixed
them, until the next pass removes them. The pass at `c454c92` removed those
fixed in `f42a4ef` and `f22f143` (FL-1, 4, 5, 10, 11, 13, 14, 16, 17, 19 and
21).

- **FL-2.** ~~**Nobody is told about `payment_failed` or `disputed`.**~~
  **Fixed in `235eeaa`**: a failed payment tells the renter, and the owner too
  when the capture failed after they accepted; a dispute tells both sides
  (all always emailed, [section 19](#19-notifications-and-their-settings)).
  `active` still tells no one, by design (the other side sees it on the
  page).
- **FL-3.** ~~**The Messages email toggle does nothing.**~~ **Fixed on the
  server in `235eeaa`**: messages are emailed at most once per conversation
  per 15 minutes, per the setting. The Profile text shown before the settings
  load still says "Everything also arrives by email" (`Profile.tsx:596`); see
  the open web items below.
- **FL-6.** ~~**The owner of a held listing gets 404 on its page.**~~ **Fixed
  in `235eeaa`**: the owner can open their own held or paused listing, so
  **View as a guest** works.
- **FL-7.** ~~**Removing or suspending from a message or review report
  fails.**~~ **Fixed in `235eeaa`**: the server accepts `remove_content` and
  suspends the message's or review's author.
- **FL-8.** **"Refunded" shown when nothing was charged.** ~~The server
  recorded a full `refund_amount` for a request cancelled before the
  accept.~~ **Fixed on the server in `235eeaa`**: nothing is recorded, and the
  cancellation quote says `charged: false`. Still open in the app: after a
  staff **Refund the buyer** there is no `refundAmount` either, so the
  booking page says "The hold on your card is released; nothing was charged"
  (`BookingDetail.tsx:418-426`) although the charge was refunded in full.
- **FL-9.** ~~**The removal reason blames the owner when moderation did
  it.**~~ **Fixed in `235eeaa`**: a staff take-down declines with "The
  listing was taken down by Cappy". The app shows it in English only (open
  web items).
- **FL-12.** ~~**Photos of a deleted account are not deleted.**~~ **Fixed in
  `235eeaa`** (D-1): every upload of the person goes with the next hourly
  sweep. The deletion sheet (fixed in `f22f143`) no longer promises it, so it
  now says less than happens.
- **FL-15.** ~~**The owner sees unpaid bookings.**~~ **Fixed in `235eeaa`**:
  `GET /bookings?role=owner` and the booking page hide `awaiting_payment`
  bookings and payments that failed before the owner saw them.
- **FL-18.** ~~**Server and client disagree on closed conversations.**~~
  **Fixed on the server in `235eeaa`**: `POST /bookings/{id}/messages`
  answers 409 `conversation_closed` for cancelled, declined, expired and
  `payment_failed` bookings, and for completed ones after the 14-day review
  window. The app closes the composer for the first four only and does not
  handle the code (open web items).
- **FL-20.** ~~**ADR 0012 is out of date on two points.**~~ **Fixed in
  `c454c92`**: the ADR carries a dated correction (Capacitor Preferences for
  the refresh token, push built).
- **One market in the code.** ~~Bookings are always `currency="eur"`.~~
  **Fixed in `235eeaa`** (M-3): a booking takes its listing's currency. Still
  one market: email times are Berlin time, the business VAT check only knows
  EU formats, the ID-check and held-listing thresholds are one number of
  minor units for every currency, and the report sheet says "call 112"
  (`Report.tsx:224`), which is not the emergency number in the US and Canada
  (GOAL 16).
- ~~**Miles for English readers in Europe.**~~ **Fixed in `44a5520`**: English
  without an English region of its own formats as `en-IE` (km, 24 h).
- ~~**A partial rollout of `paidCancellationPolicies` splits the app from the
  server.**~~ **Fixed in `44a5520`**: the app reads it with `useGlobalFlag`,
  where only 100 % counts, as booking does.
- **Stale docstring on account deletion.** `delete_me`
  (`catalog/routes.py:349-352`) still says the app deletes the sign-in and
  that bookings and payments "hold no personal data"; the server deletes the
  sign-in since `f303350`, and bookings keep redacted records
  ([`DATA.md`](DATA.md) §5.4).

### Open web items from the backend round (`235eeaa`)

The server changed; the app does not follow yet (`web/` is unchanged since
`44a5520`).

- **`conversation_closed`.** Handle the 409 from `POST /bookings/{id}/messages`
  (close the composer, say why), including a completed booking whose review
  window has closed, which the app still offers a composer for
  (`Conversation.tsx:136`, `BookingDetail.tsx:573`).
- **The `charged` flag in the cancel sheet.** `GET /bookings/{id}/cancellation`
  now says whether anything was charged; the sheet fetches it only for
  `accepted` bookings and words the rest by status
  (`BookingDetail.tsx:164`, `:745-750`). Use `charged`, and fix the
  **Refund the buyer** banner (FL-8 above).
- **German and French for the new decline reason** "The listing was taken
  down by Cappy". The app translates `declineReason` through `t()`
  (`BookingDetail.tsx:377`), and neither `i18n.de.ts` nor `i18n.fr.ts` has
  it. The same is true of the older system reasons "The listing was removed
  by its owner" and "The account was suspended".
- **The Profile copy about message emails.** Messages are now emailed (at
  most once per conversation per 15 minutes, per the setting); the Profile
  text "Only bookings and messages; never marketing. Everything also arrives
  by email." (`Profile.tsx:596`) needs to match. No string in the app says
  messages are never emailed today.
- **The country at payout onboarding.** `POST /payments/connect/onboarding`
  takes `{country}` (and `PUT /me` a `country`), and Stripe fixes an account's
  country at creation; the app sends neither, so every payout account is
  German. Send the owner's country, and show `country_unsupported`.
- **`identityProvider` driving the ID-check UI.** `/payments/config` names the
  ID-check provider and a session may answer a hosted `url`; the app always
  opens Stripe.js `verifyIdentity` (`Listing.tsx:222-244`).
- **Currency case.** Listings and quotes carry upper-case codes (`EUR`,
  `CAD`), bookings, payments and cancellation quotes lower-case (`eur`,
  Stripe's form). `formatMoney` upper-cases before formatting, so display is
  right, but the client should normalise one form before comparing or
  storing currencies.

---

## 24. How to keep this file true

This is one of the living docs in `CLAUDE.md` ("Living docs: keep them
true"). It describes the system as it is now, and **any change that alters a
flow updates this file in the same commit**: a new state or transition, a
timer or limit, a new screen, button or route, a changed notification, email
or push, or a web or app difference. Builders and agents included.

- Take the numbers from the code and name the file. Do not copy them from
  another doc.
- When you fix an item in [section 23](#23-known-gaps-between-code-ui-and-docs),
  delete it and describe the new behaviour in its flow.
- A flow that changes *why* the system is built a certain way also needs a new
  ADR (`docs/adr/`), not only an edit here.
- The companion docs are `docs/FEATURES.md` (what exists and its provider
  seams), `docs/INFRA.md` (resources and switches) and `docs/DATA.md`
  (tables, events and personal data). Keep them consistent with this file.
