# Cappy

A marketplace for idle capacity: machine hours, workshop time, 3D printers,
vans and warehouse space, rented by the hour from the people and firms who own
them. People browse and book in a web app (and an installable PWA); owners list
what they have and get paid through Stripe Connect.

## Architecture

```
browser ──► CloudFront + WAF ──► S3            the web app (web/)
                   │         └──► S3            /media/*  listing photos
                   └── /api/* ──► ALB ──► gateway ──► catalog  ─┐
                                              (allow-list)├► matching ├─ Aurora PostgreSQL
                                                          ├► booking  │  (a database each)
                                                          └► payments ┘
   Cognito (sign-in) ◄─ browser              SNS ──► SQS per consumer (+DLQ) ──► catalog, booking,
   Stripe (cards, payouts) ◄─ payments                                            payments, notifications ──► SES
```

- **Identity**: Cognito. Every service verifies the access token itself; no
  trusted headers.
- **catalog**: owner profiles, listings, windows, photos, search, reviews and
  saved listings.
- **matching**: ranks and prices a bounded candidate set, skipping booked
  windows. It is stateless.
- **booking**: the booking lifecycle. A Postgres exclusion constraint makes
  double booking impossible.
- **payments**: Stripe Connect. The card is authorised when the booking is
  made, captured when the owner accepts, and transferred to the owner on
  completion.
- **notifications**: emails through SES.
- **Events**: a transactional outbox → SNS → one SQS queue per consumer.
  Handlers are idempotent.
- **Trust**:
  - messages per booking, with contact details masked until the booking is
    accepted;
  - blocking;
  - reports and moderation (DSA notice-and-action, statements of reasons,
    audit log);
  - check-in and check-out photos;
  - identity verification (Stripe Identity) for high-value bookings;
  - fraud limits and a review queue for suspicious new listings.
- **Store-ready**: in-app account deletion and data export, a minimum app
  version with a forced update, push notifications, and emails in English,
  German and French.

The reasoning behind each choice is in [`docs/adr/`](docs/adr). The review that
started this work is in [`docs/review/`](docs/review), and the plan with its
evidence is in [`docs/PLAN.md`](docs/PLAN.md).

## Run it locally

Needs Docker, [uv](https://docs.astral.sh/uv/), Node 22 and Terraform.

```sh
cp .env.example .env        # add your LOCALSTACK_AUTH_TOKEN
make up                     # everything, migrated and seeded
cd web && npm install && npm run dev   # http://localhost:5173
```

`make up` runs Postgres, LocalStack (S3, SNS, SQS, SES), cognito-local and every
service. It then loads a demo world. Sign in as `host@demo.cappy.local`,
`buyer@demo.cappy.local` or `staff@demo.cappy.local` (the moderator) with
`Demo-pass-123!` (local only), or tap "Continue as demo …". How to test every
feature by hand: [`docs/GUIDE.md`](docs/GUIDE.md). Sign-up codes are printed by
`make codes`. Payments use a fake provider unless Stripe test keys are in
`.env`.

## Test

| Command | What it proves | Needs |
|---|---|---|
| `make test` | lint and every unit and API test | nothing |
| `make test-pg` | plus migrations vs models, concurrency, the no-double-booking constraint | `make up` |
| `make test-stripe` | the Stripe calls against stripe-mock | Docker |
| `make e2e` | the whole journey through the running stack: sign up, list, book, pay, accept, complete, pay out, rate, review, emails | `make up` |
| `make infra-validate` | every Terraform root validates | Terraform |
| `make infra-local` | the Terraform event fabric applied to LocalStack routes each event type to the right queues | `make up` |

CI runs all of it on every pull request (`.github/workflows/ci.yml`).

## Deploy

See [`docs/runbook.md`](docs/runbook.md). In short: `infra/bootstrap` is applied
once per account. After that, a merge to `main` deploys to staging, and prod
is deployed by hand behind a required reviewer
(`.github/workflows/deploy.yml`). Images are tagged by commit, migrations run
before any service rolls, and ECS rolls back a release that doesn't become
healthy.

## Layout

```
backend/   Python 3.12 uv workspace: libs/cappy_common + services/*; one Dockerfile
web/       React 19 + Vite + TanStack Query PWA
infra/     Terraform: platform module, envs/{staging,prod}, bootstrap, localstack proof
local/     compose bootstrap, service runner, e2e journey
docs/      goal, plan, TASKS (working list), resilience (failure catalogue), research,
           ADRs, review, runbook, SLOs, generated API reference (docs/api)
```
