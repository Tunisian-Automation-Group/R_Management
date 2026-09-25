# The goal

This file is the north star for the `prod-readiness` work. It does not change;
[`PLAN.md`](PLAN.md) changes as the work moves.

## The brief, verbatim

> take a look at the code and tell me what do you think, these will work
> together and they need to scale to millions of users. identify all the
> problems, be critical, you are the principal engineer in the project and will
> launch this. /goal principal level, scalable code to millions of users, will
> be deployed in AWS, needs to work seamlessly together and have all the
> features needed in the app, easy to test locally also, easy to deploy,
> follows best practices of software engineering, software architecture and
> infrustructure best practices and keep working until it is ready and commit
> with the tunisian-automation account but do not push for now.Keep working
> until you are confident this is Prod ready and if any 3rd party services can
> be used like Stripe for payment and other things than we can do that make the
> best decision always.
> create a new branch if you want to do work

Standing instructions from the same conversation:

- Keep a living plan of the steps; add, remove and reorder steps as needed.
- Change anything: delete code, add code, add tests. Principal-engineer
  authority over every decision.
- Commit as the tunisian-automation account (already the repo's identity).
  **Do not push.**
- LocalStack (with a Pro token) is available for local AWS parity. Secrets
  never enter the repository.

## What "production ready" means here

Each line is checkable. The work is done when every box in `PLAN.md`'s
definition-of-done section is ticked with evidence (a passing test, a command
that works, a file that exists).

1. **Safe.** No unauthenticated destructive or state-changing endpoint. No
   trusted identity header. No default credentials. No demo behaviour in a
   production process. Security headers, input limits, rate limits.
2. **Correct.** No double booking under concurrency. No lost or phantom
   events. No startup path that deletes data. Idempotent consumers and
   webhooks.
3. **Scales.** No request, on the server or the client, whose cost grows with
   the size of the database rather than the size of the answer. Everything
   listed is paginated. Stateless services that scale horizontally.
4. **Complete.** Sign-up with email verification and password reset; listing
   with photos; search; booking with payment (authorise, capture, pay out,
   refund); notifications; reviews; saved listings. Working end to end.
5. **Operable.** Schema migrations. Liveness and readiness. Structured logs
   with request ids, traces, alarms. Graceful shutdown.
6. **Deployable.** All AWS infrastructure in Terraform. CI that lints, tests
   and builds; CD that migrates and deploys without long-lived keys.
7. **Testable locally.** One command brings up the whole system against
   emulated AWS; one command runs every test; unit tests need no Docker.
8. **Documented.** How to run, test, deploy and operate it; why it is built
   the way it is (ADRs).

## The brief, extended (2026-09-25, verbatim)

> get the webhook and add it to the .env file, and the /goal is to keep working on the code until you are 100% that this can be in production and used by millions of users and can be scaled like uber or any of these apps, keep working for hours until you know it is fine and have an agent seperate from you verifying your work opening browser testing each and every functionality and again and again, this is the goal until you keep finding and solving all bugs. this is an app that will be in app store and web and google stores and so on, keep working until you verify everything with the verify agent.

What this adds to "production ready":

9. **Verified by someone else.** A separate agent, not the one who wrote the
   code, drives the real app in a browser through every feature, again after
   every round of fixes, until a full pass finds nothing.
10. **Store ready.** The same app ships on the web, the App Store and Google
    Play, and meets what those stores require: in-app account deletion,
    privacy policy and terms, data export (GDPR), and working deep links.
11. **Payments for real.** The Stripe test-mode flow (card form, webhook,
    capture, refund, payout) works end to end, not only the fake provider.

## The brief, extended again (2026-09-26, verbatim)

> do not apply on real aws or anything, also make sure that only signed in users see the app and keep looking at both web version and app version we cannot see anything until logged in and we need welcome screen for app for first timers, also keep looking and searching on the internet for how these apps look and keep working on back and front for web and app for at least 3 or 4 hours until every edge case known is soved in these apps, each time an agent check both versions and another searches and add tasks based on what these big  apps work on best practices and so on, keep this in a loop like this until we are done and solved everything that is the goal and each time the tasks are put in a doc under @docs/

What this adds:

12. **Nothing is ever applied to real AWS** (or any real cloud account).
    Everything runs and is proven locally. Terraform is only validated,
    and applied only to LocalStack.
13. **Signed-in only.** Nothing of the product (listings, search, people,
    prices) is visible or reachable before sign-in, on the web or in the
    apps, and the server enforces it. The only public things are what law
    or the stores require: Impressum, privacy, terms, the report form (DSA
    Art. 16) and the account-deletion page (Google Play).
14. **A welcome screen** for first-time users of the app and the web.
15. **The loop.** Each round:
    - a research agent studies how the big apps do it and adds tasks to
      `docs/TASKS.md`;
    - builders implement them on backend, web and app;
    - a separate verifier agent checks both the web version and the app
      version (the phone layout and the store shells).

    It repeats until a round finds nothing.

## The brief, extended (2026-09-26, verbatim)

> Also to keep in mind this is targeted to all europe, the us and canada so add that so the agents know this

What this adds:

16. **Markets: all of Europe, the United States and Canada.** Germany is
    the first market, not the only one. Every design and every task
    assumes more than one market:
    - **Money:** several currencies (EUR, GBP, CHF, the Nordic and
      Eastern European currencies, USD, CAD), with prices stored in minor
      units per currency and never converted silently.
    - **Tax:** VAT per EU country, UK VAT, Swiss VAT, US sales tax (by
      state) and Canadian GST/HST/PST/QST, plus the matching platform
      reporting (DAC7 in the EU, 1099-K in the US, Canada's platform rules).
    - **Law:** GDPR and UK GDPR, the DSA, consumer law per country, CCPA/CPRA
      and the other US state privacy laws, PIPEDA and Québec Law 25,
      accessibility (EAA/BFSG in the EU, ADA in the US, AODA and the ACA in
      Canada).
    - **Language and format:** English, German, French (France and
      Québec) and the other main European languages over time; locale
      dates, numbers, addresses, phone numbers, and km or miles.
    - **Data and payments:** where each market's data lives (EU data in
      the EU), and which Stripe platform entity serves which market.
    - **Places:** time zones and addresses everywhere; no assumption that
      a city is Berlin or that a place is a Berlin district.
