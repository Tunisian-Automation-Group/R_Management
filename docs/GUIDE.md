# Cappy guide: testing and developing locally

Cappy is a members-only marketplace where people and firms rent out idle
machines, rooms, vehicles and storage by the hour. It ships as a web app (an
installable PWA) and as iOS and Android apps, which are Capacitor shells
around the same build (ADR 0012). Markets are all of Europe, the US and
Canada (GOAL 16, ADR 0013); each country is a market in
`backend/libs/cappy_common/cappy_common/markets.json`, and only Germany,
Austria and Switzerland are open (`live`) today. The demo data is set in
Berlin, with one listing in Wien and one in Zürich (in francs), and 29
listings in Amsterdam, Paris, Lyon, Milan, Brescia and Lisbon that are
**hidden**, because those countries are not open yet (script 28).

This guide has two parts:

- **Part A** is for testers and other non-developers: product people, QA and
  the owner. You get a running local environment and test every feature by
  hand.
- **Part B** is for developers: setup, architecture, running, debugging,
  tests and conventions.

Everything here runs on one computer. **Nothing is ever run against real AWS
or any real cloud account** (GOAL 12). No staging or production environment
exists yet: the Terraform for them is only validated, never applied.

Last synced with the code as of `1cb2d67` (`090c890`, `6c2f2ec`, `73610c4`
and `1cb2d67`, the fixes from verification round 7; the sync before, at
`9107ad2`, covered `e2e77ab` to `9107ad2` and the guide items V6-25 to V6-27).

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
| Host (owner) | `host@demo.cappy.local` | `Demo-pass-123!` | The seeded owner "Nadia Brandt" (Kreuzberg). Owns **one** demo listing: *Festool TS 55 plunge saw + 1.4 m rail* (`l9`, Tempelhof, €4 an hour, 2 to 8 hours, by request, hand-over address "Tempelhofer Damm 22, 12099 Berlin" since `42c777c`), with its seeded reviews and record. Since `22b5e0f` it is open **every day, 08:00 to 22:00** (Berlin time, a weekly schedule `make up` gives it), and since `1cb2d67` (V7-11) that holds on every day of a clean stack: `make up` first deletes the seed's own dated windows on it (`w8` to `w12`, which closed Sunday mornings and cut some weekdays to 17:00-21:00), so on any day, weekends too, a start 5 minutes ahead can be booked between 08:00 and 22:00. Use it to accept or decline requests, hand over, get paid and see invoices. |
| Second host (new owner) | `host2@demo.cappy.local` | `Demo-pass-123!` | "Demo Host Two" (Neukölln, Germany, euros), with no completed jobs, so it behaves like a brand-new owner. Owns the three listings below. Use it for instant book, weekly opening hours, a batch (van) listing and the staff approval of a held listing (since `61b15b8`, GD-5). |
| Renter (buyer) | `buyer@demo.cappy.local` | `Demo-pass-123!` | "Demo Buyer", Germany, home district **Kreuzberg** (where Explore starts). Use it to browse, book, pay, message, cancel, dispute and review. It can make 10 booking requests a day (script 29). |
| Staff (moderator) | `staff@demo.cappy.local` | `Demo-pass-123!` | "Cappy Staff", in the `admin` group only (a **support** member: refunds up to €250 alone). Opens the staff console at `/admin`: cases, refunds waiting for approval, reports, held listings, direct actions, the audit log. |

The second host's listings are made through the API by
`local/demo_profiles.py`, the way a new owner would make them (all in
Neukölln, hand-over address "Weserstraße 1, 12047 Berlin"):

| Listing | Price | Opening hours (weekly schedule, Berlin time) | What it is for |
|---|---|---|---|
| *Bandsaw and bench, book instantly* (workshop) | €15 an hour, 1 to 8 hours | **Every day, 08:00 to 22:00** (since `22b5e0f`; Monday to Friday before) | **Instant book**: a booking is confirmed as soon as the card is held, with no host step (scripts 5, 27) |
| *Van run, Neukölln to Leipzig on Saturdays* (freight, booked by quantity) | €25 an hour plus a €20 loading fee | Saturday and Sunday, 10:00 to 16:00 | A batch listing (pallet spaces), booked by request; at most 2 pallets a booking on a stack made since `22b5e0f` |
| *Photo studio with daylight wall (waits for review)* (creator) | €160 an hour, 2 to 10 hours | Monday to Friday, 09:00 to 18:00 | **Held for a staff check**: a new owner above €100 an hour. It waits under **Waiting for a check** in the console until staff approve it (scripts 15, 19) |

Their free windows come from the weekly schedule: the server keeps eight
weeks of windows open and rolls them on hourly, so these listings never run
out of time to book. The web's listing form has a weekly editor (**Set my
own weekly hours**, since `2257182`; script 15), so a tester can add opening
hours to any listing they own. `make up` on an existing stack also moves the
plunge saw and the bandsaw to every day, 08:00 to 22:00, if they are not
already, and (since `1cb2d67`) deletes any seeded dated windows left on
them, so the schedule decides every day ("demo: … is open every day,
08:00-22:00" in its output). Removing a window you added by hand brings the
weekly hours it covered back at once (since `1cb2d67`); removing one the
schedule made closes that time until the hourly roll refills it.

**The studio starts held after every clean rebuild** (`make clean`, then
`make up`): `local/demo_profiles.py` creates it through the API as a new
owner would, and the server holds it (above €100 an hour, no completed
jobs). Its weekly schedule is saved and its windows are made at once, but
nobody except host2 can see or book it. It goes live, with its weekly hours
bookable, **only once a tester approves it** as staff (script 19). After
that it stays approved until the next clean rebuild: `make up` on an
existing stack never makes host2's listings again (they are made only while
host2 owns nothing). So on a stack someone has already used, the studio may
already be live; check the console's **Waiting for a check** first.

