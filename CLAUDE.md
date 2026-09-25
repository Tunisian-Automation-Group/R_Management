# Working in this repository

Read these first, every session:

1. **[`docs/GOAL.md`](docs/GOAL.md)** — the brief, verbatim, and what
   "production ready" means. It does not change.
2. **[`docs/PLAN.md`](docs/PLAN.md)** — the living plan. Pick up the first
   unfinished step. Tick steps with the commit that did them; add, drop or
   reorder steps as needed and record why in its change log.
3. **[`docs/adr/`](docs/adr/)** — why the system is built the way it is.
   Changing a decision means a new ADR, not a silent edit.

## Rules

- Work on the `prod-readiness` branch. Commit as the repo's configured identity
  (tunisian-automation). **Never push** unless the user says so.
- Secrets never enter the repository: LocalStack auth token, Stripe keys and
  anything else live in the untracked `.env` (see `.env.example`).
- Every commit leaves `make test` green. New behaviour comes with tests.
- Nothing demo-only runs in a service process (ADR 0010).

## Layout

```
backend/   Python services (uv workspace): gateway, catalog, matching, booking,
           payments, notifications, and the shared cappy_common library
web/       React PWA (Vite)
infra/     Terraform for AWS
docs/      goal, plan, review, ADRs, runbook
```
