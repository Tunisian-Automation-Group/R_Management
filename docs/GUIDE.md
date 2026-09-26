# Cappy guide: testing and developing locally

Cappy is a members-only marketplace where people and firms rent out idle
machines, rooms, vehicles and storage by the hour. It ships as a web app (an
installable PWA) and as iOS and Android apps, which are Capacitor shells
around the same build (ADR 0012). Markets are all of Europe, the US and
Canada (GOAL 16, ADR 0013); each country is a market in
`backend/libs/cappy_common/cappy_common/markets.json`, and only Germany,
Austria and Switzerland are open (`live`) today. The demo data is set in
Berlin, with some listings in Amsterdam, Paris, Lyon, Milan, Brescia and
Lisbon.

This guide has two parts:

- **Part A** is for testers and other non-developers: product people, QA and
  the owner. You get a running local environment and test every feature by
  hand.
- **Part B** is for developers: setup, architecture, running, debugging,
  tests and conventions.

Everything here runs on one computer. **Nothing is ever run against real AWS
or any real cloud account** (GOAL 12). No staging or production environment
exists yet: the Terraform for them is only validated, never applied.

## Contents

- [Quick start for testers (5 minutes)](#quick-start-for-testers-5-minutes)
- [Quick start for developers (5 minutes)](#quick-start-for-developers-5-minutes)
- **Part A: testing by hand**
  - [A1. Test accounts](#a1-test-accounts)
  - [A2. Payments while testing](#a2-payments-while-testing)
  - [A3. Before you start: tips that save time](#a3-before-you-start-tips-that-save-time)
  - [A4. Test scripts, feature by feature](#a4-test-scripts-feature-by-feature)
  - [A5. Shortcutting time-based steps](#a5-shortcutting-time-based-steps)
  - [A6. Resetting the local data](#a6-resetting-the-local-data)
  - [A7. Testing the app version](#a7-testing-the-app-version)
  - [A8. Reporting a bug](#a8-reporting-a-bug)
- **Part B: developing**
  - [B1. Prerequisites](#b1-prerequisites)
  - [B2. One-time setup](#b2-one-time-setup)
  - [B3. Architecture in brief](#b3-architecture-in-brief)
  - [B4. make targets](#b4-make-targets)
  - [B5. Ports and URLs](#b5-ports-and-urls)
  - [B6. Env files and secrets](#b6-env-files-and-secrets)
  - [B7. Running services, logs and the web dev server](#b7-running-services-logs-and-the-web-dev-server)
  - [B8. Tests](#b8-tests)
  - [B9. Adding a feature](#b9-adding-a-feature)
  - [B10. Swapping a provider](#b10-swapping-a-provider)
  - [B11. Debugging recipes](#b11-debugging-recipes)
  - [B12. Where to look](#b12-where-to-look)
- [How to keep this file true](#how-to-keep-this-file-true)

---

## Quick start for testers (5 minutes)

Usually a developer sets up your computer once (Part B, [B2](#b2-one-time-setup)).
After that, you start everything with three commands in a terminal, from the
project folder:

```sh
make up                      # starts the whole system and loads the demo data (a few minutes)
cd web && npm run dev        # starts the app; leave this window open
```

Then open **http://localhost:5173** in Chrome.

1. The welcome screen appears the first time. Choose **I have an account**.
2. Under the sign-in form, tap **Continue as demo buyer**. You are signed in
   as a renter with Berlin listings to browse.
3. Follow a test script in [A4](#a4-test-scripts-feature-by-feature).

To stop the system, run `make down` (your test data is kept). To start again
from a clean slate, see [A6](#a6-resetting-the-local-data).

## Quick start for developers (5 minutes)

Needs Docker, uv, Node 22, and a LocalStack Pro auth token
([B1](#b1-prerequisites)).

```sh
cp .env.example .env                       # put your LOCALSTACK_AUTH_TOKEN in it
(cd backend && uv sync --all-packages)     # Python deps for tests and scripts
make test                                  # lint + unit/API tests, no Docker
make up                                    # the stack, migrated and seeded
(cd web && npm install && npm run dev)     # http://localhost:5173
make e2e                                   # the whole journey against the running stack
```

Read `CLAUDE.md`, `docs/GOAL.md` and `docs/PLAN.md` ("Resume here") before you
change anything. Then read [B9](#b9-adding-a-feature).

---

# Part A: testing by hand

## A1. Test accounts

### The demo accounts

`make up` creates four accounts in the local sign-in service
(`local/bootstrap.py`, the `DEMO` list), all with verified emails:

| Role | Email | Password | What it is for |
|---|---|---|---|
| Host (owner) | `host@demo.cappy.local` | `Demo-pass-123!` | The seeded owner "Nadia Brandt" (Kreuzberg). Owns **one** demo listing: *Festool TS 55 plunge saw + 1.4 m rail* (Tempelhof, €4 an hour, 2 to 8 hours), with its seeded reviews and record. Use it to accept or decline requests, hand over, get paid and see invoices. |
| Second host (new owner) | `host2@demo.cappy.local` | `Demo-pass-123!` | "Demo Host Two" (Neukölln, Germany), with no completed jobs, so it behaves like a brand-new owner. Owns the three listings below. Use it for instant book, weekly opening hours, a batch (van) listing and the staff approval of a held listing (since `61b15b8`, GD-5). |
| Renter (buyer) | `buyer@demo.cappy.local` | `Demo-pass-123!` | "Demo Buyer", home district Kreuzberg. Use it to browse, book, pay, message, cancel, dispute and review. |
| Staff (moderator) | `staff@demo.cappy.local` | `Demo-pass-123!` | "Cappy Staff", in the `admin` group. Opens the staff console at `/admin`: reports, held listings, direct actions, the audit log. |

The second host's listings are made through the API by
`local/demo_profiles.py`, the way a new owner would make them (all in
Neukölln, hand-over address "Weserstraße 1, 12047 Berlin"):

| Listing | Price | Opening hours (weekly schedule, Berlin time) | What it is for |
|---|---|---|---|
| *Bandsaw and bench, book instantly* (workshop) | €15 an hour, 1 to 8 hours | Monday to Friday, 09:00 to 18:00 | **Instant book**: a booking is confirmed as soon as the card is held, with no host step (script 5) |
| *Van run, Neukölln to Leipzig on Saturdays* (freight, booked by quantity) | €25 an hour plus a €20 setup fee | Saturday and Sunday, 10:00 to 16:00 | A batch listing (pallet spaces), booked by request |
| *Photo studio with daylight wall (waits for review)* (creator) | €160 an hour, 2 to 10 hours | Monday to Friday, 09:00 to 18:00 | **Held for a staff check**: a new owner above €100 an hour. It waits under **Waiting for a check** in the console until staff approve it (scripts 15, 19) |

Their free windows come from the weekly schedule: the server keeps eight
weeks of windows open and rolls them on hourly, so these listings never run
out of time to book. The web's listing form does not offer weekly opening
hours yet; only the API does (FLOWS.md §23).

The buyer, second host and staff profiles are made by
`local/demo_profiles.py`, so they skip onboarding. The demo world also has
about 70 other owners and 78 listings, but **those owners have no sign-in**.
You can book their listings, and nobody will ever answer, so a request to
them simply lapses. For anything that needs the other side to act, book the
host's plunge saw or one of the second host's listings.

Be aware:

- **Local only.** These accounts are created by the local bootstrap and
  nowhere else. They are never created in staging or prod (ADR 0010: nothing
  demo-only runs in a service process, and the seeding command refuses to
  run in prod). The password `Demo-pass-123!` is a local-only value that
  appears in the repository on purpose. It is not a secret.
- **The "Continue as demo …" buttons** (**Continue as demo host**,
  **Continue as demo buyer**, **Continue as demo host2**, **Continue as demo
  staff**) appear under the
  sign-in form only when the build has `VITE_DEMO_ACCOUNTS`. Only the local
  bootstrap writes that setting (into `web/.env.development.local`, via
  `make up`), so a deployed build never has them.
- The store-review accounts in `docs/app-review.md` are something else. They
  are made by hand in the production user pool before a store submission, and
  their passwords never go in the repository.

### Making a fresh account

You need fresh accounts to test sign-up, onboarding, becoming a host, held
listings and account deletion. Deleting a demo account breaks the demo until
you reset (see [A6](#a6-resetting-the-local-data)).

1. Open http://localhost:5173/login and switch to **Create account**.
2. Enter any email address (it does not need to exist, for example
   `anna.test1@example.com`) and a password of **at least 12 characters**.
3. The screen changes to **Check your email**. No email is sent locally.
   Instead, ask the developer, or run this in a terminal from the project
   folder:
   ```sh
   make codes
   ```
   It prints the last 20 sign-up and password-reset codes, newest at the
   bottom, one per line: the email address it went to, then the code (since
   `61b15b8`, GD-2).
4. Type the six digits. The form submits by itself and signs you in.
5. Onboarding asks for your name, person or business, district, what brings
   you to Cappy, and the 18+ tick.

**Emails to fresh accounts.** The local sign-in service does not mark an
address as verified when you confirm it, and Cappy only emails verified
addresses. So a fresh account gets bell notifications but **no emails**
until you run, from the project folder:

```sh
make confirm EMAIL=anna.test1@example.com
```

It marks the email verified, and also confirms the account if the code was
never typed (`local/confirm.py`, since `61b15b8`, GD-2). The demo accounts
are created verified, so they get emails already.

**Making a fresh account staff.** Staff are members of the `admin` group in
the sign-in service. Locally:

```sh
make confirm EMAIL=anna.test1@example.com ADMIN=1
```

Then sign out and in again, because the group is read from the sign-in
token. Or simply use `staff@demo.cappy.local`.

### Staff two-step sign-in (MFA)

- **Locally it is off.** The local sign-in service has no MFA, so
  `ADMIN_MFA_REQUIRED` is off unless deployed, and the demo staff account
  opens the console with its password alone. Do not try to turn it on
  locally.
- **Deployed, it is required.** Staging and prod refuse to start with it off.
  A staff account without an authenticator app gets 403 `mfa_required` on
  every staff call, and the console shows **Set up two-step sign-in**:
  **Start** gives an "Open in your authenticator app" link and a key; the
  first six-digit code turns it on, and every sign-in then asks for a code
  (`docs/runbook.md`, "Moderation").

## A2. Payments while testing

**Never use a real card, and never put live Stripe keys (`sk_live_…`,
`pk_live_…`) in `.env`.** Locally Cappy only ever uses the fake provider or
Stripe **test mode**.

### The fake provider (the default)

Unless a developer has set Stripe test keys, payments run on the fake
provider (`PAYMENTS_PROVIDER=fake`, `backend/services/payments/payments/provider.py`
`FakeProvider`). No money moves and nothing is sent to Stripe:

- **There is no card form.** When you book, the card counts as "held" at once
  and the app goes straight on.
- The host "capturing", refunds and payouts are recorded, not performed.
- Every owner can be paid. **Set up payouts** on the Earn tab returns you
  straight to Earn.
- The ID check passes at once.

To see which provider is on: open http://localhost:8000/api/payments/config
while signed in (a developer can do it with `curl`). It says `"fake"` or
`"stripe"`. Simpler: if a card form appears when you book, it is Stripe.

### Stripe test mode

A developer sets these in `.env` (never committed) and runs `make up` again:

```sh
COMPOSE_PROFILES=stripe          # also runs the Stripe CLI, which forwards webhooks
PAYMENTS_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...  # docker run --rm stripe/stripe-cli listen --api-key $STRIPE_SECRET_KEY --print-secret
```

With these set, `make up` gives every demo owner a verified Stripe test
payout account (`payments.cli demo-payouts`), so the host's listing can be
booked and paid. The `stripe` container forwards the five webhook events Cappy
uses (`payment_intent.amount_capturable_updated`, `account.updated`,
`charge.dispute.created`, `identity.verification_session.verified`,
`identity.verification_session.requires_input`) to
`http://gateway:8000/api/payments/webhooks/stripe`. Watch them arrive with
`docker compose logs -f stripe`.

**Test cards.** These are Stripe's public test numbers, from
https://docs.stripe.com/testing. For all of them, use any future expiry date
(for example `12/34`), any 3-digit CVC and any postcode.

| What you want to test | Card number | What should happen in Cappy |
|---|---|---|
| A card that works | `4242 4242 4242 4242` | The card is held; the booking moves to "requested" (or "confirmed" for instant book) |
| The bank's check (3D Secure), passed | `4000 0000 0000 3220` | A bank check appears inside the card form; complete it and the card is held |
| The bank's check, always asked | `4000 0027 6000 3184` | The same, for every payment |
| The bank's check, then declined | `4000 0084 0000 1629` | The check appears, then "Payment not authorised"; the booking stays unpaid |
| A plain decline | `4000 0000 0000 0002` | "Payment not authorised" with the reason; you can try another card |
| Insufficient funds | `4000 0000 0000 9995` | Declined with that reason |
| Expired card | `4000 0000 0000 0069` | Declined as expired |
| Wrong CVC | `4000 0000 0000 0127` | Declined for the CVC |

Nothing is charged when the card is held. It is charged when the host
accepts, refunded on a cancel after that, and paid out to the host on
completion. You can see each step in the Stripe test dashboard.

A fresh host in Stripe mode has to finish Stripe's test onboarding from the
Earn tab (**Set up payouts to take bookings**) before anyone can book them.
The ID check opens Stripe Identity's own window in test mode.

## A3. Before you start: tips that save time

- **Two people at once.** Tabs in the same browser follow one account: if you
  sign in as someone else in a second tab, the first tab reloads as that
  person. To be the buyer and the host at the same time, use two separate
  Chrome profiles, or one normal and one Incognito window, or two browsers.
- **Where things are.** On a phone-sized screen there is a bottom dock:
  **Explore**, **Bookings**, **Earn**, **You**. On a desktop the same links
  are in the header, and staff also see **Staff**.
- **The bell** (notifications) is at `/notifications`: on the **You** tab on
  a phone, in the header on a desktop.
- **Emails.** No real emails leave your computer. A developer can show you
  every email sent at http://localhost:4566/_aws/ses (raw JSON).
- **A booking's id** is the last part of its address, `/bookings/<id>`. Staff
  need it to settle disputes.
- Locally, **the hand-over button is available at once**, whatever the booked
  time, and **a booking can start 5 minutes from now** (deployed: 2 hours).
  So every flow, no-shows, disputes and reviews included, can be walked in
  minutes (see [A5](#a5-shortcutting-time-based-steps)).
- **Where Cappy is open.** A profile or listing in a country that is not
  open yet (anything but Germany, Austria and Switzerland) is refused with
  "Cappy is not open in … yet" (`market_not_live`). A listing is priced in
  its owner's country's currency; another currency is refused.

## A4. Test scripts, feature by feature

Each script is a checklist. **Do** the steps, and tick when you see the
**Expect** result. Money amounts in the demo are in euros.

### 1. The welcome screen and sign-up

Use a fresh Incognito window (so the app thinks this is a first visit).

- [ ] Open http://localhost:5173/. **Expect:** the welcome screen, with what
      Cappy is, a language switch, **Create an account**, **I have an
      account**, and links to Privacy, Terms and Help. No listings, prices or
      people.
- [ ] Open http://localhost:5173/listing/l9 signed out. **Expect:** the
      sign-in screen (not the welcome), and after signing in you land on that
      listing.
- [ ] Tap **Create an account**. Enter an invalid email. **Expect:** "Enter
      your email address, like name@example.com."
- [ ] Enter a password of 11 characters. **Expect:** "Use at least 12
      characters…". Twelve characters of anything, spaces too, work.
- [ ] Submit. **Expect:** **Check your email**, and **Send a new code** is
      greyed out with a 30-second countdown.
- [ ] Type a wrong code. **Expect:** a clear "That code is not right" error.
- [ ] Type the right code from `make codes`. **Expect:** signed in, then the
      onboarding screen.
- [ ] Onboarding: leave the 18+ box unticked. **Expect:** you cannot
      continue. Tick it, fill your name and district, and continue.
      **Expect:** the Explore screen.
- [ ] Sign up again with the same email. **Expect:** "There is already an
      account with that email. Sign in instead."
- [ ] On sign-in, **Forgot your password?** with any address. **Expect:** it
      always goes on to the code step, whether or not the address has an
      account.
- [ ] After a first visit, open `/` signed out in the same window.
      **Expect:** the sign-in screen, not the welcome.

### 2. The language switch (EN / DE / FR)

- [ ] On the welcome or sign-in screen, switch to **Deutsch**, then
      **Français**. **Expect:** every text on screen changes at once, with no
      raw English left and no `{name}`-style placeholders showing.
- [ ] Signed in, go to **You** (Profile) → **Language** and switch. **Expect:**
      the same, on every screen you visit (Explore, a listing, Bookings,
      Earn, the booking page, sheets and error messages).
- [ ] Check dates, times and money on a listing in each language: German
      shows `1.234,56 €` style, French `1 234,56 €`.
- [ ] As the demo buyer, set German, then make a booking. **Expect:** the
      bell item and the email (at http://localhost:4566/_aws/ses) are in
      German.
- [ ] Known gap to confirm, not report: a few system decline reasons
      ("The listing was taken down by Cappy", "The listing was removed by its
      owner", "The account was suspended") are shown in English in every
      language (FLOWS.md §23).

### 3. Browse and search

As the demo buyer.

- [ ] Open **Explore**. **Expect:** "Free in the next 24 hours" as a rail and
      on the map, starting from Kreuzberg.
- [ ] Type two letters in search. **Expect:** "Type at least 3 letters to
      search." Type `saw`. **Expect:** matching listings, including the
      plunge saw.
- [ ] Pick a category (for example Workshop & tools). Set hours, district and
      radius. **Expect:** bookable times, never starting sooner than 5
      minutes from now locally (2 hours deployed; see
      [A5](#a5-shortcutting-time-based-steps)).
- [ ] Change the sort (best match, cheapest, soonest, nearest). **Expect:**
      the order changes and `?sort=` in the address changes with it.
- [ ] Switch between the list and the map. Pick another district or city.
- [ ] Ask for something nothing fits (a tiny radius, many hours). **Expect:**
      "No idle capacity fits that", with **Widen to 90 km** and **Allow 3
      weeks**.
- [ ] Distances read in km in German, French and European English.
- [ ] As the demo host, search. **Expect:** your own plunge saw is never
      offered to you.

### 4. A listing

As the demo buyer, open the plunge saw (`/listing/l9`).

- [ ] **Expect:** photos, title, the host card (name, verified shield, track
      record, whether a business or a private person), reviews, house rules,
      the cancellation policy (shown as flexible), and a price with "Total,
      incl. … service fee".
- [ ] Choose a duration, then a day, then a time. **Expect:** the price
      updates; only free starts are offered.
- [ ] The host card's response time. **Expect** it only for an owner with at
      least 3 answered or lapsed requests in 90 days (measured since
      `61b15b8`, H-1). Known gap, not a new bug: for an owner not yet
      measured (the demo owners), the web still prints "Replies in ~null
      min" (FLOWS.md §23).
- [ ] Tap the heart. **Expect:** it fills at once; the listing appears under
      Saved on your profile. Tap again to remove it.
- [ ] **Report** and **Block** are on the page (tested in scripts 18 and 13).
- [ ] As the demo host, open the same listing. **Expect:** "This is your
      listing" and no book button.
- [ ] Open `/listing/does-not-exist`. **Expect:** a "not found" page.

### 5. Booking by request and by instant book

**By request** (every seeded listing is request-only; of the second host's,
only the bandsaw is instant):

- [ ] As the demo buyer, on the plunge saw, pick a time and tap **Request**.
      **Expect:** a confirm sheet with when, how long, where, "You pay",
      "Nadia receives", the cancellation policy, and "Nothing is charged
      yet… has to accept first". The final button reads **Book and pay**.
- [ ] Tap **Book and pay**. **Expect:** "Request sent to …", then the booking
      page. With Stripe, a card form appears first (see script 6).
- [ ] Tap **Book and pay** twice fast, or on a flaky connection. **Expect:**
      one booking, not two.
- [ ] In the host's window, **Expect:** a badge on **Earn**, the request in
      the Earn inbox, a bell item "New request: …", and an email.

**By instant book** (you need a listing with Instant book on). The second
host's *Bandsaw and bench, book instantly* already has it on; or:

- [ ] As the demo host, go to **Earn**, **Edit** the plunge saw, and turn
      **Instant book** on. Save.
- [ ] As the buyer, open it. **Expect:** the button reads **Book** with a
      lightning icon, and the sheet says "Confirmed as soon as your card is
      held."
- [ ] Book it. **Expect:** "Booked", the booking is confirmed at once, and
      the host gets "New booking: … was booked instantly".
- [ ] Turn Instant book off again afterwards.

**Limits:**

- [ ] Leave 3 bookings unpaid (close the sheet before paying, Stripe mode
      only), then try a fourth. **Expect:** refused with a clear message.
- [ ] While another tester books the same time a moment before you:
      **Expect:** "that window was just taken; pick another", and the times
      reload.

### 6. Paying

**Fake provider:** there is no card step. Check that the booking moves on by
itself and the host sees the request.

**Stripe test mode** (see [A2](#a2-payments-while-testing)):

- [ ] Book with `4242 4242 4242 4242`. **Expect:** the card form in the sheet,
      then "Request sent". If the page briefly says "Confirming your
      payment…", it should settle within a minute.
- [ ] Book with `4000 0000 0000 3220`. **Expect:** the bank check appears
      inside the form; complete it; the booking goes through.
- [ ] Book with `4000 0000 0000 0002`. **Expect:** "Payment not authorised"
      with the reason. The booking stays unpaid; you can try `4242…` in the
      same form.
- [ ] Close the sheet halfway. **Expect:** on **Bookings**, under "Next up",
      "Finish paying…"; you can pay from the booking page.
- [ ] Leave an unpaid booking for 30 minutes. **Expect:** it expires, the
      time is free again, and nobody is emailed.

### 7. The host accepting or declining

Use two windows: buyer and host.

- [ ] Host: open the request (Earn inbox, bell or email link). **Expect:** the
      renter's name and renter rating, the time, your share, and "Answer …,
      or the request lapses".
- [ ] Host: **Accept**. **Expect:** "Accepted. … has been told". Buyer:
      "Confirmed" (bell and email). Both now see **Getting in**: the hand-over
      address and instructions.
- [ ] Make a second request. Host: **Decline**, pick a reason chip, **Send
      decline**. **Expect:** buyer sees "Declined" with the reason and "Nothing
      was charged"; buyer gets an email.
- [ ] Double-tap **Accept**. **Expect:** no error page; the second tap is
      refused quietly.
- [ ] A request nobody answers lapses at the earlier of 24 hours or the
      booked start. **Expect:** buyer gets "Expired: … Nothing was charged."
      A late tap on Accept says "this request has lapsed".

### 8. Hand-over photos, start and complete

With an accepted booking of the plunge saw.

- [ ] Both sides see a safety card (meet at the booked address, take check-in
      photos together, keep messages and payments on Cappy).
- [ ] Host: **I have handed it over** (or buyer: **I have collected it**).
      **Expect:** the booking is in progress, and check-in photos are offered.
- [ ] Add 1 to 12 check-in photos with a note. **Expect:** "Uploading 1 of …"
      progress, then the photos with their upload time, visible to both sides.
- [ ] Buyer: **Mark as handed back**. **Expect:** "Handed back and all
      fine?" with **Yes, it is done**, **Add check-out photos first** and
      **Not yet**.
- [ ] Add check-out photos, then **Yes, it is done**. **Expect:** completed.
      Host gets "You have been paid …" (bell, email). Buyer gets "How was …?"
      and the rating sheet opens.
- [ ] The host has no "complete" button: only the buyer (or, after 48 hours,
      the system) completes.

### 9. No-show

A no-show can only be reported on an accepted booking nobody has marked as
handed over, from the booked start until 2 hours after it: the buyer
reporting the host from the start itself, the host reporting the buyer from
30 minutes after the start (the late renter's grace). These windows are not
shortened locally, but the lead time is: book a start about 5 to 10 minutes
from now, have the host accept, and wait for the start
([A5](#a5-shortcutting-time-based-steps)). The host's side needs another 30
minutes of waiting.

- [ ] Before the start: **Expect:** no "did not show up" button.
- [ ] Buyer, after the start, nobody marked the hand-over: **… did not show
      up**, confirm. **Expect:** the sheet says you get everything back and it
      counts against the host. The booking is cancelled with "Reported: … did
      not show up".
- [ ] On another booking, host, from 30 minutes after the start: **… did not
      show up**. **Expect:** the sheet says the renter gets nothing back and
      you are paid.
- [ ] After 2 hours: **Expect:** the button is gone; the buyer's route is
      **Report a problem**.

### 10. Cancel and refund

- [ ] Buyer, on a requested (not yet accepted) booking: **Withdraw from this
      booking**. **Expect:** "The hold on your card is released; nothing is
      charged." The host is told; the time is free again.
- [ ] Buyer, on an accepted booking before its start: **Withdraw from this
      booking**. **Expect:** "You get back …" the full amount (paid policies
      are off, so every cancellation refunds in full). Confirm with **Yes,
      withdraw**.
- [ ] Host, on an accepted booking: **Cancel booking** → **Yes, cancel it**.
      **Expect:** the buyer gets "Cancelled: …" and a full refund.
- [ ] After the start: **Expect:** no cancel button; the buyer sees **Report a
      problem** instead.
- [ ] In Stripe mode, check the refund in the Stripe test dashboard.

### 11. Disputes

Needs an accepted or in-progress booking whose start has passed. Only the
buyer can report a problem, from the booked start until the booking
completes (the buyer confirming it, or the system 48 hours after the end).
Locally, book a start about 5 minutes from now, accept, and wait for it
([A5](#a5-shortcutting-time-based-steps)).

- [ ] Buyer, before the start: **Expect:** no **Report a problem** button.
- [ ] Buyer, after the start: **Report a problem**, write what went wrong,
      **Report the problem**. **Expect:** "Reported. The payment is on hold";
      buyer gets "We received your report: …"; host sees "… reported a
      problem… Your payout is on hold" and gets an email.
- [ ] Copy the booking id from the address bar.
- [ ] Staff: in the console, **Act directly** → **Resolve dispute: pay the
      owner**, paste the booking id. **Expect:** the booking completes; the host
      gets "You have been paid"; the buyer gets "How was …?".
- [ ] On another disputed booking: **Resolve dispute: refund the buyer**.
      **Expect:** the booking is cancelled and refunded in full; the buyer gets
      "Cancelled: …", and the booking page says the full amount "is refunded
      to the card" (the resolution records `refundAmount` since `747ed6b`;
      before, the page said "nothing was charged").
- [ ] Known gap, not a new bug: there is no list of disputed bookings in the
      console yet.
- [ ] A disputed booking never completes by itself.

### 12. Two-way blind reviews

After a completed booking.

- [ ] Buyer: rate the host (on time or late, 1 to 5 stars, tags, an optional
      note). **Expect:** "Thanks. … will see it once they have rated too."
      The review is **not** on the listing yet.
- [ ] Host: **Rate …** the renter (1 to 5 stars). **Expect:** now both
      ratings are published: the review appears on the listing, signed like
      "Ada L.".
- [ ] Try to rate twice. **Expect:** refused.
- [ ] The buyer's **Bookings** badge counts completed bookings not yet rated.
- [ ] Only hosts see renter ratings (as the renter's record on a request).

### 13. Messaging and masking

On a booking of the plunge saw, in **Messages with …**.

- [ ] While the booking is unpaid: **Expect:** no message panel.
- [ ] While it is requested (not yet accepted), buyer sends: `mail me at
      anna@example.com or +49 170 1234567, or see www.example.com`.
      **Expect:** both sides see "contact hidden until accepted" in place of
      the email, phone number and link. Dates and times such as "Tuesday
      18:00" are never hidden.
- [ ] Host accepts. **Expect:** both sides now see the original text.
- [ ] Send "Can I pay you by PayPal or cash?". **Expect:** it is sent, the
      sender sees "Keep payments on Cappy…", and the reader sees a warning.
- [ ] Other side: **Report** on a message, then **Block … too**. **Expect:**
      no more messages or new bookings between you, both ways. The booking
      itself stays. Unblock from Profile → **Blocked people**.
- [ ] Cancel an accepted booking. **Expect:** contact details hide again and
      the conversation becomes read-only.
- [ ] Send 31 messages in a few minutes. **Expect:** the 31st says to wait a
      little.
- [ ] Type a draft, reload the page. **Expect:** the draft is still there.
- [ ] Emails for messages: at most one per conversation every 15 minutes, and
      they carry the title and a link, never the text.
- [ ] Known gap: on a completed booking older than 14 days the app still
      shows the message box, but the server refuses the message (FLOWS.md §23).

### 14. The ID check

Needed once per person when a booking's total is above the ID-check
threshold of the listing owner's market (`markets.json`
`id_check_above`): **€300** in Germany and Austria, CHF 280 in
Switzerland. Every demo owner is German, so €300 here.

- [ ] As the demo buyer, open *LED wall, 4 × 3 m* (Kreuzberg, €26 an hour)
      and book 12 hours or more. **Expect:** the sheet **Check your ID once**,
      explaining a photo of an ID and a selfie, with a consent tick.
- [ ] Try to start without ticking. **Expect:** you cannot.
- [ ] Tick and start. **Fake provider:** it passes at once and the booking
      goes ahead with no second tap. **Stripe mode:** Stripe Identity's test
      window opens; after it, the app waits up to a minute and books.
- [ ] Book another listing above €300. **Expect:** no second ID check.
- [ ] Nobody answers this request (its owner has no sign-in); it lapses.

### 15. Becoming a host and creating a listing (held listings)

Use a **fresh** account (the demo host already has completed jobs, so its
listings are never held). To see a held listing without making one, the
second host's photo studio is already waiting. The threshold is the owner's
market's (`markets.json` `held_listing_above`): €100 an hour in Germany and
Austria, CHF 95 in Switzerland.

- [ ] Go to **Earn** → **List your first thing** (or Profile → **List
      something you own**). Pick a category.
- [ ] Fill in the title, blurb, district, the hand-over address, the rate,
      hours, photos (at most 12; each tile shows its upload progress, and a
      failed one offers **Retry**), rules, instructions
      and free windows. Reload halfway. **Expect:** "Your unsaved changes are
      back", with **Discard**.
- [ ] Publish with a rate of **€100 an hour or less**. **Expect:** "… is live",
      and the listing is found in search by other accounts.
- [ ] Publish another with a rate **above €100 an hour**. **Expect:** "… is
      saved and waiting for a quick check…", and the Earn card says "Waiting
      for a quick check". Other accounts cannot find or open it. **View as a
      guest** still works for you.
- [ ] Staff: in the console under **Waiting for a check**, **Approve**.
      **Expect:** "Approved: it is live now", and other accounts can now find
      it.
- [ ] Manage a listing: **Edit** (mode and category cannot change),
      **Pause** (not offered; waiting requests stay), **Remove** (confirm;
      waiting requests are declined, confirmed bookings stand).
- [ ] Leave a live listing with no free window in the next 7 days (a fresh
      listing whose only window is further out). **Expect:** within about an
      hour (the catalog's hourly job), a bell item and email "No free time
      next week: …" linking to its edit page, at most once a week per
      listing (since `61b15b8`, H-4).

### 16. Payouts and invoices

- [ ] Fresh host, **Earn**. **Expect:** **Set up payouts to take bookings**.
      Fake provider: tapping it brings you straight back. Stripe mode: Stripe's
      test onboarding opens; after it Earn says "Stripe is checking your
      details" until it is done.
- [ ] Complete a booking of one of your listings (scripts 5, 7, 8). **Expect:**
      "You have been paid …" (bell, email), and Earn shows it under earned.
- [ ] **Invoices** on Earn. **Expect:** one invoice for Cappy's fee per
      completed booking. Tapping it opens the invoice in a new tab.

### 17. Notifications and their settings

- [ ] Open the bell. **Expect:** newest first, an unread count, items marked
      read after a moment, **Mark all as read**. Tapping an item opens its
      screen.
- [ ] Switch language, reopen the bell. **Expect:** the items re-render in the
      new language.
- [ ] Profile → **Notifications**: turn off Bookings email. Make a new
      request. **Expect:** the host gets the bell item but no "New request"
      email.
- [ ] With emails off, accept, decline or cancel. **Expect:** those emails
      still arrive: confirmations, declines, cancellations, failed payments
      and disputes are always emailed, because they are records of a contract
      or money.
- [ ] News and offers is off by default.
- [ ] Known gap: the text "Everything also arrives by email." on Profile is out
      of date (FLOWS.md §23).

### 18. Reporting content, signed out and signed in

**Signed in:**

- [ ] On a listing, **Report**. Pick a reason, write fewer than 10 characters.
      **Expect:** you cannot send. Write more, tick the good-faith statement,
      send. **Expect:** a reference, and "We received your report" in the bell
      and by email.
- [ ] Report a person (the host card), a message and a review the same way.

**Signed out:**

- [ ] In an Incognito window, open http://localhost:5173/legal/report.
      **Expect:** the form, asking what you are reporting, its link or
      reference (paste `http://localhost:5173/listing/l9`, or just `l9`), your
      email, and the good-faith statement.
- [ ] Send 4 reports with the same email in one day. **Expect:** the 4th is
      refused.
- [ ] Staff then sees each report in the console queue (script 19).

### 19. The admin console

Sign in as `staff@demo.cappy.local`. Open **Profile** → **Open the staff
console**, or **Staff** in the desktop header, or http://localhost:5173/admin.

- [ ] As the demo buyer, open `/admin`. **Expect:** "Only for Cappy staff".
- [ ] **Reports**: the open queue, oldest first. Open one, **Decide on this
      report**. Try a statement shorter than 20 characters. **Expect:** you
      cannot decide.
- [ ] **Dismiss** with a statement. **Expect:** the reporter is told nothing
      was wrong.
- [ ] On a listing report, **take down**. **Expect:** the listing disappears
      for everyone; pending requests on it are declined with "The listing was
      taken down by Cappy"; the owner gets "We removed your listing" with the
      reasons and how to contest.
- [ ] On a message or review report, **Remove the message / review**.
      **Expect:** the message reads "[removed by Cappy: it broke our rules]"
      for both sides; a review keeps its stars and loses its words.
- [ ] **Suspend** (the owner, the author or the person). **Expect:** their
      listings come down; they cannot list or book; they can still sign in,
      message, and keep accepted bookings.
- [ ] **Waiting for a check**: approve a held listing (script 15).
- [ ] **Act directly**: **Take a listing down** (listing id), **Suspend an
      owner** / **Reinstate an owner** (owner id), and the two **Resolve
      dispute** actions (booking id). A reinstated owner can list and book
      again, but their old listings stay down.
- [ ] **Audit log**: every action above, with who, what and why.

### 20. Data export and account deletion

Use a **fresh** account for deletion.

- [ ] Profile → **Your data** → **Download my data**. **Expect:** a file
      `cappy-my-data.json` with your profile, listings, bookings, messages,
      payments, notifications and settings. No card numbers. Since
      `747ed6b` it also has the ID-check consent (when, which text), links
      to your hand-over photos that work for a day, and staff decisions about
      your messages and reviews.
- [ ] Download 6 times in a day. **Expect:** the 6th is refused: "try again
      tomorrow".
- [ ] With an open booking (requested, accepted, in progress or disputed):
      **Delete account**. **Expect:** refused, saying to finish or cancel open
      bookings, and from which date you can delete.
- [ ] Without open bookings: **Delete account** → **Delete my account**.
      **Expect:** "Your account is deleted", you are signed out, and signing in
      again fails. Your listings are gone; your reviews read "Former member".
- [ ] Signed out, open http://localhost:5173/account/delete. **Expect:** a
      public page explaining how to delete an account.

### 21. Sign out everywhere

- [ ] Sign in as the same fresh account in two browsers.
- [ ] In one: Profile → **Sign out everywhere** → confirm. **Expect:** that
      browser is signed out with "Signed out on every device".
- [ ] The other browser, on its next action. **Deployed**, it is signed out.
      **Locally this may not happen:** the local sign-in service cannot end
      other sessions, so Cappy skips that step and the other browser can
      refresh its sign-in and carry on. Its push devices are still removed.
      Note what you see, but do not report the other browser staying signed in
      as a bug: this is a stated limitation of the local stack (GD-4, not
      fixable on cognito-local, which has no global sign-out).
- [ ] Try it 6 times in an hour. **Expect:** the 6th is refused.
- [ ] Plain **Sign out**. **Expect:** back to sign-in; drafts are cleared.

### 22. Offline

In Chrome: DevTools (F12 or Cmd+Option+I) → **Network** tab → throttling
menu → **Offline**.

- [ ] **Expect:** a bar: "You are offline. What you see may be out of date;
      paying, booking and sending wait until you are back."
- [ ] What was on screen stays readable. Every button that moves money or
      sends something is greyed out: book, pay, accept, decline, hand-over,
      complete, cancel, dispute, no-show, send, rate and block.
- [ ] Open a screen you have not visited. **Expect:** "Cannot reach Cappy.
      Check your connection and try again."
- [ ] Reload while offline. **Expect:** the app opens as the last signed-in
      person with the offline bar.
- [ ] Go back online. **Expect:** the bar goes and everything works again.

### 23. The phone layout

See [A7](#a7-testing-the-app-version) for how to set it up. Then walk through
scripts 1 to 22 again at 390 × 844 and check:

- [ ] The bottom dock (**Explore**, **Bookings**, **Earn**, **You**) with
      badges, and nothing hidden behind it.
- [ ] On a listing, the price and button sit in a bottom bar.
- [ ] Sheets open from the bottom and can be closed.
- [ ] No sideways scrolling on any screen, in all three languages (German
      words are long).
- [ ] Text and buttons are big enough to tap.

## A5. Shortcutting time-based steps

Some steps depend on the clock. Locally a few are shortened; for the rest a
developer can change a setting.

**Already shortened locally** (`compose.yaml`):

- `MIN_LEAD_MINUTES: "5"` (the `matching` service, since `61b15b8`, GD-3): a
  booking can start 5 minutes from now (deployed: 120 minutes). This is what
  makes no-shows, disputes and reviews walkable in minutes.
- `START_EARLY_MINUTES: "100000"` (`booking`): the hand-over can be marked
  straight away for any booking starting in the next ~69 days (deployed: 30
  minutes before the start). So you can walk a booking from request to
  payout in minutes: request, accept, **I have handed it over**, **Mark as
  handed back**.
- `SWEEP_SECONDS: "5"` (`booking`): expiries and auto-completions are applied
  within seconds of being due (deployed: 30 seconds).

These shortcuts never reach real people: deployed (staging, prod) a service
refuses to start with `MIN_LEAD_MINUTES` under 60, `START_EARLY_MINUTES`
above 60 or `AUTO_COMPLETE_AFTER_HOURS` under 24 (`unsafe_reasons` in
`matching/settings.py` and `booking/settings.py`).

**Not shortened** (so the time must really pass, or a developer changes the
setting):

| Step | Rule | Setting (service) |
|---|---|---|
| Unpaid booking expires | 30 min | `PAYMENT_TIMEOUT_MINUTES` (booking) |
| Host must answer | 24 h, never past the start | `ANSWER_WITHIN_HOURS` (booking) |
| Auto-complete | 48 h after the end | `AUTO_COMPLETE_AFTER_HOURS` (booking) |
| No-show | from the start (the buyer reporting the host) or start + 30 min (the host reporting the buyer), until start + 2 h; only if nobody marked the hand-over | fixed in code (`booking/routes.py` `NO_SHOW_GRACE`, `NO_SHOW_REPORTABLE`) |
| Dispute | the buyer, from the start until the booking completes | fixed in code (`booking/routes.py`) |
| Review window | 14 days after the end | fixed in code |
| Weekly schedule roll-on and the "no free time next week" notice | hourly | fixed in code (`catalog/jobs.py`) |

**Testing no-shows and disputes.** You need an accepted booking whose start
has passed:

1. As the buyer, book a start about 5 to 10 minutes from now (the plunge
   saw, or one of the second host's listings); the host accepts.
2. Wait until the start. For the next 2 hours you can test no-shows (do not
   mark the hand-over; the host's report opens 30 minutes after the start)
   and disputes.

To change any other setting, add it under the service's `environment:` in
`compose.yaml`, then run `docker compose up -d <service>`. Take it out again
afterwards and do not commit it.

## A6. Resetting the local data

- `make down` stops everything and **keeps** your data.
- `make up` starts it again. It also re-adds any missing demo data, but never
  removes or resets what is there.
- To start from a clean slate (all accounts, bookings and listings you made
  are deleted, and the demo world is loaded fresh):
  ```sh
  make clean
  make up
  ```
  Then restart the web app (`cd web && npm run dev`), because `make up` writes
  a new sign-in setting for it. Clear the site's data in the browser too
  (DevTools → **Application** → **Storage** → **Clear site data**), or you may
  see a stale session.

Reset after anything that breaks the demo for others: deleting or suspending
a demo account, taking down the host's listing, or filling the host's
calendar.

## A7. Testing the app version

The store apps are the same app inside a native shell, so nearly everything
can be tested in a desktop browser at phone size.

### The phone layout in a desktop browser

1. In Chrome, open http://localhost:5173 and DevTools (F12 or Cmd+Option+I).
2. Click the **device toolbar** icon (or Cmd+Shift+M / Ctrl+Shift+M).
3. Choose **Dimensions: Responsive** and type **390 × 844** (an iPhone
   12 to 15 size).
4. Reload. Test in English, German and French.

### What needs a real device (a developer build)

| Thing | Why a browser is not enough |
|---|---|
| Push notifications | They need Apple's or Google's push service and the store app. Locally, pushes are only logged. |
| The camera for photos | The browser shows a file picker; the app can open the camera directly. |
| Deep links | Opening `/listing/…`, `/bookings/…`, `/earn…` or `/pay/…` links in the app needs the real domain and signed apps. |
| The 3D Secure return | A bank that leaves the app returns through the `/pay/return` link, which only opens the app on a real domain. In the browser the check stays inside the card form. |
| The Android back button, text size (Dynamic Type), share sheet for the data export and invoices | Native behaviour only. |
| Forced update ("Update Cappy") | Shown only to store builds older than the minimum version. |

### How a developer builds the shells

From `web/README.md` and `web/capacitor.config.ts` (app id `app.cappy`):

```sh
cd web
VITE_API_URL=https://<domain>/api npm run build   # a shell has no same-origin /api
npx cap sync                                      # copies dist/ and the plugins into ios/ and android/
npx cap open ios                                  # Xcode 16+
npx cap open android                              # Android Studio, SDK 36
```

### Known not to be testable here

- **A store shell against the local stack is not set up.** The shells need a
  reachable API; the local gateway and sign-in service only listen on
  `127.0.0.1`, serve plain `http`, allow no cross-origin callers (CORS is off
  unless `CORS_ORIGINS` is set), and the web build points sign-in at
  `http://localhost:9229`. None of these is configured for a device.
- **A phone's browser on your Wi-Fi** can load `npm run dev` (it listens on
  the network), but sign-in will fail, because the app looks for the sign-in
  service at the phone's own `localhost`. The service worker also needs HTTPS.
- **Real push, deep links and the `/pay/return` hand-back** need a deployed
  HTTPS domain, signing keys and store accounts. There is no deployed
  environment yet (GOAL 12).
- Test those on a device only once an environment exists. Until then, the
  phone layout in the browser is the app check.

## A8. Reporting a bug

Include:

1. **What you did**, step by step, from a known start (for example "signed in
   as demo buyer, opened the plunge saw, picked tomorrow 10:00, 2 hours,
   tapped Request").
2. **What you expected** (the "Expect" line from the script) and **what
   happened**.
3. **Which account**: the demo role, or the fresh account's email.
4. **Which screen**: the address in the address bar (for example
   `/bookings/01J…`).
5. **Web or phone layout**, the browser, and the language (EN, DE, FR).
6. **When**: the date and time, to the minute. Developers find the logs by
   time.
7. **The reference in the error message.** When something fails on Cappy's
   side, the message says "Something went wrong on our side. Try again; if it
   keeps happening, tell us reference …". Copy that reference exactly: it is
   the request id, and it finds the exact log lines.
8. **Payments mode** (fake or Stripe) and, in Stripe mode, the test card
   used.
9. A screenshot or screen recording.

Before reporting, check FLOWS.md §23 ("Known gaps"): those are already known.

---

# Part B: developing

## B1. Prerequisites

| Tool | Version | Where it is pinned |
|---|---|---|
| Docker (with Compose v2) | recent | `compose.yaml` |
| uv | recent | CI uses `astral-sh/setup-uv@v6` |
| Python | 3.12 (uv installs it) | `backend/.python-version`, `requires-python >=3.12` |
| Node | 22 | CI `node-version: 22` |
| Terraform | 1.12.2 (roots need `>= 1.10`) | CI; only for `infra-*` targets |
| LocalStack Pro auth token | | `.env` (compose refuses to start without it) |
| Stripe test keys, optional | `sk_test_…`, `pk_test_…`, `whsec_…` | `.env` |
| Xcode 16+ / Android Studio (SDK 36), optional | | only for the store shells |

The LocalStack licence in use covers S3, SNS, SQS and SES v1 only (ADR 0009).

## B2. One-time setup

```sh
cp .env.example .env              # fill LOCALSTACK_AUTH_TOKEN; Stripe test keys optional
cd backend && uv sync --all-packages && cd ..
cd web && npm install && cd ..
make up                           # builds, migrates, seeds; writes web/.env.development.local
```

`make up` prints the API and the demo accounts when it is done.

## B3. Architecture in brief

```
browser ─► Vite dev server :5173 ─► /api, /media ─► gateway :8000 ─► catalog, matching, booking, payments
   └─► cognito-local :9229 (sign-in)                                     │ outbox → SNS → SQS per consumer
                                                                        └─► catalog, booking, payments, notifications → SES
```

- **Services** (`backend/services/`): `gateway` (allow-list router, admission
  control), `catalog` (profiles, listings, photos, search, reviews, saved,
  reports and moderation, export and deletion), `matching` (stateless
  ranking and pricing), `booking` (lifecycle, messages, evidence, blocks),
  `payments` (Stripe Connect, ID check, invoices), `notifications` (email,
  push, the bell, settings). Shared code is `backend/libs/cappy_common`.
- **One Postgres database per service** (ADR 0001). No double booking: a
  Postgres exclusion constraint (ADR 0004).
- **Identity**: Cognito; every service verifies the JWT itself, no trusted
  headers (ADR 0002).
- **Events**: transactional outbox → SNS topic `cappy-events` → one SQS queue
  per consumer, each with a DLQ; handlers are idempotent (ADR 0003).
- **Local stand-ins** (ADR 0009): `postgres:16-alpine` for Aurora; LocalStack
  for S3, SNS, SQS, SES; `jagregory/cognito-local` for Cognito; the fake
  provider or Stripe test mode for Stripe; `stripe-mock` for contract tests.
- **Web**: React 19 + Vite + TanStack Query in `web/`. `src/domain` is pure,
  `src/data/repo.ts` is the only module that talks to the API, `src/app` has
  the screens.
- Deeper: `docs/adr/`, `docs/INFRA.md`, `docs/DATA.md`, `docs/FLOWS.md`,
  `docs/FEATURES.md`.

## B4. make targets

`make` (or `make help`) lists them. All from the `Makefile`:

| Target | What it does | Needs |
|---|---|---|
| `up` | Build and start the stack, wait for health, copy `.local/web.env` to `web/.env.development.local`, then `seed-demo` | `.env` |
| `down` | Stop the stack, keep data | |
| `clean` | Stop it, delete volumes and `.local/*.env` | |
| `logs` | Follow the six services' logs | stack |
| `seed-demo` | Load the demo world (additive; local and staging only), the demo buyer, second host and staff profiles and the second host's three listings (`local/demo_profiles.py`, through the API; skipped once it owns anything), and in Stripe mode verified test payout accounts for demo owners | stack |
| `codes` | The last 20 sign-up and reset codes from cognito-local's log, each with the email it went to | stack |
| `confirm` | `make confirm EMAIL=… [ADMIN=1]`: mark a local account's email verified (so Cappy emails it), confirm it if the code was never typed, and with `ADMIN=1` add it to the `admin` group (`local/confirm.py`) | stack |
| `test` | `ruff check`, `ruff format --check`, `pytest -q` | nothing |
| `test-pg` | `pytest` including the Postgres tests, against the compose Postgres on 5433 | `make up` |
| `test-stripe` | Start `stripe-mock` on 12111 and run the `stripe_mock` tests | Docker |
| `e2e` | The whole journey against the running stack (`local/e2e.py`) | `make up` |
| `web` | `npm ci && npm run build` in `web/` | Node |
| `infra-validate` | `terraform fmt -check` and `validate` in every root | Terraform |
| `infra-local` | Apply `infra/localstack` (the event fabric) to LocalStack and prove its routing | `make up`, Terraform |
| `openapi` | Regenerate `docs/api/*.json` from the services' code | |
| `load` | 50 users for 60 s: no 5xx, one winner per contested window | `make up` |
| `load-spike` | 10× arrival rate for 60 s; shedding may answer 503 | `make up` |
| `load-mixed` | Open model: 90 % browse, 8 % signed-in, contested bookings, 120 s | `make up` |
| `load-soak` | An hour at a steady rate; connections, memory and queue ages stay flat | `make up` |

Everything runs from the root `Makefile` and `compose.yaml`; there is no
second stack under `backend/`.

## B5. Ports and URLs

All bound to `127.0.0.1`. The services themselves are reachable only inside
the compose network, as in AWS.

| URL | What |
|---|---|
| http://localhost:5173 | The web app (Vite dev server; proxies `/api` and `/media` to the gateway) |
| http://localhost:8000/api | The API, through the gateway |
| http://localhost:8000/healthz, `/readyz` | Gateway liveness and readiness |
| http://localhost:8000/docs, `/openapi.json` | The gateway's own OpenAPI page. The services' API reference is `docs/api/*.json` (`make openapi`) |
| http://localhost:9229 | cognito-local (the browser signs in against it) |
| http://localhost:4566 | LocalStack |
| http://localhost:4566/_aws/ses | Every email "sent" (JSON), as `local/e2e.py` reads them |
| `localhost:5433` | Postgres, user `cappy`, password `cappy`, one database per service (`catalog`, `booking`, `payments`, `notifications`) |
| `localhost:12111` | stripe-mock, only during `make test-stripe` |

## B6. Env files and secrets

| File | Tracked? | What |
|---|---|---|
| `.env.example` | yes | The template: `LOCALSTACK_AUTH_TOKEN`, and the optional Stripe test-mode lines |
| `.env` | **no** | Your copy with the real values. Compose reads it. **Secrets live only here** |
| `.local/local.env` | no | Written by `local/bootstrap.py`: pool id, client id, issuer, queue URLs, the demo owner map. Loaded by `local/run.sh` into each service |
| `.local/web.env` → `web/.env.development.local` | no | The Cognito endpoint and client id, and `VITE_DEMO_ACCOUNTS`, for the Vite dev server |
| `web/.env.example` | yes | `VITE_API_URL` (leave unset locally) |
| `compose.yaml` | yes | Every non-secret local setting. `INTERNAL_TOKEN: local-only-internal-token-not-a-secret` and the LocalStack `test` credentials are deliberately fake |

Rules (CLAUDE.md): the LocalStack token, Stripe keys and anything else secret
never enter the repository. Only **test** Stripe keys go in `.env`; live keys
exist only in AWS Secrets Manager, set by hand (`docs/runbook.md`, step 4).
Deployed, services refuse to start with unsafe settings
(`cappy_common/settings.py` `unsafe_reasons`).

## B7. Running services, logs and the web dev server

**Each service runs as a container** under compose, started by `local/run.sh`
(load `.local/local.env`, run its migrations, start uvicorn on
`<service>.main:create`).

```sh
docker compose ps                              # what is running
docker compose up -d --build booking           # rebuild and restart one service after a change
docker compose logs -f booking                 # one service's logs
make logs                                      # all six services
docker compose exec booking sh                 # a shell inside it
docker compose exec postgres psql -U cappy -d booking   # its database
```

Changing a setting locally: add it under the service's `environment:` in
`compose.yaml` (for example `ACCEPTING_BOOKINGS: "false"` on `booking`), then
`docker compose up -d booking`. Do not commit test values.

**Without Docker** a service starts on SQLite with default settings, which is
enough for a quick look at its routes but not for real work (some background
jobs log SQLite errors):

```sh
cd backend && uv run --package cappy-catalog uvicorn --factory catalog.main:create --port 8001
```

**Logs.** Locally they are plain text (`LOG_JSON=false`):
`time LEVEL logger [requestId] message`. Deployed they are JSON lines with
`requestId`.

**The web dev server:**

```sh
cd web
npm run dev          # http://localhost:5173 (also on your LAN, --host)
npm run build        # tsc -b && vite build → dist/
npm run preview      # serve dist/ with the same proxy
npx tsc --noEmit -p .  # type-check only, as CI does
```

`VITE_API_PROXY` changes where `/api` is proxied (default
`http://localhost:8000`). After `make clean && make up`, restart the dev
server: the Cognito client id changes.

## B8. Tests

| Command | What it proves | Needs |
|---|---|---|
| `make test` | Lint, format and every unit and API test (SQLite, in-memory bus, a throwaway JWKS). Includes the subscription consistency test (D-13) and the privacy register test (D-11) | nothing |
| `make test-pg` | Also the Postgres tests: migrations build exactly the models, concurrency, the no-double-booking constraint | `make up` |
| `make test-stripe` | The Stripe calls against stripe-mock | Docker |
| `make e2e` | Sign up, list with a photo, search, book, pay, accept, hand over, complete, pay out, rate, review, emails, plus the edge refusing what it must. In Stripe mode it needs `sk_test_` keys and confirms with Stripe's test card | `make up` |
| `make load`, `load-spike`, `load-mixed`, `load-soak` | Concurrency: no errors, no double booking, latency percentiles. A laptop finds errors, not capacity numbers | `make up` |
| `make infra-validate`, `make infra-local` | Terraform validates; the event fabric applied to LocalStack routes each event type correctly | Terraform (`infra-local` also `make up`) |

Web checks (`cd web`; CI runs all five after `npm ci --ignore-scripts`,
`npx tsc --noEmit -p .` and `npm run build`):

| Script | What it checks |
|---|---|
| `npm run check:i18n` | Every German and French text keeps its English key's `{placeholders}`; French and German have the same keys; every literal `t('…')` in the app has a German (and so French) entry |
| `npm run check:flags` | The rollout bucket matches the server's |
| `npm run check:size` | The first-paint JavaScript is under 170 kB gzipped (run after a build) |
| `npm run check:a11y` | Every `<img>` has `alt`; nothing clickable is smaller than 24 × 24 px |
| `npm run check:attempt` | Idempotency keys: a retry after an unknown outcome reuses the key, a known outcome or changed body gets a new one |

A single backend test: `cd backend && uv run pytest -q services/booking -k no_show`.

Before a commit (the rule in PLAN.md): `make test` and every web `check:*`
green, chained with `&&`.

## B9. Adding a feature

Rules from `CLAUDE.md`: work on `prod-readiness`, commit as the repo's
identity, **never push** unless told, every commit leaves `make test` green,
new behaviour comes with tests, nothing demo-only runs in a service process
(ADR 0010).

Checklist:

1. **Tests first or alongside.** API tests run on SQLite in `make test`.
   Anything that depends on Postgres behaviour goes in a
   `test_<service>_postgres.py` (run by `make test-pg`). Extend `local/e2e.py`
   when a journey changes.
2. **Living docs in the same commit.** Update whichever of
   `docs/FEATURES.md`, `docs/FLOWS.md`, `docs/INFRA.md` and `docs/DATA.md` the
   change makes untrue, and this guide if a tester-visible step changes.
   Changing a decision needs a new ADR, not an edit.
3. **Migrations.** Alembic per service, in
   `<service>/migrations/versions/`, numbered (`0015_currency_upper.py` is the
   latest in booking, `0017_weekly_schedule.py` in catalog). Expand and contract: new code must work with the schema
   before and after the migration. `make test-pg` fails if migrations and
   models drift.
4. **Events and subscriptions (D-13).** Event types are in
   `cappy_common/events.py`. A new consumer needs the type in the handler map
   of the consuming service **and** in all four subscription lists:
   `infra/platform/data.tf`, `local/bootstrap.py` (`CONSUMERS`),
   `infra/localstack/main.tf` and `infra/localstack/check.py`.
   `backend/libs/cappy_common/tests/test_subscriptions.py` fails otherwise.
   Handlers must be idempotent. On an existing stack, `make up` re-runs the
   bootstrap, which updates each subscription's filter.
5. **The privacy register (D-11).** A new table with a person's id goes into
   `cappy_common/privacy.py`: whether deletion deletes, redacts or keeps it,
   and whether the export includes it, with a reason. `tests/test_privacy.py`
   fails otherwise. Retention periods: `docs/retention.md`.
6. **Three languages.** App texts: English is the key (`t('Book and pay')`),
   with entries in `web/src/i18n.de.ts` and `web/src/i18n.fr.ts`
   (`check:i18n` enforces it). Server error messages are English and are
   translated in the app through the same catalogues, so add those too.
   Emails and pushes: `notifications/texts.py` (EN, DE, FR). Never call `t()`
   at module level. Format money, dates and distances with the helpers in
   `web/src/domain/money.ts` and `web/src/app/format.ts`, never by hand.
7. **Idempotency keys.** A POST that creates something takes an
   `Idempotency-Key` (`cappy_common/idempotency.py`: same key, same answer;
   same key, other body, 422). On the web, use `web/src/domain/attempt.ts`
   (`check:attempt`).
8. **Feature flags and kill switches.** Roll out with `FEATURE_FLAGS`
   (`cappy_common/flags.py`, `web/src/domain/flags.ts`; the apps read them from
   `/api/app-config`). Kill switches are settings: `ACCEPTING_BOOKINGS`,
   `PAYOUTS_ON`, `ACCEPTING_LISTINGS` (`docs/runbook.md`, "Kill switches").
   A new provider or unsafe option adds its own `unsafe_reasons` check.
   **Markets** are configuration, not code (since `747ed6b`, M-2):
   `cappy_common/markets.json` gives each country its cell, currency,
   languages, units, minimum age, emergency number and money thresholds (ID
   check, held listing, price cap) in its own minor units, read through
   `cappy_common/markets.py` (`market`, `live_market`). Opening a country is
   setting its `status` to `live`; `tests/test_markets.py` checks the file.
9. **Signed-in only** (GOAL 13): nothing of the product is reachable before
   sign-in, on the server too. New public routes need a reason (law or the
   stores).
10. Run `make test`, the web checks, and, when the stack is involved,
    `make test-pg` and `make e2e`.

## B10. Swapping a provider

`docs/FEATURES.md` lists every provider (Cognito, Stripe, Stripe Identity,
SES, SNS Mobile Push, S3 and CloudFront, …), its seam, and what a swap takes
(its "Summary" and "Cross-cutting seams"). In short: a provider is chosen by
settings; the replacement plugs into the named interface (for example
`payments/provider.py` `Provider`, `payments/identity.py`
`IdentityProvider`, the `Mailer`); it needs its own `unsafe_reasons` checks,
a local fake or emulator (ADR 0009), and a DPA and privacy-policy entry.

## B11. Debugging recipes

**Find a request by its id.** Every response carries `x-request-id`; the app
shows it in "tell us reference …" errors, and it is in every log line.

```sh
docker compose logs --no-color | grep <request-id>
```

**Sign-up codes:** `make codes` prints each code with the email it went to.

**cognito-local helpers:** `make confirm EMAIL=anna.test1@example.com` lets
Cappy email the account (cognito-local does not verify on confirmation) and
confirms it if the code was never typed; add `ADMIN=1` to make it staff
(then sign out and in again). The script is `local/confirm.py`: it reads the
pool id from `.local/local.env` and talks to cognito-local on `:9229`, so it
works on the local stack only.

**cognito-local quirks** (INFRA.md §7, ADR 0009):

- needs `tty: true`, or its log (with the codes) is buffered;
- issues tokens with `iss=http://0.0.0.0:9229/<pool>`, which is why the
  issuer and the JWKS URL are separate settings;
- does not set `email_verified` on confirmation (so fresh accounts get no
  email until `make confirm`; see above);
- answers 500 on `GlobalSignOut`, and cannot sign a user out everywhere, so
  notifications skips that step locally (`notifications/mail.py`);
- has no MFA, so `ADMIN_MFA_REQUIRED` is off locally.

**Queues and dead letters.** Each consumer has `cappy-<service>` and
`cappy-<service>-dlq` in LocalStack. A message lands in the DLQ after 12
failed receives (visibility 120 s). See the depths:

```sh
cd backend && uv run python - <<'EOF'
import boto3
sqs = boto3.client("sqs", region_name="eu-central-1", endpoint_url="http://localhost:4566",
                   aws_access_key_id="test", aws_secret_access_key="test")
for s in ["catalog", "booking", "payments", "notifications"]:
    for q in (f"cappy-{s}", f"cappy-{s}-dlq"):
        url = sqs.get_queue_url(QueueName=q)["QueueUrl"]
        print(q, sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])
              ["Attributes"]["ApproximateNumberOfMessages"])
EOF
```

To read a dead letter, `receive_message` on the DLQ URL. To redrive after
fixing the cause, do what the runbook does in AWS,
`start_message_move_task(SourceArn=<dlq arn>)`, or receive each message and
send its body back to the main queue. Handlers are idempotent, so redriving
is safe. (Whether LocalStack supports the move task has not been checked.)

An event that could not be **published** stays in the service's `outbox`
table; the runbook's `outbox-set-aside` entry has the SQL to resend it.

**LocalStack limits.** The licence covers S3, SNS, SQS and SES v1 only: no
Cognito (hence cognito-local), ECS, RDS, ELB, CloudFront, WAF, ECR or SES v2.
Only the messaging Terraform is applied to it (`make infra-local`). It must
run with `SQS_ENDPOINT_STRATEGY=off`.

**Payments.** `GET /api/payments/config` shows the provider. In Stripe mode,
`docker compose logs -f stripe` shows each forwarded webhook and its answer.
A booking stuck in `awaiting_payment` usually means the webhook never arrived;
the reconciliation loop catches intents still `created` after 10 minutes.

**Never real AWS.** Nothing in this repository is to be applied to a real
AWS account or any real cloud (GOAL 12). Terraform for staging and prod is
only validated (`make infra-validate`); LocalStack is the only apply. The
first real apply is the owner's decision.

## B12. Where to look

| Question | File |
|---|---|
| What the project must achieve | `docs/GOAL.md` |
| What to do next | `docs/PLAN.md` ("Resume here"), `docs/TASKS.md` |
| Why it is built this way | `docs/adr/` (0001 to 0013) |
| How each flow behaves, and known gaps | `docs/FLOWS.md` (§0 has every number; §23 the gaps) |
| What exists and its provider seams | `docs/FEATURES.md` |
| AWS resources, local stack, kill switches | `docs/INFRA.md` |
| Tables, events, personal data | `docs/DATA.md` |
| Deploying and operating | `docs/runbook.md`, `docs/slo.md`, `docs/resilience.md` |
| Store review notes | `docs/app-review.md` |
| The API | `docs/api/*.json` |
| The demo world | `backend/libs/cappy_common/cappy_common/fixtures/seed.json` (generated; do not edit by hand); the demo accounts in `local/bootstrap.py` (`DEMO`), their profiles and the second host's listings in `local/demo_profiles.py` |
| Markets (which countries are open, currency, thresholds) | `backend/libs/cappy_common/cappy_common/markets.json` |
| How results are ranked | `GET /api/ranking` (the ranker's own weights, `matching/domain/match.py` `W`, `SIGNALS`) |

---

## How to keep this file true

This guide describes what a tester and a developer do **today**. Any change
that alters a step here updates this file in the same commit: a new or
renamed screen, button or label; a new make target, port, setting or
account; a change to the demo world, the payment modes or a time rule; a
known gap fixed or found. Take every value from the code (and name the file
when it helps), not from another doc. The step-by-step flows behind each test
script are in `docs/FLOWS.md`; when a flow there changes, check its script
here.

Proposed line for the "Living docs — keep them true" list in `CLAUDE.md`:

```markdown
- **[`docs/GUIDE.md`](docs/GUIDE.md)**: how to run Cappy locally and test every feature by hand (testers), and how to set up, run, debug and test it (developers): accounts, payments modes, click paths, commands.
```