The buyer, second host and staff profiles are made by
`local/demo_profiles.py`, so they skip onboarding. The demo buyer's home is
Kreuzberg and stays so: since `32338dd` `make e2e` uses a second buyer of its
own (`rival-<run>@example.com`, deleted at the end) and never signs in as the
demo buyer, which it used to move to Mitte. On a stack where an older `make
e2e` ran, the demo buyer may still be in Mitte: set Kreuzberg under
Profile → **Edit profile**, or reset ([A6](#a6-resetting-the-local-data)).

The demo world also has 71 other owners and 79 listings (among them an
Austrian owner's drill set in Wien, in euros, and a Swiss owner's track saw in
Zürich, in francs, since `7444e37`), but **those owners have no sign-in**.
Since `1cb2d67` (V7-29) Germany also has places outside Berlin, with no
listings yet: Altona (Hamburg), Maxvorstadt (München), Ehrenfeld (Köln),
Bockenheim (Frankfurt am Main) and Plagwitz (Leipzig); onboarding, Profile
and the listing form offer them as "Altona (Hamburg)" and so on.
You can book their visible listings, and nobody will ever answer, so a request
to them simply lapses. 29 of them are hidden (script 28). For anything that
needs the other side to act, book the host's plunge saw or one of the second
host's listings.

Be aware:

- **Local only.** These accounts are created by the local bootstrap and
  nowhere else. They are never created in staging or prod (ADR 0010: nothing
  demo-only runs in a service process, and the seeding command refuses to
  run in prod). The password `Demo-pass-123!` is a local-only value that
  appears in the repository on purpose. It is not a secret.
- **The "Continue as demo …" buttons** (**Continue as demo host**,
  **Continue as demo buyer**, **Continue as demo host 2 (new owner)**, **Continue as demo
  staff**) appear under the
  sign-in form only when the build has `VITE_DEMO_ACCOUNTS`. Since
  `9107ad2` they are translated too (German "Weiter als Demo-Anbieter 2
  (neu)", French "Continuer avec le compte …"). Only the local
  bootstrap writes that setting (into `.local/web.env`, which `make up` copies
  to `web/.env.development.local`), so a deployed build never has them.
- **After a bootstrap re-run.** `make up` does the copy for you (`Makefile`,
  the `up` target). If the stack was started any other way (a plain `docker
  compose up`), copy it by hand and restart the web app:
  ```sh
  cp .local/web.env web/.env.development.local
  ```
  Without it, after a fresh sign-in pool the app signs in against the old
  pool and the demo buttons fail.
- `make up` ends by printing all four demo accounts and the password (since
  `42c777c`).
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
5. Onboarding asks for your name, person or business, **country** (the open
   ones: Germany, Austria, Switzerland; since `2257182`), district (only that
   country's), what brings you to Cappy, and the age tick ("I am 18 or
   older"; the age comes from the country).

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

**A staff lead** (since `22b5e0f`), for refunds above a support member's
limit and approving other staff's refunds (script 24):

```sh
make confirm EMAIL=lead.test1@example.com ADMIN=1 LEAD=1
```

`LEAD=1` puts the account in both `admin` and `admin-lead` (it creates the
`admin-lead` group the first time), so `ADMIN=1` may be left out. Sign out
and in again afterwards. The account needs a finished onboarding (name,
country, district) before the console opens.

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
  are in the header. **The staff console** is not in the header or the
  dock: staff open it from **You** (Profile) → **Staff** → **Open the staff
  console**, on a phone and a desktop alike; on a desktop there is also a
  **Staff** link at the very bottom of every page, in the footer's row of
  legal links (the footer is not shown on a phone). Or go to
  http://localhost:5173/admin.
- **The bell** (notifications) is at `/notifications`: on the **You** tab on
  a phone, in the header on a desktop.
- **Emails.** No real emails leave your computer. A developer can show you
  every email sent at http://localhost:4566/_aws/ses (raw JSON).
- **A booking's id** is the last part of its address, `/bookings/<id>`.
  Staff can find a case by it (script 24).
- **Ten booking requests a day per renter.** A renter's 11th booking in 24
  hours is refused. If the demo buyer runs out, rent as another account
  (script 29).
- Locally, **the hand-over button is available at once**, whatever the booked
  time, and **a booking can start 5 minutes from now** (deployed: 2 hours).
  So every flow, no-shows, disputes and reviews included, can be walked in
  minutes (see [A5](#a5-shortcutting-time-based-steps)).
- **Where Cappy is open.** The app offers only Germany, Austria and
  Switzerland in its country pickers (since `2257182`). A profile or listing
  in a country that is not open yet is refused with "Cappy is not open in
  that country yet." (`market_not_live`, in your language). A district must
  be in your own country (since `7444e37`: "Pick a district in your own
  country.", `district_not_in_country`). A listing is priced in its owner's
  country's currency (a Swiss owner's in francs); the form shows it and never
  sends another.
- **Errors look like errors** (since `2257182`): a failure toast has a red
  mark instead of a tick and stays about 6 seconds; a success toast about 3.
  A form the server refuses shows each problem under its own field.

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
- [ ] Tap **Create an account**. Enter an invalid email and leave the field.
      **Expect:** "That does not look like an email address." under it
      (since `2257182`); submitting says "Enter your email address, like
      name@example.com."
- [ ] Enter a password of 11 characters. **Expect:** "Use at least 12
      characters…". Twelve characters of anything, spaces too, work.
- [ ] Submit. **Expect:** **Check your email**, and **Send a new code** is
      greyed out with a 30-second countdown.
- [ ] Type a wrong code. **Expect:** a clear "That code is not right" error.
- [ ] Type the right code from `make codes`. **Expect:** signed in, then the
      onboarding screen.
- [ ] Onboarding: leave the name empty and the 18+ box unticked, choose
      **A business** with no details, and continue. **Expect:** every
      problem at once (since `2257182`): the name, "Complete the business
      details above." with each missing business field marked, and the age.
- [ ] **The country picker** (since `2257182`). **Expect:** **Country**
      offers only Germany, Austria and Switzerland, named in the app's
      language, and starts at your device's country if it is one of them
      (else the first). Pick Switzerland. **Expect:** **Where are you?** lists
      only that country's districts, each with its city where the name
      alone would not say it (since `9107ad2`): since `7444e37` Zürich-Kreis 5,
      Plainpalais (Genève), Kleinbasel (Basel), Länggasse (Bern) and Flon
      (Lausanne); for Austria Neubau (Wien), Lend (Graz), Urfahr (Linz),
      Salzburg-Altstadt and Wilten (Innsbruck). Pick Germany again.
      **Expect:** Berlin's districts, and since `1cb2d67` (V7-29) Altona
      (Hamburg), Maxvorstadt (München), Ehrenfeld (Köln), Bockenheim
      (Frankfurt am Main) and Plagwitz (Leipzig), and "I am 18 or older".
      Tick, fill your name and district, and continue. **Expect:** the
      Explore screen.
- [ ] As a business, the tax field reads **VAT ID (optional)** (since
      `4e86866`). Enter `DE12345`. **Expect:** "A German VAT ID is DE and 9
      digits." under the field before anything is sent. Leave it empty.
      **Expect:** accepted (a small business without a VAT ID).
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
- [ ] The system decline reasons ("The listing was taken down by Cappy",
      "The listing was removed by its owner", "The account was suspended")
      are translated since `2257182`: take a listing down (script 19) with a
      request waiting, and read the declined booking in German and French.
      Since `73610c4` (V7-14) the buyer's page is headed by what happened,
      "Cappy removed this listing" ("The listing was removed", "Cappy
      stopped this request"), not "{name} could not take this one"; the
      "Reason: …" line stays under it.
- [ ] German names people neutrally (V7-25), the same in the app and the
      emails (D-25): on a request, the booking page and the case form,
      **Expect** "die vermietende Person" / "die mietende Person" (for
      example "Wartet auf die Annahme durch die vermietende Person", "Neu
      auf Cappy"), never "der Anbieter", "der Mieter" or "die … Seite". In
      French: "le propriétaire" / "la personne locataire".
- [ ] Open the app in two tabs and switch the language in one. **Expect**
      (since `d4a458a`, V7-30) the other tab follows, and the next email
      comes in that language.
- [ ] Open **Help** and the legal pages (privacy, terms, withdrawal,
      ranking, reporting, accessibility, account deletion) in French.
      **Expect:** French text since `2257182` (the Impressum stays German),
      and since `73610c4` (V7-9) a narrow no-break space before ";" and "?"
      ("Vous ne pouvez plus vous connecter ?"), a no-break space before ":"
      (`npm run check:i18n` checks both, in the catalogue and in these
      pages).
      The help pages give the emergency number of your country (112 here).
- [ ] As an English reader on a US device (Chrome: Settings → Languages,
      put English (United States) first), look at times. **Expect:** "5:00
      PM", no leading zero; in German and French, 24-hour times. Emails to
      an `en-US` account read "Sat, Sep 26, 2:00 PM" (since `42c777c`).
- [ ] **Each reader's own locale** (since `ad9dee9`). Buyer's browser on
      English (United Kingdom), host's on English (United States); each
      opens the bell once (that is when the app's locale is remembered).
      The buyer requests the plunge saw. **Expect:** the host's "New
      request" email reads "3:00 PM" style, and a mail the host causes for
      the buyer (accept, an offer) reads "Sat 3 Oct, 15:00" style: always
      the reader's format, never the sender's.
- [ ] In French, emails put a no-break space before ":" and a narrow one
      before ";", "?" and "!" (as in "Refusée : …" and the offer mail's
      "… ; ensuite, c’est nous qui décidons"), and never two full stops
      after a reason. They say « la
      personne locataire » throughout (since `e2e77ab` and `ad9dee9`).

### 3. Browse and search

As the demo buyer.

- [ ] Open **Explore**. **Expect:** "Free in the next 24 hours" as a rail and
      on the map, starting from Kreuzberg.
- [ ] Type two letters in search. **Expect:** "Type at least 3 letters to
      search." Type `saw`. **Expect:** matching listings, including the
      plunge saw. Search looks only in the city you are in (the place in
      the header). On a desktop, press Enter. **Expect:** the cursor stays
      in the field and you can type on (since `9107ad2`; on a phone Enter
      puts the keyboard away).
- [ ] Pick a category (for example Workshop & tools). Set hours, district and
      radius. **Expect:** bookable times, never starting sooner than 5
      minutes from now locally (2 hours deployed; see
      [A5](#a5-shortcutting-time-based-steps)).
- [ ] Change the sort (best match, cheapest, soonest, nearest). **Expect:**
      the order changes and `?sort=` in the address changes with it.
- [ ] Switch between the list and the map. Pick another district or city.
- [ ] Ask for something nothing fits (a tiny radius, many hours). **Expect:**
      "No idle capacity fits that", with **Widen to 90 km** and **Allow 3
      weeks**. For one day (`/?cat=workshop&h=10&km=1&days=1`) the text says
      "…10 hours free in the next 24 hours." (since `73610c4`, V7-17; "in the
      next {n} days" for more), and in a miles locale a 1 km radius reads
      "0.6 mi", not "1 mi".
- [ ] Distances read in km in German, French and European English, the
      radius on the requirement chip too (since `2257182`).
- [ ] **The ranking page** (since `2257182`). Beside the count of bookable
      slots, and beside free-text results, tap **How results are ordered**.
      **Expect:** `/legal/ranking` with four signals (price, trust, soonest,
      distance) and their weights as percentages (30 %, 30 %, 20 %, 20 %),
      read from the server (`GET /api/ranking`), in the app's language, and
      the statement that nobody can pay for a better position. It opens
      signed out too.
- [ ] As the demo host, search. **Expect:** your own plunge saw is never
      offered to you.

### 4. A listing

As the demo buyer, open the plunge saw (`/listing/l9`).

- [ ] **Expect:** photos, title, the host card (name, verified shield, track
      record, whether a business or a private person), reviews, house rules,
      the cancellation policy (shown as flexible), and a price with "Total,
      incl. … service fee".
- [ ] Choose a duration, then a day, then a time. **Expect:** the price
      updates; only free starts are offered, and **every** start of the day
      (since `4e86866`: with 2 hours on a day open until 22:00, 20:00 is
      there; before, the chips stopped after twelve). Each day chip carries
      its weekday, also after the first week. Since `9107ad2` the day chips
      reach **two weeks** ahead (before, they stopped after four or five
      days), so next weekend can be picked. Since `1cb2d67` (V7-1) a day with
      more than 28 starts is thinned evenly across the day, not cut: on a
      listing free around the clock, **Expect** starts into the evening
      (before, 00:00 to 13:30 only). With the plunge saw's 08:00-22:00 every
      day, **Expect** the same times on a Sunday as on a weekday.
- [ ] The duration being priced is always a selected chip (since
      `9107ad2`): on the photo studio (2 to 10 hours) the chips include the
      duration the price and the sticky bar name, selected.
- [ ] The host card's response time. The seeded owners start with the
      response time in the demo data (the plunge saw's host: "Replies in ~12
      min"). Once booking has measured an owner (after their first answer or
      lapsed request), it is shown only with at least 3 answered or lapsed
      requests in 90 days (H-1), with "Answers {n} % of requests". Under
      that, and for the second host, **Expect** nothing about response
      time, never "null" (fixed in `2257182`).
- [ ] **Expect** "Approximate area. The exact address is shared once the
      owner accepts." (on the district line, and in the confirm sheet). On
      the instant-book bandsaw it reads "… shared once the booking is
      confirmed." (since `4e86866`).
- [ ] As the demo buyer, open the van run. **Expect** (on a stack made
      since `22b5e0f`) quantity chips 1 and 2 only, "{n} pallets take about
      …, including 1 h to load", and a **Loading** row of €20.00 in the
      price.
- [ ] Tap the heart. **Expect:** it fills at once; the listing appears under
      Saved on your profile. Tap again to remove it.
- [ ] **Report** and **Block** are on the page (tested in scripts 18 and 13).
- [ ] At 200 % text on a phone-sized window in French (A7), **Expect:** no
      sideways scrolling; the host card's rating column wraps (since
      `9107ad2`), and the category chip over the photo wraps instead of
      reading "At…" (since `73610c4`, V7-27).
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
      the Earn inbox, a bell item "New request: …", and an email. Since
      `1cb2d67` (V7-23) the email's subject names the start ("New request:
      Festool TS 55…, Sat 3 Oct, 10:00") and the text the price ("Someone
      wants to book … for €8.00."). It does not name the renter yet.

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
      "Confirmed" (bell and email); since `1cb2d67` the email names the start
      and says "You paid €…. Hand-over: <address, postal code>. The instructions are in the app." (D-26). Both now see **Getting in**: the hand-over
      address (for the plunge saw "Tempelhofer Damm 22, 12099 Berlin") and
      instructions, and for a listing with a postal code or a point, the
      postal code after the address and **Open in a map** (since
      `2257182`; the point is the district's centre for now).
- [ ] Host: **Edit** the listing's hand-over address after accepting. Buyer:
      reload the booking. **Expect:** the new address (since `42c777c`: it is
      read live while the booking is accepted or in progress).
- [ ] Make a second request. Host: **Decline** (on Earn or on the booking
      page), pick a reason chip, **Send decline** (the booking page's
      button says so too since `9107ad2`). **Expect:** both pages show "Reason: It needs a repair
      first." on its own line above "The hold on the card is released;
      nothing was charged.", and only the buyer's offers **Find another**
      (since `4e86866`); the buyer's email ends with "Reason: …" (since
      `22b5e0f`), and since `1cb2d67` (V7-4) so does the bell item. A reason
      the host typed ending in "?" or "!" gets no extra full stop, and in
      French it is quoted exactly as typed (V7-24).
- [ ] Double-tap **Accept** (Earn inbox or booking page). **Expect:** no
      error at all: since `73610c4` (V7-6) a second tap that finds the
      booking already accepted counts as done (before, a red toast "cannot
      accept a booking that is accepted").
- [ ] A request nobody answers lapses at the earlier of 24 hours or the
      booked start. **Expect:** buyer gets "Expired: … Nothing was charged."
      A late tap on Accept says "this request has lapsed".

### 8. Hand-over photos, start and complete

With an accepted booking of the plunge saw.

- [ ] Both sides see a safety card (meet at the booked address, take check-in
      photos together, keep messages and payments on Cappy).
- [ ] Host: **I have handed it over** (or buyer: **I have collected it**).
      **Expect:** the booking is in progress, and check-in photos are offered.
- [ ] Add 1 to 12 check-in photos with a note. Pick one photo, then tap
      **Add more photos** and pick another. **Expect:** both are kept (since
      `2257182`), each preview has a remove button, then "Uploading 1 of …"
      progress, then the photos with their upload time, visible to both
      sides.
- [ ] Buyer: **Mark as handed back**. **Expect:** "Handed back and all
      fine?" with **Yes, it is done**, **Add check-out photos first** and
      **Not yet**.
- [ ] Tap **Add check-out photos first**, pick a photo, **Save 1 photo**.
      **Expect** (since `73610c4`, V7-22): once the photos are saved,
      "Handed back and all fine?" comes back by itself. **Not now** in the
      photo sheet does not bring it back.
- [ ] **Yes, it is done**. **Expect:** completed.
      Host gets "You have been paid …" whose text names the listing and its
      start ("Your share for Festool TS 55…, Sat 3 Oct, 10:00…", since
      `22b5e0f`, never a booking id) (bell, email). Buyer gets "How was …?"
      and the rating sheet opens. A completed booking no longer offers
      check-out photos (since `4e86866`).
- [ ] The host has no "complete" button: only the buyer (or, after 48 hours,
      the system) completes.

### 9. No-show

A no-show can only be reported on an accepted booking nobody has marked as
handed over, from the booked start until 2 hours after it: the buyer
reporting the host from the start itself, the host reporting the buyer from
30 minutes after the start (the late renter's grace). These windows are not
shortened locally, but the lead time is: book a start about 5 to 10 minutes
from now on the plunge saw (the host accepts) or the bandsaw (confirmed at
once), which are open every day from 08:00 to 22:00, weekends included, and
wait for the start ([A5](#a5-shortcutting-time-based-steps)). The host's side
needs another 30 minutes of waiting.

- [ ] Before the start: **Expect:** no "did not show up" button.
- [ ] Buyer, after the start, nobody marked the hand-over: **… did not show
      up**, confirm. **Expect:** the sheet says you get everything back and it
      counts against the host. The booking is cancelled with "Reported: … did
      not show up". **Expect** (emails, since `ad9dee9`): the buyer gets
      "Refunded: …" with "you get the full price back (€…)"; the host gets
      "Reported as a no-show: …", that it counts against their reliability,
      and "If this is wrong, tell us through Get help on the booking."
- [ ] On another booking, host, from 30 minutes after the start: **… did not
      show up**. **Expect:** the sheet says the renter gets nothing back and
      you are paid. The host gets "No-show recorded: …" ("you are paid as for
      a late cancellation: nothing is refunded."), the buyer "Reported as a
      no-show: …" with "nothing is refunded" and how to contest. In the
      staff case, **Payment** reads "Paid out", with nothing refunded. Since
      `73610c4` (V7-2) both booking pages' price card shows the price as
      charged, the fee and the host's share (before, "Nothing: hold
      released"), and **Bookings → Past** shows what stayed.
- [ ] A booking with an extension waiting (script 27): report the no-show
      on the first booking. **Expect:** the extension is declined with "The
      booking it extends was cancelled" (since `ad9dee9`). A **confirmed**
      extension (the bandsaw's) is cancelled with a full refund instead, its
      page gives the same reason, and since `1cb2d67` (V7-12) the buyer gets
      "Extension cancelled: …" with "You get €… back to your card." and the
      host "The renter gets everything back (€…)" (always emailed).
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
      **Expect:** the buyer gets "Cancelled by the owner: …", "The owner
      cancelled your booking of … You get €… back to your card." (since
      `ad9dee9`), and a full refund.
- [ ] After the start: **Expect:** no cancel button; the buyer sees **Report a
      problem** instead.
- [ ] Handed over before the start (tap **I have handed it over** early):
      **Expect:** no cancel button either; the buyer sees **Report a
      problem** (since `42c777c`).
- [ ] After any cancellation, open the booking. **Expect** (since
      `73610c4`, V7-2/V7-3) the price card to tell what moved: "Charged ·
      Nothing: hold released" for a withdrawn request, "Refunded €…" when
      everything came back, and after a part refund (a settled dispute,
      script 25) the total, "Refunded −€…", the fee and the host's share of
      what stayed; **Bookings → Past** shows the same net amount, not the
      list price.
- [ ] The cancel sheet reads the server's answer (since `2257182`): on a
      requested booking it says the hold is released and nothing is
      charged; on an accepted one, what you get back.
- [ ] In Stripe mode, check the refund in the Stripe test dashboard.

### 11. Disputes

Needs an accepted booking whose start has passed, or an in-progress one
(handed over), at any time. Only the buyer can report a problem: on an
accepted booking from the booked start, on an in-progress one at once (since
`42c777c`, an early hand-over), until the booking completes (the buyer
confirming it, or the system 48 hours after the end). Locally, book the
plunge saw or the bandsaw about 5 minutes from now (any day), and wait for
the start, or just mark the hand-over ([A5](#a5-shortcutting-time-based-steps)).

- [ ] Buyer, on an accepted booking before the start: **Expect:** no
      **Report a problem** button.
- [ ] Buyer, on a booking handed over before its start: **Report a problem**.
      **Expect:** the report goes through (since `42c777c`).
- [ ] Buyer, after the start: **Report a problem**, write what went wrong,
      **Report the problem**. **Expect:** "Reported. The payment is on hold";
      buyer gets "We received your report: …"; host sees "… reported a
      problem… Your payout is on hold" and gets an email.
- [ ] Both pages. **Expect** (since `4e86866`): under the banner a card
      **Settle it between you**, the sticky button **Get help with this
      booking** (not "Browse capacity"), and the **Getting in** address
      still shown. Host2's (or the host's) **Earn** lists it under **Under
      review** with **Payout on hold**.
- [ ] The two sides can settle it themselves: script 25. Staff decide it:
      script 24.
- [ ] A disputed booking never completes by itself.
- [ ] If the server refuses a report, **Expect:** the sheet stays open with
      what you typed and a red error toast (since `2257182`).

### 12. Two-way blind reviews

After a completed booking.

- [ ] Buyer: rate the host (on time or late, 1 to 5 stars, tags, an optional
      note). **Expect:** "Thanks. … will see it once they have rated too."
      The review is **not** on the listing yet.
- [ ] Host: **Rate …** the renter (1 to 5 stars). **Expect:** "Thanks. Both
      ratings are published now." (since `4e86866`), and the review appears
      on the listing, signed like "Demo B.".
- [ ] On another booking, host rates first, then the buyer. **Expect:** the
      host reads "Thanks. … will see it once they have rated too.", the
      buyer "Review posted on …" (the confirmation follows who rated first,
      since `4e86866`).
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
- [ ] Host accepts. **Expect:** both sides now see the original text, the
      buyer's window too **without a reload** (since `4e86866`, the thread
      is read again when the booking's status changes).
- [ ] Send "Can I pay you by PayPal or cash?". **Expect:** it is sent, the
      sender sees "Keep payments on Cappy…", and the reader sees a warning.
- [ ] Other side: **Report** on a message, then **Block … too**. **Expect:**
      no more messages or new bookings between you, both ways. The booking
      itself stays. Unblock from Profile → **Blocked people**.
- [ ] **The block in the conversation** (since `73610c4`, V7-5). As the
      buyer, block the host from the booking page. **Expect:** the message
      box is gone and in its place "You blocked Nadia, so no messages can be
      sent." with **Unblock**; tap it. **Expect:** "Unblocked" and the box
      back. Now let the host block the buyer, and send as the buyer.
      **Expect:** no raw server text: the box gives way to "Messages to
      Nadia cannot be sent."
- [ ] Cancel an accepted booking. **Expect:** contact details hide again and
      the conversation becomes read-only.
- [ ] Send 31 messages in a few minutes. **Expect:** the 31st says to wait a
      little.
- [ ] Type a draft, reload the page. **Expect:** the draft is still there.
- [ ] Emails for messages: at most one per conversation every 15 minutes, and
      they carry the title and a link, never the text.
- [ ] On a completed booking more than 14 days after its end, **Expect:** no
      message box, and "This booking is closed, so no new messages can be
      sent." (since `2257182`). The same text appears if the server refuses
      a message as closed.

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
      window opens; after it, the app waits up to a minute and books. (A
      provider with a hosted page would open in a new window and wait up to
      two minutes; none is configured locally.)
- [ ] Book another listing above €300. **Expect:** no second ID check.
- [ ] Nobody answers this request (its owner has no sign-in); it lapses.

### 15. Becoming a host and creating a listing (held listings)

Use a **fresh** account (the demo host already has completed jobs, so its
listings are never held). To see a held listing without making one, the
second host's photo studio is waiting after a clean rebuild (unless a tester
has approved it since; see [A1](#a1-test-accounts)). The threshold is the owner's
market's (`markets.json` `held_listing_above`): €100 an hour in Germany and
Austria, CHF 95 in Switzerland.

- [ ] Go to **Earn** → **List your first thing** (or Profile → **List
      something you own**). Pick a category.
- [ ] **Where is it?** lists only your own country's districts (since
      `4e86866`): as a German owner, Berlin's and, since `1cb2d67` (V7-29),
      Altona (Hamburg), Maxvorstadt (München), Ehrenfeld (Köln), Bockenheim
      (Frankfurt am Main) and Plagwitz (Leipzig); not Amsterdam or Milan.
- [ ] Fill in the title, blurb, district, the hand-over address, the
      optional **Postal code** (since `2257182`), the rate (the € sign comes
      from your country), hours, photos (at most 12; each tile shows its
      upload progress, and a failed one offers **Retry**), rules,
      instructions and when it is free. Reload halfway. **Expect:** "Your
      unsaved changes are back", with **Discard**.
- [ ] **The weekly editor** (since `2257182`). Under when it is free, each
      preset now reads "… · every week". Choose **Set my own weekly hours**.
      **Expect:** a row of day chips (Mon to Sun, in your language) with
      **Free from** and **Until**, Monday to Friday 09:00 to 18:00 to start,
      and "Repeats every week in {your device's time zone, such as
      Europe/Berlin}. Cappy keeps the next 8 weeks open and never overlaps a
      booking." Untick every
      day. **Expect:** "Pick at least one day for each time." Set **Until**
      before **Free from**. **Expect:** "It has to stop being free after it
      starts being free." Tap **Add other hours** (Saturday and Sunday 10:00
      to 16:00 appear), fix the first row and publish. **Expect:** on the
      listing, free windows on those days for the next eight weeks. If one of
      the days is today and its hours have begun, today's window starts at
      the next quarter hour (since `22b5e0f`; before, today was left out).
- [ ] Pick **Freight** (booked by quantity).
      **Expect** (since `4e86866`): **Vehicle** instead of Machine, **Pallets
      loaded per hour**, and **Most per booking (optional)** ("How many
      pallet spaces you have free, say 2."). Set 2 and publish; as the buyer
      the listing offers 1 and 2 only.
- [ ] Edit that listing. **Expect:** a card "Repeats every week" with the
      hours and "Cappy keeps the next 8 weeks open for you (Europe/Berlin)."
      Tap **Stop repeating** (it reads "The weekly schedule stops when you
      save" and offers **Keep the weekly schedule**) and save. **Expect:** the
      windows the schedule made are gone; windows you added by date stay.
      The second host's listings show the same card.
- [ ] On a listing with weekly hours, add a window by date that covers
      part of them, then remove that window (Earn → **Edit**, or
      `DELETE /api/listings/{id}/slots/{slot}`). **Expect** (since `1cb2d67`,
      V7-11): the weekly hours it covered are free again at once, not only
      after the next hourly roll.
- [ ] Publish with a rate of **€100 an hour or less**. **Expect:** "… is live",
      and the listing is found in search by other accounts.
- [ ] Publish another with a rate **above €100 an hour**. **Expect:** "… is
      saved and waiting for a quick check…", and the Earn card says "Waiting
      for a quick check". Other accounts cannot find or open it. **View as a
      guest** still works for you.
- [ ] Staff: in the console under **Waiting for a check**, **Approve**.
      **Expect:** "Approved: it is live now", and other accounts can now find
      it.
- [ ] **The listing plate's time** (since `73610c4`, V7-20). On Earn (or a
      cover in Explore), the time on the plate is a start that can really
      be booked: the next half hour after the lead time (5 minutes on the
      dev server, 2 hours in a build), so at 16:39 locally "17:00", never
      "18:39"; in the reader's clock ("5:00 PM" on an English (United
      States) device).
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
      completed booking, listed as "Service fee · {title} · {dates}" in your
      language's date format (since `2257182`). Tapping it opens the invoice
      in a new tab. The recipient block names the host and an address (since
      `42c777c`): a business's own address, or for a private host the address
      the payout provider verified; with the fake provider that is
      "Musterstraße 1, 10115 Berlin, DE (test)".
- [ ] **The invoice in the app's language** (since `ad9dee9`). With the app
      in English, open an invoice. **Expect:** "Invoice", "Platform fee for
      {listing title}", a separate "Booking reference: bk_…" line, amounts
      like "€6.00", and "VAT ID (USt-IdNr.)" and "Tax number (Steuernummer)"
      in the issuer block. Switch to French: "Facture", "Référence de
      réservation", "6,00 €". German: "Rechnung", "Vermittlungsgebühr für
      …".
- [ ] **Written the reader's way** (since `1cb2d67`, V7-10). **Expect:** in
      French "Date de facture :" (a space before every ":"), "TVA 19 %" and
      dates like "26/09/2026"; in English "VAT 19%" and "26/09/2026" (on an
      English (United States) device "9/26/2026"); in German "USt 19 %" and
      "26.09.2026". A booking of one day shows its date once, not "26.09.2026
      – 26.09.2026". The issuer block shows both the VAT ID ("DE000000000
      (local)") and the tax number locally.
- [ ] Stripe mode: **Set up payouts** creates the Stripe account in the
      profile's country (since `2257182` the app sends it; every demo host is
      German).

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
      or money; since `22b5e0f` also how a dispute was settled ("Settled: …")
      and a late-return decision, since `ad9dee9` the no-show notices and
      "Cancelled by the owner: …", and since `1cb2d67` "Extension cancelled:
      …" (script 9).
- [ ] Decline a request with a reason (script 7). **Expect** the buyer's
      bell item to show "Reason: …" under its first line (since `1cb2d67`,
      V7-4; before, only the email had it).
- [ ] A removal notice in the bell (a message or review of yours removed by
      staff, script 19). **Expect** (since `22b5e0f` and `4e86866`) the whole
      statement: what was removed, why, the ground and how to contest, on
      several lines, not only "A message or review of yours was
      removed".
- [ ] News and offers is off by default.
- [ ] Profile → **Notifications**: **Expect:** one row per kind, each with
      a **Push** and an **Email** checkbox (since `73610c4` rows that wrap,
      not a table), and under them "Booking confirmations and changes always
      arrive by email, whatever you choose here." (the old "Everything also
      arrives by email." is gone since `2257182`).
- [ ] At 200 % text in French on a 390 px window (A7), Profile. **Expect:**
      no sideways scrolling (since `73610c4`, V7-8; the table ran 529 px
      wide), and the language switch wraps if it must.

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
      email, and the good-faith statement. Under the form: "If someone is in
      danger, call 112 first" (your country's number since `2257182`).
- [ ] Send 4 reports with the same email in one day. **Expect:** the 4th is
      refused: "We already have your reports from today; we will be in
      touch." (429 `reports_today` since `1cb2d67`), in your language
      since `d4a458a`.
- [ ] Staff then sees each report in the console queue (script 19).

### 19. The admin console

Sign in as `staff@demo.cappy.local`. Open **You** (Profile) → **Staff** →
**Open the staff console**, or on a desktop **Staff** at the bottom of the
page (the footer's legal links), or http://localhost:5173/admin. The console
opens with **Cases** and **Waiting for approval** (script 24), then the
reports queue, held listings, **Act directly** and the **Audit log**.

- [ ] As the demo buyer, open `/admin`. **Expect:** "Only for Cappy staff".
- [ ] **Reports**: the open queue, oldest first. **Expect** (since
      `73610c4`, V7-19) each target by name: "Fraud or a scam · Person Nadia
      Brandt", "Unsafe · Listing Festool TS 55…" (a listing links to its
      staff view), named from the server's `targetLabel` since `d4a458a`;
      never a raw `d0ae1f5d-…`. Open one, **Decide on this report**.
      **Expect** (V7-26) the sheet opens with what was reported: the reason,
      the target by name, the reporter's words, and for a review the
      review's own text. Try a statement shorter than 20
      characters. **Expect:** you cannot decide.
- [ ] Pick **Take down**, type a statement, close the sheet without deciding,
      and open **Decide** on another report. **Expect:** it opens fresh, at
      **Dismiss** with an empty statement (since `2257182`).
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
- [ ] **Waiting for a check**: approve a held listing (script 15). Each card
      shows the title, the rate, how long it has waited and the owner's name,
      jobs done and year joined (since `4e86866`), the rate in the
      listing's own currency (since `b5cdd93`), and **Look at it**.
- [ ] **The staff view** (since `eaeb485`, reworked in `9107ad2`). On the
      held *Photo studio with daylight wall* (second host, waiting after a
      clean rebuild), **Look at it**. **Expect:** `/admin/listing/<id>`: the
      listing page under a banner **Staff view · Held: waiting for a quick
      check** with "Held … ago" and **Approve**; a **Hand-over address**
      card; its reviews, if it has any; its real free starts for Monday to Friday, 09:00 to
      18:00 (not "Nothing free that long") and a price; no **Report**, no
      **Block**, and no way to book. On one of the 29 held for where they
      are (script 28), **Expect:** the reason ("In a country where Cappy is
      not open yet"), no **Approve**, and no durations or start times. As the
      demo buyer, the same address says "Only for Cappy staff". Since
      `73610c4` (V7-26) the staff view never speaks to a renter: **Expect**
      "Business. EU consumer rights apply to bookings with it." (a business
      owner, by its whole name), "If the owner cancels, the renter gets
      everything back.", and the week's bar in free and sold, not "your
      booking".
- [ ] Back on **Waiting for a check**, **Approve** the studio (or approve it
      from its staff view). **Expect:** "Approved: it is live now"; the
      buyer finds it and can book it Monday to Friday, 09:00 to 18:00, for
      the next eight weeks; as host2, **Edit** shows "Repeats every week". It
      stays approved until the next `make clean`.
- [ ] Listings held for where they are (script 28) show "Not live: Cappy is
      not open in that country yet…" instead of **Approve**.
- [ ] **Act directly**: **Take a listing down** (listing id), **Suspend an
      owner** / **Reinstate an owner** (owner id). A reinstated owner can list
      and book again, but their old listings stay down. **Expect** no
      "Resolve dispute" actions any more (since `4e86866`: disputes are
      decided on the case page, script 24).
- [ ] **Audit log**: every staff action, in every service, newest first, in
      words ("Taken down · Listing", "Resolved a dispute · Booking …",
      "Opened a case", "Looked at hand-over photos", "Withdrew a refund
      proposal"; "by you", or "by staff" and the first 8 characters of their
      id). Since `9107ad2` a booking action's line reads the listing, the
      outcome, the money and the reason in words, then the note ("Bandsaw
      and bench… · Refund part of it · €5.00 · Damage. The photos show…"),
      never "partial 500 EUR (damage)" or "withdrew rs_…", and one visit to
      a case is one "Opened a case" (twice within a minute is one line,
      since `ad9dee9`; since `1cb2d67`, V7-13, any read within 60 s of the
      last, so deciding a case no longer adds a second "Opened a case" when
      its refetch crosses the minute). A booking's id links to its
      case. Type an id under **About (booking, listing or person id)** and
      **Filter**: only that target's entries. **Older** loads the next page
      (since `4e86866`). In German, the approve statement reads in German,
      not "Checked and approved".

### 20. Data export and account deletion

Use a **fresh** account for deletion.

- [ ] Profile → **Your data** → **Download my data**. **Expect:** a file
      `cappy-my-data.json` with your profile, listings, bookings, messages,
      payments, notifications and settings. No card numbers. Since
      `747ed6b` it also has the ID-check consent (when, which text), links
      to your hand-over photos that work for a day, and staff decisions about
      your messages and reviews (since `42c777c` also older decisions,
      attributed by a migration and an hourly job). Since `1cb2d67` (V7-16)
      the buyer's file also has `claimsAboutMe` (a late return reported
      against them, script 26) and `renterRatingsAboutMe` (hosts' ratings of
      them, only once both reviews are published). On a desktop browser the
      file downloads (since `2257182`); on a phone the share sheet opens.
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
- [ ] In one: Profile → **Sign out everywhere**. **Expect:** the dialog
      says every phone, tablet and browser "is signed out at once and stops
      getting notifications" (since `9107ad2`; before, "within an hour").
      Confirm. **Expect:** that browser is signed out with "Signed out on every device", and its old
      token is refused at once (since `42c777c` the check is exact to the
      moment, not the second), by every service including browse and
      search (matching asks catalog, within 30 s).
- [ ] The other browser, on its next action. **Deployed**, it is signed out.
      **Locally this may not happen:** the local sign-in service cannot end
      other sessions, so Cappy skips that step and the other browser can
      refresh its sign-in and carry on. Its push devices are still removed.
      Note what you see, but do not report the other browser staying signed in
      as a bug: this is a stated limitation of the local stack (GD-4, not
      fixable on cognito-local, which has no global sign-out; `docs/runbook.md`,
      "Local stack only").
- [ ] Try it 6 times in an hour. **Expect:** the 6th is refused.
- [ ] Plain **Sign out**. **Expect:** back to sign-in; drafts are cleared.
      **Locally**, an access token copied before the sign-out keeps working
      until it expires (cognito-local issues them for 24 hours and ignores
      the revocation; deployed they last 15 minutes and are revoked with the
      refresh token). Do not report that as a bug (V7-28, `docs/runbook.md`
      since `1cb2d67`); **Sign out everywhere** does end it.

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
- [ ] At 200 % text (the browser's text size, or Dynamic Type in the app),
      in French: **Expect:** no sideways scroll on a listing, and the dock
      turns to icons only, also when the text size changes after the page
      has loaded (since `9107ad2`); since `73610c4` also none on **You**
      (Profile: the notification settings wrap, V7-8), and the listing's
      category chip wraps instead of cutting to "At…" (V7-27).

### 24. The staff case view and resolving a dispute

Needs a disputed booking (script 11). For a refund **within** a support
member's limit (€250 in Germany and Austria, `markets.json`
`refund_limit_support`), a bandsaw or plunge-saw booking will do. For one
**above** it you need a booking over €250: the second host's photo studio
(€160 an hour) for 2 hours is €320 (approve it first, script 19; it is open
Monday to Friday, so on a weekend add today in its weekly hours as host2,
script 15; above €300 the ID check comes first and passes at once with the
fake provider, script 14). You also need a **second staff account that is a
lead** for the four-eyes approval:

1. Make a fresh account ([A1](#making-a-fresh-account)), for example
   `lead.test1@example.com`, and finish onboarding (name, Germany, a Berlin
   district).
2. Run `make confirm EMAIL=lead.test1@example.com ADMIN=1 LEAD=1`.
3. Sign out and in again with it, in a second browser or Chrome profile
   ([A3](#a3-before-you-start-tips-that-save-time)).

`staff@demo.cappy.local` stays a support member (limit €250); the lead's
limit is €2 500.

**Finding a case.**

- [ ] As `staff@demo.cappy.local`, open the console. **Expect:** **Cases**
      at the top with **Disputed** selected: your disputed booking with its
      status, price, time, "Demo Buyer → Demo Host Two" (the two names) and
      "changed … ago". An offer on the table shows "Offer on the table: …",
      and "Escalated to staff" an escalated one; both only while the
      booking is disputed (since `9107ad2`, a settled one shows neither).
- [ ] Switch to **All**. **Expect:** every booking, most recently changed
      first, and **Next page** when there are more.
- [ ] Paste the booking id (the end of its `/bookings/<id>` address) into
      **Booking id** and **Search**. **Expect:** that one case.
- [ ] Type `buyer@demo.cappy.local` into **Member id or email** and
      **Search**. **Expect:** the demo buyer's bookings on either side
      (works locally since `b5cdd93`: every service asks cognito-local).
- [ ] Open the case (its title). **Expect:** `/admin/case/<id>` with the
      status, time, price and id; **Open the listing (staff view)** (script
      19); a banner **In dispute** ("Reported by the renter … ago:
      {reason}"); **People** (renter and owner by name); **Decide the
      dispute**; **Timeline** (each step by renter, owner, "you" or "staff
      …", and payment results and sweeps as **Cappy (automatic)**, never a
      service name; since `eaeb485`); **Conversation, as written**, where
      contact details masked before acceptance read in full; **Hand-over
      photos**; **Payment** (status, amount, and what was captured,
      refunded and paid out to the owner as money, since `b5cdd93`).
- [ ] **Audit log** on the console. **Expect:** one "Opened a case ·
      Booking …" by you for the visit (every opening is logged, and so is
      looking at hand-over photos as staff; opening it again within a
      minute adds no second line, since `ad9dee9`, and since `1cb2d67`
      within 60 s of the last read, so deciding the case, whose refetch may
      cross the minute, adds no second "Opened a case" either, V7-13). In
      German the outcomes read neutrally ("Der mietenden Person alles
      erstatten", V7-25, D-25).

**Within the limit: settled at once.**

- [ ] On the bandsaw booking (€15), **Decide the dispute**: **Refund part of
      it**. Type `20`. **Expect:** "More than nothing and less than €15.00."
      Type `5`. **Decide** stays greyed out until a **Reason** is chosen and
      **What you found** has at least 10 characters. Pick **Damage**, write
      a note such as "The photos show a bent fence; a small refund is
      fair.", **Decide**. **Expect:** "Decided. Both sides have been told";
      under **Decisions** (since `9107ad2`; "Refund decisions" before)
      "Refund part of it · €5.00 · Done" with the reason, "you" and your
      note.
- [ ] **Expect** for both sides (always emailed): "Settled: Bandsaw and
      bench…", "Cappy decided: €5.00 goes back to the renter, and the owner
      is paid for the rest.", then "From Cappy's team: The photos show a
      bent fence; …" as its own paragraph (email since `b5cdd93`; the bell
      item carries the note too since `ad9dee9`). No "Cancelled" and no
      "How was …?". Host2 gets "You have been paid €8.50" (their 85 % of the
      €10 kept). Both booking pages show **The reported problem was
      decided** ("You get €5.00 back to your card, and the owner is paid the
      rest." / "The renter gets €5.00 back, and you are paid the rest.") and
      under it "From Cappy’s team: The photos show…" (since `9107ad2`). The
      case's **Payment** status reads "Partly refunded", with €15.00
      captured, €5.00 refunded and €8.50 paid out to the owner.
- [ ] On another disputed booking, **Pay the owner**. **Expect:** completed;
      the renter's banner says it was decided in the owner's favour, the
      owner's that the payout is on its way. **Refund the renter in full**
      on a third: cancelled, "the renter gets the full price back".

**Above the limit: four eyes.**

- [ ] On the €320 studio booking, as `staff@demo.cappy.local`: **Refund the
      renter in full**, a reason and a note, **Decide**. **Expect:** "Above
      your limit: it waits for a second staff member"; under **Decisions**
      "Refund the renter in full · €320.00 · Waiting for a second staff
      member" with "you" and **Withdraw my proposal**; nothing is refunded
      yet; the case card on the console says "Waiting for approval".
- [ ] **The Decide lock** (since `9107ad2`). **Expect:** in place of the
      form, a **Decide** card: "A proposal is waiting for a second staff
      member: Refund the renter in full · €320.00. Nothing else can be
      decided until it is approved, rejected or withdrawn.", with
      **Withdraw my proposal**. No other decision can be sent.
- [ ] On the console, **Waiting for approval** lists it with the listing
      and the owner ("Photo studio with daylight wall · …", since
      `9107ad2`) and "proposed by you". **Expect:** only **Open the case**
      and **Withdraw my proposal**: you cannot approve your own proposal
      (since `eaeb485`; the server would refuse it with "A second staff
      member has to approve a refund you proposed.").
- [ ] **Withdraw my proposal** (since `e2e77ab`/`eaeb485`). **Expect:**
      "Withdrawn. You can decide the case again"; it leaves **Waiting for
      approval**; on the case its decision reads "Withdrawn by the
      proposer" and the **Decide the dispute** form is back. Propose it
      again for the next step.
- [ ] As the lead, **Waiting for approval** → **Approve** with a why.
      **Expect:** "Approved. The money moves now"; the booking is cancelled
      and refunded in full; both sides get "Settled: … Cappy decided: the
      renter gets the full price back (€320.00)" and the note under "From
      Cappy's team:" (the proposer's note); the decision reads "… Done ·
      approved by staff …" (as the lead: "approved by you").
- [ ] Propose another over-limit refund, and as the lead **Reject** it.
      **Expect:** "Rejected. The booking stays in dispute", and a new
      decision can be made.
- [ ] Optional: a second staff account **without** `LEAD=1`
      (`make confirm EMAIL=… ADMIN=1`) approving an over-limit refund.
      **Expect:** "This refund is above your limit: a lead has to approve
      it."
- [ ] As the lead, decide a €320 refund yourself. **Expect:** settled at
      once (within the lead's €2 500).
- [ ] **Audit log**: "Proposed a refund", "Withdrew a refund proposal",
      "Approved a refund", "Rejected a refund", "Resolved a dispute", each
      with who and when, and in words (since `9107ad2`): the listing, the
      outcome, the money and the reason, then the note ("Photo studio with
      daylight wall · Refund the renter in full · €320.00 · Damage. …").
      No machine text such as "refund_buyer 32000 EUR (damage)".

### 25. Dispute offers between the two sides

Needs a disputed bandsaw booking (script 11; €15). Buyer and host2 in two
windows.

- [ ] Both pages. **Expect:** **Settle it between you**: "Agree on what goes
      back to the renter, and it is settled at once. Otherwise Cappy decides
      {when}." (in about 10 minutes locally, about three days deployed; one
      full stop, also in German) and **Make an offer**. In the last minute
      it reads "in under a minute", never "in 0 min" (since `73610c4`,
      V7-21).
- [ ] Buyer: **Make an offer**. **Expect:** a sheet "What should go back to
      the renter?", the field **You get back**, "Of €15.00. The owner is paid
      the rest." Type `20`. **Expect:** "Between nothing and €15.00." and
      the button greyed out. Type `10`, **Offer €10.00**. **Expect:** "Offer
      sent. Demo can answer until {day} {time}" (the other side's first name
      and the real deadline, about 10 minutes away locally; since
      `9107ad2`), and
      "Your offer · €10.00 back to the renter … Waiting for Demo.", with no
      **Accept** for your own offer.
- [ ] Host2: **Expect:** a bell item (and an email, per the Bookings
      setting) "An offer to settle: Bandsaw and bench…", "€10.00 back to the
      renter. Accept it, or make another offer, by {date and time}; after
      that we decide." On the page (within 15 seconds): "Demo offers €10.00
      back to the renter" and **Accept €10.00**.
- [ ] Host2: **Make another offer** (the field reads **You give back**, and
      "Of €15.00. You are paid the rest.", since `9107ad2`), €6.
      **Expect:** the buyer's page shows host2's offer instead, and the
      window starts again.
- [ ] Stale offer: with the buyer's page open, host2 offers €7; before the
      buyer's page refreshes (15 s), the buyer taps **Accept €6.00**.
      **Expect:** "The offer changed a moment ago. Look at the new one."
- [ ] Buyer: **Accept €7.00**. **Expect:** "Agreed. The dispute is
      settled"; the booking completes; both get "Settled: …" (always
      emailed): host2 "You agreed a settlement: €7.00 goes back to the
      renter, and the owner is paid for the rest.", and since `1cb2d67`
      (V7-23) the buyer, about themselves, "You agreed a settlement: you get
      €7.00 back to your card, and the owner is paid for the rest."; both pages show **You agreed on the
      reported problem** (since `9107ad2`; staff decisions keep **The
      reported problem was decided**). In the staff case, the decision reads
      "agreed by the parties", and on the console's **All** the case no
      longer shows "Offer on the table". Both price cards now show "Total
      €15.00", "Refunded −€7.00", the fee and host2's share of the €8.00 that
      stayed (since `73610c4`, V7-3), and **Bookings → Past** shows €8.00 for
      the buyer.
- [ ] An offer of €0 (nothing back) or of the whole €15 also settles: paying
      the owner in full, or cancelling with a full refund.
- [ ] **Escalation**: locally the window is 10 minutes (`DISPUTE_OFFER_MINUTES`
      in `compose.yaml`; 72 hours deployed). No text names a fixed number of
      hours any more (since `ad9dee9` and `9107ad2`). Wait 10 minutes after
      the report or the last offer, then within a sweep (seconds) both sides
      get "We are deciding now: …" ("There was no agreement in time, so
      Cappy now looks at what happened…"), the card reads "You did not agree
      in time, so Cappy’s staff decide now. You can still agree on an offer
      until then.", and the console lists the case first with "Escalated to
      staff" and the banner "Escalated: the parties did not agree in
      time".

### 26. Late return

Deployed, the owner reports it after the booked end. Locally
`LATE_RETURN_EARLY_MINUTES` opens it as soon as the booking is handed over, so
nobody waits for the end (the app follows the booking's `lateReturnFrom`,
since `b5cdd93`). Use the bandsaw (instant book, 1 hour, €15 an hour,
open every day 08:00 to 22:00):

1. As the buyer, book it for **1 hour** starting about 5 minutes from now.
   It is confirmed at once.
2. Either side marks the hand-over.

- [ ] Host2, before the hand-over. **Expect:** no **Late return** card.
- [ ] Host2, after the hand-over, on the booking page. **Expect:** **Late
      return**: "Came back late? Report it within 24 hours after the end.
      The first 30 minutes are free." and **Report a late return**.
- [ ] **Report a late return**: "How late did Demo bring it back?" Type
      `20` under **Minutes late**, **Report the late return**. **Expect:**
      "The first 30 minutes are free, so there is nothing to report."
- [ ] Type `90`, a note under **What happened (optional)**, report.
      **Expect:** "Reported. Cappy looks at it and tells you both"; the card
      reads "90 minutes late, €30.00 · Cappy is looking at it" (60 minutes
      at €15 an hour, plus a late fee of one hour's rate, €15, capped at €50
      in Germany; with 45 minutes it would be €3.75 + €15 = €18.75).
- [ ] Buyer: **Expect:** "A late return was reported: …", "The owner
      reports that … came back late and asks for €30.00. Nothing is charged:
      we look at it and tell you what we decide."
- [ ] Buyer, on the booking page (since `73610c4`, V7-15). **Expect:** a
      **Late return** card with "90 minutes late, €30.00 · Cappy is looking
      at it" and "The owner says it came back late. Not so? Tell Cappy with
      “Get help with this booking” below, with anything that shows when you
      returned it."; no report button. Once staff decide, the status line
      changes and the text reads "Questions about this decision? Use “Get
      help with this booking” below."
- [ ] Host2 again. **Expect:** no second report button (one late return per
      booking).
- [ ] Staff: on the console, **All** and **Only with open claims**.
      **Expect:** the booking with "1 open claim" (singular since
      `9107ad2`). Open it: **Claims**,
      "Late return: 90 minutes · €30.00 · Open", the note, **Confirm** and
      **Reject**, and "Confirming records the claim; nothing is charged to
      the renter yet."
- [ ] **Confirm**. **Expect:** "Claim confirmed"; both get "Late return: our
      decision on …" ("… confirmed it: €30.00 is owed to the owner. We will
      be in touch about paying it.", always emailed); host2's card reads
      "Confirmed by Cappy"; nothing moves on the card or the payment. On
      another booking, **Reject**: "… did not confirm it: nothing is owed",
      "Not confirmed by Cappy".
- [ ] The report works on an in-progress, completed or disputed booking, and
      only until 24 hours after the end; after that the button is gone.

### 27. Extend

- [ ] As the buyer, book the bandsaw for 1 hour starting about 5 minutes
      from now (instant: confirmed at once). On the booking page. **Expect:**
      "Need it longer? Ask for the time straight after, if it is free." and
      **Extend**.
- [ ] **Extend**. **Expect:** "How much longer?" with **1 h**, **2 h** and
      **4 h**, and "A new booking right after this one, at the listing’s
      price, confirmed at once." Pick 1 h, **Book 1 h more and pay**.
      **Expect:** "Extended", and the app opens the **new** booking: the hour
      straight after the first, confirmed; host2 gets "New booking: …". The
      first booking is unchanged.
- [ ] On the plunge saw (by request, 2 hours at least), extend an accepted
      booking. **Expect:** the sheet offers only **2 h** and **4 h** (never
      less than the listing's minimum, since `9107ad2`) and says "… The owner
      accepts it first."; the toast "Asked for more time", and a new request
      the host answers. Its page reads "This extends your booking before
      it." and links back (since `9107ad2`). The host's email and bell item
      read "Extension request: …", "Your renter wants to extend their
      booking: … for €8.00." (since `1cb2d67`).
- [ ] On the bandsaw (instant book), the toast reads "Extended" even while
      the card step is still confirming it (since `73610c4`, V7-7; before,
      "Asked for more time").
- [ ] **An extension ends with its booking** (since `ad9dee9`). With that
      extension still waiting, host: **Cancel booking** on the first one.
      **Expect:** the extension is declined, "Reason: The booking it extends
      was cancelled." (German and French too), and nothing is charged for
      it. A confirmed extension (the bandsaw) is cancelled with a full
      refund when its first booking is, its page gives the same reason, and
      both sides get "Extension cancelled: …" with the amount back (since
      `1cb2d67`, V7-12).
- [ ] Block the time after: as another renter (script 29) book the hour
      straight after one of your bookings, then **Extend** it. **Expect:**
      "The time straight after is not free, or the booking is not on any
      more." Near the end of the day's hours (22:00) the same refusal.
- [ ] Host's page, a van (quantity) booking, or a booking whose end has
      passed. **Expect:** no **Extend**.
- [ ] Each extension is a booking of its own: it counts towards the daily
      limit (script 29), is paid by card, and can be cancelled on its own.

### 28. The hidden out-of-market listings

Why: only Germany, Austria and Switzerland are open. The demo world has 29
listings in countries that are not: 7 in Amsterdam (NL), 7 in Paris and Lyon
(FR), 8 in Milan and Brescia (IT) and 7 in Lisbon (PT). Since `22b5e0f` the
catalog's hourly job holds every live listing whose place is not in an open
market, or not in its owner's country (`market_not_live`,
`district_not_in_country`), so nobody can find or book them. The job runs
when catalog starts and then about every hour; on a fresh stack it first
runs before the demo world is loaded, so the 29 disappear at its next run,
within about an hour of `make up` (a developer can run `docker compose
restart catalog` to do it at once; `docker compose logs catalog` shows a
"listing … held: market_not_live" line for each).

Explore's search looks only in the city you are in (the place in the
header), so a search from Berlin never shows Amsterdam or Milan, held or
not. The checks below search where the hidden listings are, and open them
directly.

- [ ] As the demo buyer, open `/listing/n-l3` (the Amsterdam sander).
      **Expect:** "That listing is not here". (Before the job has run it
      opens; that is how you know the check can fail.)
- [ ] On Explore, tap the place in the header and pick **Amsterdam**; search
      `sander`. **Expect:** no *Festool ETS 150 sander + extractor*
      (Oud-West). Pick **Milan** and search `mitre`. **Expect:** no *Makita
      mitre saw + stand* (Lambrate). The city list still offers Amsterdam
      and Milan (they are places), counting no listings there once the job
      has run.
- [ ] The same search can find something: pick **Wien** and search `drill`.
      **Expect:** the *Bosch cordless drill set* (a live Austrian listing).
- [ ] As staff, **Waiting for a check**. **Expect:** the 29 listed with
      "Not live: Cappy is not open in that country yet. Move it to a place in
      an open market to publish it." and **no Approve** button (approving is
      refused).
- [ ] The Wien drill set (*Bosch cordless drill set*, €3 an hour) and the
      Zürich track saw (*Makita track saw…*, CHF 9 an hour) stay visible:
      their owners are Austrian and Swiss and their countries are open.
- [ ] Their owners have no sign-in, so the owner's side (Earn's **Not
      live** pill and the release on moving the listing) cannot be seen on
      them. A tester's own listing can no longer be put outside their
      country: the form offers only their own country's districts, and the
      server refuses another ("Pick a district in your own country.").

### 29. Daily booking limit and switching renter accounts

The rule (`booking/settings.py` `max_requests_per_day`): each **renter** can
start at most **10 bookings in 24 hours** (a rolling window), whatever became
of them (paid, cancelled, declined, lapsed, extensions too). It is counted
per renter, not per host or listing. Stripe mode also allows at most 3
unpaid bookings at once (script 5).

- [ ] As the demo buyer, make bookings until the 11th in a day. **Expect:**
      refused with "that is a lot of booking requests for one day; try again
      tomorrow". Nothing resets it but time (or a clean rebuild,
      [A6](#a6-resetting-the-local-data)).
- [ ] `make e2e` no longer counts against the demo buyer (since `32338dd`
      it books as a buyer of its own).
- [ ] **Switch renter** to go on testing: sign out, then under the sign-in
      form **Continue as demo host** (can rent the second host's bandsaw,
      van and studio), **Continue as demo host 2 (new owner)** (can rent the plunge saw),
      or **Continue as demo staff** (a member too; can rent any of them).
      Nobody can book their own listing. Or make a fresh account
      ([A1](#making-a-fresh-account)): it gets its own 10 a day.
- [ ] To be renter and host at once, use two browsers or Chrome profiles
      ([A3](#a3-before-you-start-tips-that-save-time)): all tabs of one
      browser follow one account.

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
- `DISPUTE_OFFER_MINUTES: "10"` (`booking`, since `b5cdd93`): a dispute the
  two sides do not settle goes to staff after 10 minutes (deployed: 72
  hours), and each new offer restarts the 10 minutes (script 25).
- `LATE_RETURN_EARLY_MINUTES: "100000"` (`booking`, since `b5cdd93`): the
  owner may report a late return as soon as the booking is handed over
  (deployed: 0, from the booked end; script 26).

These shortcuts never reach real people: deployed (staging, prod) a service
refuses to start with `MIN_LEAD_MINUTES` under 60, `START_EARLY_MINUTES`
above 60, `AUTO_COMPLETE_AFTER_HOURS` under 24, `DISPUTE_OFFER_MINUTES`
under 72 hours, `LATE_RETURN_EARLY_MINUTES` above 0 or
`LATE_RETURN_CLAIM_HOURS` under 24 (`unsafe_reasons` in
`matching/settings.py` and `booking/settings.py`).

**Not shortened** (so the time must really pass, or a developer changes the
setting):

| Step | Rule | Setting (service) |
|---|---|---|
| Unpaid booking expires | 30 min | `PAYMENT_TIMEOUT_MINUTES` (booking) |
| Host must answer | 24 h, never past the start | `ANSWER_WITHIN_HOURS` (booking) |
| Auto-complete | 48 h after the end | `AUTO_COMPLETE_AFTER_HOURS` (booking) |
| No-show | from the start (the buyer reporting the host) or start + 30 min (the host reporting the buyer), until start + 2 h; only if nobody marked the hand-over | fixed in code (`booking/routes.py` `NO_SHOW_GRACE`, `NO_SHOW_REPORTABLE`) |
| Dispute | the buyer, from the start (at once once handed over, since `42c777c`) until the booking completes | fixed in code (`booking/routes.py`) |
| Late return, the end of the window | until 24 h after the booked end (its start is shortened locally, above); the first 30 min are free | `LATE_RETURN_CLAIM_HOURS` (booking); grace fixed in code |
| Booking requests per renter | 10 in 24 h | `MAX_REQUESTS_PER_DAY` (booking) |
| Review window | 14 days after the end | fixed in code |
| Weekly schedule roll-on and the "no free time next week" notice | hourly | fixed in code (`catalog/jobs.py`) |

**Testing no-shows and disputes.** You need an accepted booking whose start
has passed:

1. As the buyer, book a start about 5 to 10 minutes from now on the plunge
   saw (the host accepts) or the bandsaw (instant); both are open every day
   from 08:00 to 22:00 since `22b5e0f`, weekends included (on a clean
   stack since `1cb2d67`: no seeded dated window closes a morning). Outside those
   hours, add a window first as their owner (Earn → **Edit** → **Set my own
   weekly hours** or **Pick the dates myself**, script 15).
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
  a new sign-in setting for it. The second host's studio is held again
  (script 19 approves it). Clear the site's data in the browser too
  (DevTools → **Application** → **Storage** → **Clear site data**), or you may
  see a stale session.

Reset after anything that breaks the demo for others: deleting or suspending
a demo account, taking down the host's listing, or filling the host's
calendar. The demo buyer's 10 bookings a day are not reset by `make up`
(script 29).

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

`make up` prints the API, the four demo accounts with their password, and a
pointer to this guide when it is done (since `42c777c`).

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
| `up` | Build and start the stack, wait for health, copy `.local/web.env` to `web/.env.development.local`, then `seed-demo`, then print the API and the four demo accounts | `.env` |
| `down` | Stop the stack, keep data | |
| `clean` | Stop it, delete volumes and `.local/*.env` | |
| `logs` | Follow the six services' logs | stack |
| `seed-demo` | Load the demo world (additive; local and staging only), the demo buyer, second host and staff profiles and the second host's three listings (`local/demo_profiles.py`, through the API; skipped once it owns anything), and in Stripe mode verified test payout accounts for demo owners | stack |
| `codes` | The last 20 sign-up and reset codes from cognito-local's log, each with the email it went to | stack |
| `confirm` | `make confirm EMAIL=… [ADMIN=1] [LEAD=1]`: mark a local account's email verified (so Cappy emails it), confirm it if the code was never typed, with `ADMIN=1` add it to the `admin` group, and with `LEAD=1` (since `22b5e0f`) to `admin` and `admin-lead` (creating the group if needed) for staff-lead refund limits (`local/confirm.py`) | stack |
| `test` | `ruff check`, `ruff format --check`, `pytest -q` | nothing |
| `test-pg` | `pytest` including the Postgres tests, against the compose Postgres on 5433 | `make up` |
| `test-stripe` | Start `stripe-mock` on 12111 and run the `stripe_mock` tests | Docker |
| `e2e` | The whole journey against the running stack (`local/e2e.py`) | `make up` |
| `web` | `npm ci && npm run build` in `web/` | Node |
| `infra-validate` | `terraform fmt -check` and `validate` in every root | Terraform |
| `infra-local` | Apply `infra/localstack` (the event fabric) to LocalStack and prove its routing | `make up`, Terraform |
| `openapi` | Regenerate `docs/api/*.json` from the services' code | |
| `bench` | Since `42c777c`: candidate and free-text search at 100 000 synthetic listings in a throwaway database `scale` on the compose Postgres, dropped afterwards (`backend/services/catalog/bench/candidates.py`; results in `docs/bench.md`) | `make up` |
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
| `.local/web.env` → `web/.env.development.local` | no | The Cognito endpoint and client id, and `VITE_DEMO_ACCOUNTS`, for the Vite dev server. Written by bootstrap; only `make up` copies it, so after a bootstrap run any other way, `cp .local/web.env web/.env.development.local` and restart `npm run dev` |
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
| `make test` | Lint, format and every unit and API test (SQLite, in-memory bus, a throwaway JWKS). Includes the subscription consistency test (D-13), the privacy register test (D-11) and, since `e2e77ab`, `notifications/tests/test_texts_every_kind.py`, which renders every notification kind in EN, DE and FR and fails on English left in a translation, a missing or unfilled placeholder, two full stops, or the wrong space before French punctuation (a new text must pass it) | nothing |
| `make test-pg` | Also the Postgres tests: migrations build exactly the models, concurrency, the no-double-booking constraint | `make up` |
| `make test-stripe` | The Stripe calls against stripe-mock | Docker |
| `make e2e` | Sign up, list with a photo, search, book, pay, accept, hand over, complete, pay out, rate, review, emails, plus the edge refusing what it must. Since `32338dd` it signs up a second buyer of its own for the contested window and deletes it at the end, so it never touches the demo accounts. In Stripe mode it needs `sk_test_` keys and confirms with Stripe's test card | `make up` |
| `make load`, `load-spike`, `load-mixed`, `load-soak` | Concurrency: no errors, no double booking, latency percentiles. A laptop finds errors, not capacity numbers | `make up` |
| `make infra-validate`, `make infra-local` | Terraform validates; the event fabric applied to LocalStack routes each event type correctly | Terraform (`infra-local` also `make up`) |
| `make bench` | How fast the candidate search (25 km over 7 days, 500 km over 30 days) and two free-text searches are at 100 000 listings: the mean of 10 runs after a warm-up, printed per query. For another size: `cd backend && uv run python services/catalog/bench/candidates.py 20000`. It compares changes on one machine, it does not size production; add a row to `docs/bench.md` (date, commit, conditions) when search code changes | `make up` |

Web checks (`cd web`; CI runs all six after `npm ci --ignore-scripts`,
`npx tsc --noEmit -p .` and `npm run build`):

| Script | What it checks |
|---|---|
| `npm run check:i18n` | Every German and French text keeps its English key's `{placeholders}`; French and German have the same keys; every literal `t('…')` in the app has a German (and so French) entry; French typography, a no-break space (U+00A0) before ":" and a narrow one (U+202F) before "; ? !", in the catalogue (since `090c890`; URLs, placeholders and clock times left out) and in the French prose of `Legal.tsx` (since `73610c4`) |
| `npm run check:flags` | The rollout bucket matches the server's |
| `npm run check:size` | The first-paint JavaScript is under 170 kB gzipped (run after a build) |
| `npm run check:a11y` | Every `<img>` has `alt`; nothing clickable is smaller than 24 × 24 px |
| `npm run check:attempt` | Idempotency keys: a retry after an unknown outcome reuses the key, a known outcome or changed body gets a new one |
| `npm run check:money` | `moved()` (`web/src/domain/pricing.ts`, since `73610c4`): what a booking charged, refunded, and the fee and owner's share of what stayed, for a renter no-show, a part refund, a withdrawn or declined request and a cancellation with or without a refund |

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
   latest in booking, `0018_decisions_on_reviews.py` in catalog,
   `0009_currency_upper.py` in payments, `0007_revocations.py` in
   notifications). Expand and contract: new code must work with the schema
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
   translated in the app through the same catalogues, so add those too; a
   refusal code the reader must understand gets its own line in `CODE_TEXT`
   (`web/src/data/repo.ts`), and a server sentence with no code one in
   `MESSAGE_TEXT` (since `73610c4`), keyed on the exact sentence. People's
   own words in a notice (a reason, a note) pass through `quoted` in
   `texts.render`, so French typography is never applied to them. A validation error lists every field in
   `error.fields` (`cappy_common/errors.py`, since `42c777c`): raise
   `ValueError` in a pydantic validator, or pass `fields=` to an `ApiError`,
   and show them under the form's fields (`ApiError.fields`).
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
confirms it if the code was never typed; add `ADMIN=1` to make it staff,
or `LEAD=1` to make it a staff lead (both groups; then sign out and in
again). The script is `local/confirm.py`: it reads the
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
| The web app: run, checks, what is stored on the device, languages, store shells | `web/README.md` (rewritten in `2257182`, GD-1) |
| The API | `docs/api/*.json` |
| The demo world | `backend/libs/cappy_common/cappy_common/fixtures/seed.json`, the source since `42c777c` (edit it by hand; the old export script is gone): owners with invented trader details for the businesses, listings, slots, reviews, and `listingAddresses`, invented hand-over addresses per listing; the demo accounts in `local/bootstrap.py` (`DEMO`), their profiles and the second host's listings in `local/demo_profiles.py` |
| Markets (which countries are open, currency, thresholds) | `backend/libs/cappy_common/cappy_common/markets.json` |
| How results are ranked | `GET /api/ranking` (the ranker's own weights, `matching/domain/match.py` `W`, `SIGNALS`), shown on `/legal/ranking` |
| Search speed | `docs/bench.md` (`make bench`) |
| What behaves differently on the local stack | `docs/runbook.md`, "Local stack only" |

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
