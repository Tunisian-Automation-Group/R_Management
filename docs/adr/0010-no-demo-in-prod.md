# 0010. Demo data is a dev-only seeding tool

## Context
Seeding on startup, fingerprint-driven rebuilds, simulated hosts, a seeded
inbox request, a seeded account and a public reset endpoint are all runtime
behaviour today, several on by default.

## Decision
None of it runs in a service process. The demo world is loaded by an explicit
command (`make seed-demo`, or the `seed` one-off task), which refuses to run
unless `APP_ENV` is `local` or `staging`, never deletes, and skips anything
already present. There is no reset endpoint. Simulated host replies are gone:
a host with no account cannot receive bookings (they have no payout account).
Startup refuses to boot in `prod` with any demo setting enabled.
