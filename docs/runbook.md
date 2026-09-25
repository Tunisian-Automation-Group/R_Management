# Runbook

## First deploy of an environment

1. **Account bootstrap** (once per AWS account, by a person with admin rights):
   `cd infra/bootstrap && terraform init && terraform apply -var github_repo=<owner>/<repo>`.
   This creates the state bucket and the GitHub OIDC roles `plan`, `deploy-staging`
   and `deploy-prod`.
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
   `payment_intent.amount_capturable_updated` and `account.updated`. Enable
   Connect with Express accounts.
5. **SES**: request production access for the region, so mail reaches
   addresses that aren't verified. DKIM, SPF and DMARC records are created by
   Terraform.
6. Run the `deploy` workflow.

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

## Everyday operations

- **A shell in a running task**:
  `aws ecs execute-command --cluster cappy-<env> --task <id> --container <service> --interactive --command sh`.
- **Rotate the internal token**: `terraform taint 'module.platform.random_password.internal_token'`,
  then deploy. All services pick up the new value together.
- **Rotate a service's database password**: taint
  `module.platform.random_password.db_service["<service>"]`, then deploy. The
  migrate task sets the new password before the services roll.
- **Demo data**: staging only.
  `aws ecs run-task … --overrides '{"containerOverrides":[{"name":"catalog","command":["python","-m","catalog.cli","seed-demo"]}]}'`.
  The command refuses to run in prod.

## Known limits, and when to act

- Bookings, saved listings and reviews in the app show the newest 100. Add
  "load more" using the `nextCursor` the API already returns.
- Rate limiting is per IP, done by WAF. Add per-user limits (they need shared
  state such as Redis) when metrics show abuse from signed-in accounts.
- A buyer who cancels an accepted booking is refunded in full. Put a
  cancellation policy in `payments/handlers.py` before it is needed.
