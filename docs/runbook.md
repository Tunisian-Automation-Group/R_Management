# Runbook

## First deploy of an environment

1. **Account bootstrap** (once per AWS account, by a person with admin rights):
   `cd infra/bootstrap && terraform init && terraform apply -var github_repo=<owner>/<repo>`.
   This creates the state bucket and the GitHub OIDC roles `deploy-staging` and
   `deploy-prod`, which only the deploy workflow running from `main`, inside
   that GitHub environment, can assume. In Billing, activate the `env` tag as
   a cost allocation tag, so each environment's budget sees its own spend
   (R2-4).
2. **GitHub**: create the environments `staging` and `prod`, and require a
   reviewer on `prod`. In each environment set these variables:
   - `AWS_DEPLOY_ROLE_ARN`, from the bootstrap output (`deploy-<env>`)
   - `AWS_IMAGES_ROLE_ARN`, from the bootstrap output (`images-<env>`): image builds push with it and can do nothing else; the web app is built with no AWS access (P-2)
   - `ZONE_ID`, the Route 53 hosted zone of the domain
   - `ALARM_EMAIL`
   - `LEGAL`, the operator on invoices and in the app's Impressum, privacy
     policy and DSA contact point, as JSON:
     `{"company":"…","address":"…","email":"…","vat_id":"…","tax_number":"…","register":"…"}`.
     Deploys stop without it, and the web build refuses to build without the
     company, address and email (R2-1).
   - `APPS` (once the store apps ship): `{"apple_team_id":"…","android_sha256":"AB:CD:…","app_store_url":"…","play_store_url":"…"}`.
     Without it no app-link files are published (a placeholder would verify nothing).
   - `SWITCHES` and `FEATURE_FLAGS` (optional; see "Kill switches")

   And this environment **secret**:
   - `PAGER_ENDPOINT`: the pager's SNS HTTPS integration URL (PagerDuty,
     Opsgenie, or an Incident Manager response plan). Page-level alarms go
     there as well as to `ALARM_EMAIL`; a prod plan warns without it
     (see "Severity and on-call").

   Add the `LOCALSTACK_AUTH_TOKEN` repository secret so CI runs the e2e.
3. **DNS**: the domain in `infra/envs/<env>/main.tf` must live in that hosted zone.
4. **Stripe**: once, after the first apply has created the secret
   `cappy-<env>/stripe`, set it by hand. It is never set in Terraform or the
   repository:
   ```sh
   aws secretsmanager put-secret-value --secret-id cappy-<env>/stripe --secret-string \
     '{"STRIPE_SECRET_KEY":"sk_live_…","STRIPE_PUBLISHABLE_KEY":"pk_live_…","STRIPE_WEBHOOK_SECRET":"whsec_…"}'
   ```
   In the Stripe dashboard, add a webhook endpoint
   `https://<domain>/api/payments/webhooks/stripe` for the events
   `payment_intent.amount_capturable_updated`, `account.updated`, `charge.dispute.created`, `charge.dispute.updated`, `charge.dispute.closed`, `charge.dispute.funds_withdrawn`, `charge.dispute.funds_reinstated`, `identity.verification_session.verified` and `identity.verification_session.requires_input`. Enable
   Connect with Express accounts, and Stripe Identity.
5. **Push notifications** (once, when the store apps are ready): create two SNS
   platform applications, APNs with the Apple push key (`.p8`, key id, team id)
   and FCM with the Firebase service-account JSON (FCM HTTP v1). Pass their ARNs
   as `push_app_arns`. Without them pushes are only logged.
6. **SES**: request production access for the region, so mail reaches
   addresses that aren't verified. DKIM, SPF and DMARC records are created by
   Terraform.
7. Run the `deploy` workflow.

## Releasing and rolling back

A release is a commit on `main` whose `ci` run passed (R2-8). A green CI run
on `main` deploys it to staging by itself; the `deploy` workflow's first job
refuses any sha without a successful `ci` run.

