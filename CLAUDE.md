# Working in this repository

Read these first, every session:

1. **[`docs/GOAL.md`](docs/GOAL.md)** — the brief, verbatim, and what
   "production ready" means. It does not change.
2. **[`docs/PLAN.md`](docs/PLAN.md)** — the living plan. Pick up the first
   unfinished step. Tick steps with the commit that did them; add, drop or
   reorder steps as needed and record why in its change log.
3. **[`docs/adr/`](docs/adr/)** — why the system is built the way it is.
   Changing a decision means a new ADR, not a silent edit.

## Living docs — keep them true

These describe the system as it is now. Any change that alters what one of
them says updates it **in the same commit** (builders and agents included):

- **[`docs/FEATURES.md`](docs/FEATURES.md)**: every feature, where it lives,
  and its provider seam (for example ID checks, payments, email, push, maps),
  with what swapping it for another third party takes.
- **[`docs/INFRA.md`](docs/INFRA.md)**: the AWS resources and local stack,
  per cell and environment, the kill switches, costs, and what is validated
  vs applied (never real AWS, GOAL 12).
- **[`docs/FLOWS.md`](docs/FLOWS.md)**: how the app flows work from the
  user's side (welcome, sign-in, booking, payment, hand-over, disputes,
  moderation, deletion), on web and in the store apps.
- **[`docs/GUIDE.md`](docs/GUIDE.md)**: how to run Cappy locally and test
  every feature by hand (testers), and how to set up, run, debug and test it
  (developers): accounts, payment modes, click paths, commands.
- **[`docs/DATA.md`](docs/DATA.md)**: services, their tables, the events
  between them, who reads what, retention and personal data.

After each round of work, a docs-sync agent reads the round's commits
(`git log -p <from>..HEAD`) and brings all five docs up to date, so a
builder that missed one is caught.

## UI work

Any agent building or reviewing a screen first loads the `frontend-design`
skill and reads [`.claude/skills/cappy-ui/SKILL.md`](.claude/skills/cappy-ui/SKILL.md)
(spacing, type, colour pairing in light and dark, component specs, motion) and
runs its review checklist at 390, 375, 360 and 430 px wide in light and dark.
Light is the default theme; dark is opt-in.

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
