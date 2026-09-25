# Runbook

## First deploy of an environment

1. **Account bootstrap** (once per AWS account, by a person with admin rights):
   `cd infra/bootstrap && terraform init && terraform apply -var github_repo=<owner>/<repo>`.
   This creates the state bucket and the GitHub OIDC roles `deploy-staging` and
   `deploy-prod`, which only the deploy workflow running from `main`, inside
   that GitHub environment, can assume.
2. **GitHub**: create the environments `staging` and `prod`, and require a
   reviewer on `prod`. In each environment set these variables:
   - `AWS_DEPLOY_ROLE_ARN`, from the bootstrap output
   - `ZONE_ID`, the Route 53 hosted zone of the domain
   - `ALARM_EMAIL`

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
   `payment_intent.amount_capturable_updated`, `account.updated` and `charge.dispute.created`. Enable
   Connect with Express accounts.
5. **Push notifications** (once, when the store apps are ready): create two SNS
   platform applications, APNs with the Apple push key (`.p8`, key id, team id)
   and FCM with the Firebase service-account JSON (FCM HTTP v1). Pass their ARNs
   as `push_app_arns`. Without them pushes are only logged.
6. **SES**: request production access for the region, so mail reaches
   addresses that aren't verified. DKIM, SPF and DMARC records are created by
   Terraform.
7. Run the `deploy` workflow.

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
| `<service>-dead-letters` | An event failed 5 times. Read it: `aws sqs receive-message --queue-url <dlq>`. Fix the cause, then redrive with `aws sqs start-message-move-task --source-arn <dlq-arn>`. Handlers are idempotent, so redriving is safe. |
| `<service>-queue-age` | The consumer is down or too slow. Check the service is running and its logs. |
| `db-cpu`, `db-at-max-capacity` | Raise `db_max_acu`; find the slow queries in Performance Insights. |

## A buyer reported a problem (disputed booking)

A `disputed` booking has been paid (captured) but not paid out, and it will
not complete by itself. Read the buyer's reason (`declineReason`) and hear
both sides. Then settle it from inside the network (for example with ECS Exec
into any booking task):

```sh
curl -s -X POST http://localhost:8000/internal/bookings/<id>/resolve \
  -H "X-Internal-Token: $INTERNAL_TOKEN" -H 'content-type: application/json' \
  -d '{"outcome":"pay_owner","by":"<your name>"}'     # or "refund_buyer"
```

- `pay_owner` completes the booking, and payments transfers the owner's share.
- `refund_buyer` cancels it, and payments refunds the buyer in full.

Both are recorded in the booking's audit trail as `support:<name>`.

## Everyday operations

- **A shell in a running task**:
  `aws ecs execute-command --cluster cappy-<env> --task <id> --container <service> --interactive --command sh`.
- **Rotate the internal token**: `terraform taint 'module.platform.random_password.internal_token'`,
  then deploy. All services pick up the new value together.
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

## Kill switches

Each one pauses a single thing everywhere, without shipping code:

```sh
cd infra/envs/prod
terraform apply -var image_tag=<the running tag> -var zone_id=… -var alarm_email=… \
  -var 'switches={bookings=false,payouts=true,listings=true}'
```

| Switch | Off means | When |
|---|---|---|
| `bookings` | New bookings get a 503 saying "paused". Booked ones carry on. | A card-testing wave, or a pricing bug |
| `payouts` | Payouts wait on their queue, retried with backoff. Nothing is lost. When the wait gets long they reach the DLQ; redrive it after switching back on. | Suspected fraud by owners, a Connect problem |
| `listings` | New listings get a 503. Existing ones stay bookable. | A spam wave |

## Restoring the database (rehearse this every quarter)

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
- Cancelling an accepted booking before its time starts refunds in full; after
  that the buyer can only dispute. Put a partial-refund policy in
  `payments/handlers.py` if late cancellations should cost something.
- Every service can publish any event type to the one topic. A compromised
  service could forge events; per-publisher topics (and consumers checking
  which topic a message came from) close that when the threat model needs it.