- **Prod**: Actions → deploy → Run workflow, `env: prod`, `release:` the sha
  staging runs (empty means the latest on `main`). The prod environment asks
  a reviewer.
- **Rollback**: the same, with the previous release's sha. Its images
  already exist in ECR, so only Terraform and the roll run (minutes). The
  database is not rolled back: every migration is **expand/contract**, so the
  previous release runs against the newer schema:
  1. *expand*: add columns and tables, nullable or with defaults; the code
     writes both old and new;
  2. *migrate*: backfill in a later release;
  3. *contract*: drop what nothing reads any more, one release after that.

  A migration that cannot be undone this way (dropping data) is its own
  release, after a restore rehearsal.
- **Web**: the previous release's hashed files stay published for 30 days
  (R2-9), so tabs opened before a deploy keep working.

## A deploy failed

- **Migration step failed**: nothing rolled out. The migrate task's logs are
  in CloudWatch under `/cappy/<env>/migrate`. Fix it, then deploy again.
  Migrations must be backwards compatible (expand, then contract in a later
  release), because the old code keeps running against the new schema until
  the roll completes.
- **Services did not stabilise**: the ECS circuit breaker has already rolled
  back to the previous task definition. Look in `/cappy/<env>/<service>`.

## Alarms

| Alarm | First look |
|---|---|
| `api-5xx-rate` | Logs of the gateway and services for `ERROR`. Every line carries `requestId`, which is also in the client's `x-request-id` response header. |
| `api-p99-latency` | Container Insights CPU per service, and Aurora `ServerlessDatabaseCapacity`. |
| `<service>-dead-letters` | An event failed 12 times (about 2 h of backoff). Read it: `aws sqs receive-message --queue-url <dlq>`. Fix the cause, then redrive with `aws sqs start-message-move-task --source-arn <dlq-arn>`. Handlers are idempotent, so redriving is safe. |
| `outbox-set-aside` | A service could not publish an event 20 times (SNS down or refusing it); the change is committed, its event is not sent. Find `OUTBOX_SET_ASIDE <id> <type>` in the service's logs, fix the cause, then send it again: `UPDATE outbox SET attempts = 0 WHERE id = '<id>' AND sent_at IS NULL;` in that service's database (the relay picks it up within seconds). |
| `<service>-queue-age` | The consumer is down or too slow. Check the service is running and its logs. |
| `db-cpu`, `db-at-max-capacity` | Raise `db_max_acu`; find the slow queries in Performance Insights. |

## Severity and on-call

| Severity | What | Goes to | Answer |
|---|---|---|---|
| **SEV1** | Everyone or money: the site is down, bookings or payments fail for many, a data breach, a security incident | Page (pager + mail) | At once, day or night; incident commander named in 15 min |
| **SEV2** | Part of the service or some people: one journey failing, payouts or mail stuck, the error budget burning fast | Page | Within 30 min |
| **SEV3** | Degraded but working: slow, capacity near its limit, a slow budget burn, email reputation | Ticket (mail) | Next working day |

Page-level alarms (topic `…-alarms`): `api-5xx-rate`, `<service>-dead-letters`,
the canary, the fast burn-rate and per-journey page alarms, root-account use
and high GuardDuty findings. Everything else is a ticket (topic `…-tickets`).

**On-call** (the owner names the rota; one primary and one secondary, a week
each, handed over in writing):
- keep the pager on and a laptop within 15 minutes; acknowledge within 5;
- for SEV1/SEV2, name an **incident commander** (the first responder until
  handed over), open an incident record from
  [`incidents/TEMPLATE.md`](incidents/TEMPLATE.md), and post updates every 30
  minutes where the team sees them;
- mitigate first (kill switch, rollback, scale), then find the cause;
- every SEV1 and SEV2, and every burn of more than half an SLO's monthly
  budget (`slo.md`), gets a blameless postmortem within 5 working days,
  from [`incidents/POSTMORTEM.md`](incidents/POSTMORTEM.md).

