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