## Security or personal-data incident (a breach)

A breach is any loss of confidentiality, integrity or availability of
personal data: a leaked export, a wrong person seeing a booking, a stolen
credential, a lost backup, ransomware. Treat a suspected one as real until
shown otherwise.

1. **Contain** (SEV1): rotate the exposed credential, revoke sessions
   (`POST /api/me/sign-out-everywhere` for affected people; Cognito
   `AdminUserGlobalSignOut` in bulk), switch off the affected feature, block at
   the WAF. Keep the evidence: CloudTrail (object-locked, a year), the
   service logs, GuardDuty findings. Do not delete anything.
2. **Record it** in the incident register at once, from
   [`incidents/TEMPLATE.md`](incidents/TEMPLATE.md): the time you became
   aware starts every clock below.
3. **Assess** with the privacy lead: whose data, which categories (ID
   checks and messages are high risk), how many people, which countries,
   and whether it is likely to harm them.
4. **Notify**, by the rule that applies (counsel confirms each case):

   | Law | Who | When |
   |---|---|---|
   | GDPR Art. 33 (EU, and UK GDPR) | The lead supervisory authority (Germany: the Berlin commissioner for an establishment there), unless it is unlikely to be a risk | Within **72 hours** of becoming aware; late ones say why |
   | GDPR Art. 34 | The people affected | Without undue delay, when the risk to them is high |
   | Switzerland (revFADP Art. 24) | The FDPIC | As soon as possible, when the risk is high |
   | Canada, PIPEDA | The Privacy Commissioner and the people affected | As soon as feasible, for a real risk of significant harm; keep a record of every breach for 24 months |
   | Québec, Law 25 | The CAI and the people affected | Promptly, for a risk of serious injury; keep a register of every incident |
   | US states | The people affected, some attorneys general | By each state's law, often 30–60 days; counsel lists the states |
   | Stripe, Apple, Google | Each, if their data or keys are involved | By their terms |

5. **Tell processors and partners** whose data it was (the DPA terms), and
   **write the postmortem**. Keep the register entry for at least 5 years.

## A chargeback

A card holder disputed a charge with their bank. With separate charges and
transfers the platform carries it (R2-3). Payments follows every
`charge.dispute.*` event from Stripe:

- **Opened**: the owner's payout is held (a completed booking's payout is
  kept, not dropped), and a `chargeback` ticket opens.
- **Staff answer it** before the evidence deadline: `GET
  /api/admin/payments/chargebacks` lists the open ones, soonest deadline
  first. Gather the booking's case (`/admin/case/<booking>`): the timeline,
  the hand-over photos (signed links), the messages, the renter's
  confirmation. Then `POST /api/admin/payments/<booking>/dispute-evidence
  {"text": "…", "links": ["…"]}` sends it to Stripe and is audited.
  ponytail: text and links only; attach photos as files in the Stripe
  dashboard until uploading them is built.
- **Won** (or a warning the bank closed): the hold ends and a held payout is
  paid out, with its invoice.
- **Lost**: the money went back to the card holder. An owner already paid
  gives their share back through a transfer reversal; if their Stripe
  balance cannot cover it, the chargeback list shows `ownerOwes`, and it is
  taken from their next payout per the terms (counsel confirms the clause).
  Repeated losses on one owner or renter go to moderation.

## A buyer reported a problem (disputed booking)

A `disputed` booking has been paid (captured) but not paid out, and it will
not complete by itself. The two sides get 72 hours to settle it themselves
(S-21): either offers a refund amount, the other accepts, done. An offer
nobody answers in 72 hours sends the dispute to you (`escalatedAt` on it;
escalated disputes list first).

Work a case in the admin console: `GET /api/admin/bookings?status=disputed`
(or `?member=<id or email>`, `?booking=<id>`, `?claims=open`), then
`GET /api/admin/bookings/<id>/case`: the timeline, the whole conversation as
written, the hand-over photos, the payment, the dispute and what was decided.
Opening a case is logged.

Settle it with `POST /api/admin/bookings/<id>/resolve`:

| `outcome` | What happens |
|---|---|
| `pay_owner` | Completes it; payments transfers the owner's share |
| `refund_buyer` | Cancels it; payments refunds everything |
| `partial` + `refundAmount` | Completes it; payments refunds that part and pays the owner their share of the rest |

Give a `reasonCode` (damage, no_show, not_as_described, late_return,
cleanliness, safety, goodwill, other) and a `note`. A refund above your limit
(`refund_limit_support` / `refund_limit_lead` in `markets.json`, per market)
waits as `pending_approval` for someone else: `GET /api/admin/resolutions`,
then `POST /api/admin/resolutions/<id>/approve` (a lead, or anyone whose
limit covers it) or `/reject`. Leads are the Cognito group `admin-lead`, on
top of `admin`.

From inside the network (ECS Exec into any catalog task; booking accepts
catalog's internal token, not its own, P-10), the same rules with the support
limit:

```sh
curl -s -X POST http://booking:8000/internal/bookings/<id>/resolve \
  -H "X-Internal-Token: $INTERNAL_TOKEN" -H 'content-type: application/json' \
  -d '{"outcome":"pay_owner","reasonCode":"other","note":"...","by":"<your name>"}'
```

Everything is in the booking's audit trail as `support:<name>` and in the
staff audit log (`GET /api/admin/audit?target=<booking id>`).

### An owner says it came back late

The owner reports it within 24 hours of the end (`POST
/api/bookings/<id>/late-return`): a claim with the extra time after 30
minutes' grace at the listing's rate, plus a late fee of one hour's rate
capped per market (`late_fee_cap`). Confirm or reject it with `POST
/api/admin/claims/<id>/decide`. Nothing is charged: collecting needs a saved
card (S-9, waiting on the insurance decision G-B1); until then settle it
with the owner directly.

## Everyday operations

- **A shell in a running task**:
  `aws ecs execute-command --cluster cappy-<env> --task <id> --container <service> --interactive --command sh`.
- **Internal tokens** (P-10): each service has its own, `<service>:<random>`,
  in `cappy-<env>/internal-token/<service>`, and accepts only the callers in
  `local.internal_callers` (`infra/platform/data.tf`) by hash
  (`INTERNAL_CALLERS`). A call from a service not listed is a 403: add the
  edge there when one service starts calling another. **Rotate one**: `terraform taint
  'module.platform.random_password.internal_token["<service>"]'`, then deploy:
  the service and the hashes its callees hold change in the same rollout.
- **Rotate a service's database password**: taint
  `module.platform.random_password.db_service["<service>"]`, then deploy. The
  migrate task sets the new password before the services roll.
- **Stripe test mode locally**: set the test keys and `COMPOSE_PROFILES=stripe`,
  `PAYMENTS_PROVIDER=stripe` in `.env`; `make up` then gives every demo owner a
  verified test connected account (`python -m payments.cli demo-payouts`, test
  keys only). The webhook secret is `docker run --rm stripe/stripe-cli listen
  --api-key $STRIPE_SECRET_KEY --print-secret`.
- **Demo data**: staging only.
  `aws ecs run-task … --overrides '{"containerOverrides":[{"name":"catalog","command":["python","-m","catalog.cli","seed-demo"]}]}'`.
  The command refuses to run in prod.

## Moderation (DSA Art. 16/17)

Staff are members of the Cognito group `admin`:
`aws cognito-idp admin-add-user-to-group --user-pool-id … --username … --group-name admin`.
Wherever it is deployed a staff account also needs an authenticator app (TOTP
MFA) switched on, or every `/api/admin/…` call answers 403 `mfa_required`
(P-3): the new moderator signs in, sets up the authenticator from their
profile, and signs in again. Services check it with Cognito `AdminGetUser`,
cached five minutes, so turning MFA off takes up to five minutes to bite.
Locally `ADMIN_MFA_REQUIRED` is off (cognito-local has no MFA), so the demo
staff account works with its password alone; staging and prod refuse to
start with it off.
The console API is under `/api/admin/…`:

| Call | What it does |
|---|---|
| `GET /api/admin/reports?status=open` | The queue of notices, oldest first |
| `POST /api/admin/reports/{id}/decide` `{action: dismiss\|take_down\|suspend, statement, ground?: law\|terms, clause?, automated?}` | Decides. The person affected gets the structured statement of reasons (Art. 17(3)): the restriction, the facts (`statement`), the legal ground or terms clause, whether it was automated, and how to contest it. The reporter gets the outcome (Art. 16(5)) |
| `GET /api/admin/dsa-stats?month=YYYY-MM` | The numbers a transparency report needs (Art. 15/24); the exact active-recipient count is in `docs/analytics.md` |
| `POST /api/admin/listings/{id}/take-down` `{statement}` | Takes a listing down without a report |
| `POST /api/admin/owners/{id}/suspend` · `/reinstate` | Suspends: their listings come down, and they cannot list or book. To also stop sign-in: `aws cognito-idp admin-disable-user` |
| `GET /api/admin/bookings` `?status=&member=&booking=&claims=open` · `/{id}/case` | Finds and opens a case (H-9) |
| `POST /api/admin/bookings/{id}/resolve` `{outcome: pay_owner\|refund_buyer\|partial, refundAmount?, reasonCode, note}` | Settles a dispute; above your limit it waits for approval |
| `GET /api/admin/resolutions` · `POST /{id}/approve` · `/reject` | The second pair of eyes (H-6) |
| `POST /api/admin/claims/{id}/decide` `{decision: confirm\|reject, note}` | An owner's late-return claim |
| `GET /api/admin/audit` `?target=&actor=&cursor=` | Every staff action, in every service: who, what, when, why, request id (H-7) |

Aim to decide safety-related notices within 24 h.

The queue also holds notices nobody sent: `reason: reliability` (an owner cancelled or missed 3
accepted bookings in 30 days) and `reason: linked_to_suspended` (someone paid with a card a
suspended account used; could be a family card, could be ban evasion). Look at their bookings and
messages before acting; dismiss with a note if it is innocent.

## Kill switches

Each one pauses a single thing everywhere, without shipping code. The
environment's variables in GitHub are the one place they are set, so a deploy
never undoes them:

1. Settings → Environments → `prod` → variable `SWITCHES`, e.g.
   `{"bookings":false,"payouts":true,"listings":true}`.
2. Actions → deploy → Run workflow (`env: prod`). The same image is rolled
   out again with the new settings (about 10 minutes).

| Switch | Off means | When |
|---|---|---|
| `bookings` | New bookings get a 503 saying "paused". Booked ones carry on. | A card-testing wave, or a pricing bug |
| `payouts` | Payouts wait on their queue, retried with backoff. Nothing is lost. When the wait gets long they reach the DLQ; redrive it after switching back on. | Suspected fraud by owners, a Connect problem |
| `listings` | New listings get a 503. Existing ones stay bookable. | A spam wave |

Feature flags (`cappy_common/flags.py`) roll a change out to a share of people, the same way:
the `FEATURE_FLAGS` variable, e.g. `newcheckout:5`, then 25, 50, 100, each followed by a deploy run. `0` switches it off for everyone at once.
The apps read them from `/api/app-config` (cached up to 5 minutes).

## Restoring the database (rehearse this every quarter)

Two sources: Aurora's point-in-time restore (to any second in the last 14
days in prod), below; and AWS Backup's daily and monthly recovery points in
the vault `cappy-<cell>-<env>-vault` (R2-5), which no role in the account can
delete, for when the cluster itself is gone (Backup console → Protected
resources → Restore).

Aurora keeps continuous backups (14 days in prod), so any second in that
window can be restored.

1. Restore to a **new** cluster at the moment before the damage:
   `aws rds restore-db-cluster-to-point-in-time --source-db-cluster-identifier cappy-prod
   --db-cluster-identifier cappy-prod-restore --restore-to-time <UTC> --use-latest-restorable-time false`,
   then add an instance (`db.serverless`).
2. Compare what was lost and copy it back with SQL. Or, if the whole
   database is bad, point the services at the restored cluster: update the
   `database-url` secrets, then force a new deployment.
3. Write down how long each step took. Those numbers are the real RTO.

Last rehearsal: never. Do one before launch.

## A whole region goes down

The decision (T-26): run in **one region** (eu-central-1) across three
Availability Zones.
- An AZ loss is absorbed automatically: tasks in three AZs, an Aurora reader
  in another AZ, failover in about 30 s.
- A region loss means downtime until the region returns, with an RPO of
  minutes (continuous backups) and an RTO of hours.

When uptime commitments or revenue need more, the next step is Aurora
Global Database (RPO about 1 s, RTO minutes). That also needs a second copy
of the stack and a Cognito plan, because user pools are regional and are the
hard part.

## Game days (AWS Fault Injection Service)

Run one in staging before launch, then every quarter. For each, write down
whether the alarms fired and whether the runbook worked.

| Experiment | Expected |
|---|---|
| Fail over Aurora (`aws:rds:failover-db-cluster`) | About 30 s of errors on writes; retries succeed; no booking lost or doubled |
| Stop half of catalog's tasks (`aws:ecs:stop-task`) | Latency blips; ECS replaces them; no 5xx alarm |
| Block Stripe egress for 30 min | Bookings get 503; captures and payouts retry, then succeed after the block with nothing in the DLQ |
| Throttle SES | Emails delay; nothing is lost |
| Revoke the booking service's queue permissions | The queue-age alarm fires within 10 min |

## Known limits, and when to act

- Bookings, saved listings and reviews in the app show the newest 100. Add
  "load more" using the `nextCursor` the API already returns.
- Rate limiting is per IP, done by WAF. Add per-user limits (they need shared
  state such as Redis) when metrics show abuse from signed-in accounts.
- Every service can publish any event type to the one topic. A compromised
  service could forge events; per-publisher topics (and consumers checking
  which topic a message came from) close that when the threat model needs it.

## Local stack only: what behaves differently

- **Sign out everywhere cannot end other devices locally (GD-4).**
  cognito-local has no global sign-out, so a refresh token keeps minting new
  access tokens there. The services still refuse every access token issued
  before the sign-out (P-24), so the device that signed out, and any other
  whose token was issued earlier, get 401 at once; another device that
  refreshes afterwards carries on locally. With real Cognito,
  `AdminUserGlobalSignOut` revokes the refresh tokens too. Fronting
  cognito-local with a deny list was judged not worth it for a local-only gap.
- **A plain Sign out leaves the access token working locally (V7-28).** The
  app calls Cognito `RevokeToken` on the refresh token (`web/src/data/cognito.ts`).
  Real Cognito then also refuses the access tokens that refresh token issued,
  and access tokens last 15 minutes anyway (`identity.tf`). cognito-local
  ignores the revocation for access tokens and issues them for 24 hours, so
  locally the old token keeps working until it expires. Sign out everywhere
  does end it locally (P-24).
- **Staff MFA is off** (`ADMIN_MFA_REQUIRED`), see Moderation.
- **Short windows** (`MIN_LEAD_MINUTES=5`, `START_EARLY_MINUTES`,
  `SWEEP_SECONDS` in `compose.yaml`) so every flow can be walked in minutes;
  deployed settings refuse them.
