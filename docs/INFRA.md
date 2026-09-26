# Infrastructure

What Cappy runs on, per environment and cell, and why. This is a living doc
(see `CLAUDE.md`): it describes the Terraform, compose file and workflows as
committed. The reasons behind them are in the ADRs, mainly
[0008](adr/0008-aws-runtime.md) (AWS runtime),
[0009](adr/0009-local-parity.md) (local parity) and
[0013](adr/0013-markets.md) (markets and cells). How to operate it is in
[`runbook.md`](runbook.md).

> **Nothing here has ever been applied to a real AWS account, and nothing
> will be (GOAL 12).** The Terraform is checked with `terraform fmt` and
> `terraform validate` only. The event fabric (`infra/modules/messaging`) is
> the one part that is applied, to LocalStack. Everything else runs locally
> under `compose.yaml`. Where this file says "creates", read "would create
> when applied".

References are `path:line` in the committed tree. Last synced with the code
as of `2257182` (`42c777c` and `2257182`: `make bench`, `make up` listing
every demo account, the runbook's "Local stack only" section, the second demo
host's comment, `VITE_CAPPY_USER` gone from `web/.env.example`). Neither
commit adds an AWS resource or a cost. The sync before covered `747ed6b` and
`61b15b8`.

Contents: [1 Overview](#1-overview) · [2 Terraform, file by file](#2-terraform-file-by-file) ·
[3 Environments and cells](#3-environments-and-cells) · [4 Security](#4-security) ·
[5 Operations](#5-operations) · [6 Capacity and cost](#6-capacity-and-cost) ·
[7 Local development](#7-local-development) · [8 How to keep this file true](#8-how-to-keep-this-file-true)

---

## 1. Overview

One cell (today: EU, eu-central-1) is one copy of `infra/platform`:

```
                    Browser / PWA / store apps (Capacitor shells)
                         |                                  |
            HTTPS (one origin: app, /api/*, /media/*)       |  sign-in, sign-up, refresh
                         v                                  v
   +------------------ us-east-1 ------------------+   +-------------------------------+
   | CloudFront  (PriceClass_100, HTTP/2+3, IPv6)  |   | Cognito user pool             |
   |   + WAF web ACL "edge" (per-IP rate, writes,  |   |   + regional WAF "cognito"    |
   |     IP reputation, common, bad inputs,        |   |     (100 req/5 min per IP,    |
   |     Bot Control in prod)                      |   |      IP reputation)           |
   |   + security headers (CSP, HSTS, ...)         |   |   Plus tier + threat          |
   +---+-----------------+-----------------+-------+   |   protection in prod          |
       | default         | /media/*        | /api/*  +-------------+-----------------+
       v                 v                 | (X-Origin-Secret)     | email codes via SES
   S3 web bucket    S3 media bucket        v                       |
   (OAC, private)   (OAC, versioned)   ALB origin.<domain> :443    |
                         ^             (only CloudFront prefix     |
                         | put/delete   list; 403 without secret)  |
                         |                 |                       |
   +------------- VPC 10.40.0.0/16, 3 AZs, private subnets --------+-------------+
   |                     |                 v                       |             |
   |                     |          gateway (ECS Fargate)          |             |
   |                     |                 | Service Connect http://<svc>:8000   |
   |                     |   +-------------+------+----------+--------------+    |
   |                     +-- catalog   matching   booking   payments   notifications
   |                          |   \               |   \       |    \          |   \
   |                          |    reader         |  reader   |   Stripe API   |  SES (mail)
   |                          v                   v           v   (via NAT)    |  SNS push
   |              Aurora PostgreSQL 16 Serverless v2: writer + reader(s),      |  (APNs/FCM)
   |              one database and one role per service                       |
   |                                                                          |
   |  Each task: service container + ADOT collector sidecar --> AWS X-Ray     |
   |  Logs: awslogs --> CloudWatch /cappy/<env>/<service>                     |
   +--------------------------------------------------------------------------+

   Events (transactional outbox, ADR 0003):
     catalog / booking / payments --publish--> SNS topic cappy-<env>-events (KMS)
        |-- filter per consumer --> SQS cappy-<env>-<svc>  --12 receives--> SQS <svc>-dlq
        |      (catalog, booking, payments, notifications)
        '-- all events ----------> Kinesis Firehose --(Lambda scrub: allowlisted fields only)
                                        --> S3 analytics (dt= partitions) --> Glue table --> Athena

   Outside-in: CloudWatch Synthetics canary (every 5 min) --> the public URL
   Alarms: CloudWatch --> SNS cappy-<env>-alarms --> email
```

Where each box is defined: CloudFront, WAF, ALB `infra/platform/edge.tf`;
Cognito and its WAF `infra/platform/identity.tf`; VPC `infra/platform/network.tf`;
ECS `infra/platform/ecs.tf`; Aurora and secrets `infra/platform/data.tf`;
SNS/SQS `infra/modules/messaging/main.tf`; SES `infra/platform/email.tf`;
buckets `infra/platform/storage.tf`; analytics `infra/platform/analytics.tf`;
alarms `infra/platform/observability.tf`; canary `infra/platform/synthetics.tf`.

---

## 2. Terraform, file by file

### Layout

| Root / module | What it is | State |
|---|---|---|
| `infra/bootstrap/` | Once per AWS account, by a person: the state bucket and the GitHub OIDC roles | local |
| `infra/platform/` | The whole cell, as a module (no backend) | via the env roots |
| `infra/modules/messaging/` | SNS topic, per-consumer SQS queue and DLQ | via its callers |
| `infra/envs/staging/` | `platform` with staging sizes | S3 `cappy-terraform-state`, key `staging/terraform.tfstate` (`infra/envs/staging/main.tf:3-10`) |
| `infra/envs/prod/` | `platform` with prod sizes | S3, key `prod/terraform.tfstate` (`infra/envs/prod/main.tf:3-10`) |
| `infra/localstack/` | Only the messaging module, pointed at LocalStack | local |

Versions: Terraform `>= 1.10`, AWS provider `~> 6.0`, random `~> 3.6`, http
`~> 3.4`, archive `~> 2.4` (`infra/platform/versions.tf:1-9`). The platform
takes a second AWS provider, `aws.us_east_1`, for CloudFront's certificate and
WAF (`infra/platform/versions.tf:4`; wired in `infra/envs/staging/main.tf:27-33`).
CI pins Terraform 1.12.2 (`.github/workflows/ci.yml:84`). State locking is
S3-native (`use_lockfile = true`, `infra/envs/prod/main.tf:9`).

All names start with `local.name = "cappy-${var.env}"` (`infra/platform/network.tf:6`).
Default tags `app`, `env`, `managed_by` come from the env roots' providers
(`infra/envs/prod/main.tf:19-24`).

### `infra/platform/variables.tf`: the inputs

| Variable | Default | Staging | Prod | Line |
|---|---|---|---|---|
| `env` | (required; `staging` or `prod` only) | `staging` | `prod` | 1 |
| `region` | `eu-central-1` | default | default | 10 |
| `domain` | (required) | `staging.cappy.app` | `cappy.app` | 15 |
| `zone_id` | (required) | `-var zone_id` from GitHub `vars.ZONE_ID` | same | 20 |
| `image_tag` | (required) | commit sha from CD | same | 25 |
| `az_count` | `3` | default | default | 30 |
| `nat_gateways` | `1` | `1` | `3` | 35 |
| `db_min_acu` | `0.5` | `0.5` | `1` | 41 |
| `db_max_acu` | `16` | `4` | `64` | 46 |
| `db_instances` | `2` (writer + reader) | `1` | `2` | 51 |
| `scale` | see below | smaller map | default | 57-73 |
| `alarm_email` | (required) | `vars.ALARM_EMAIL` | same | 75 |
| `waf_rate_limit` | `2000` per 5 min per IP | default | default | 80 |
| `switches` | all `true` | GitHub environment variable `SWITCHES` (JSON; all on when unset), as `TF_VAR_switches` | same | 86 |
| `legal` | (required: company, address, VAT ID, tax number) | GitHub environment variable `LEGAL` (JSON), as `TF_VAR_legal` | same | 96 |
| `feature_flags` | `""` | GitHub environment variable `FEATURE_FLAGS`, as `TF_VAR_feature_flags` | same | 101 |
| `bot_control` | `false` | default | `true` | 107 |
| `cognito_threat_protection` | `false` | default | `true` | 113 |
| `push_app_arns` | `{ ios = "", android = "" }` | default | default (set once the store apps exist) | 119 |

Env overrides: `infra/envs/staging/main.tf:65-90`, `infra/envs/prod/main.tf:65-86`.

`scale` (cpu units / MiB / min tasks / max tasks):

| Service | Default = prod (`variables.tf:65-72`) | Staging (`envs/staging/main.tf:82-89`) |
|---|---|---|
| gateway | 512 / 1024 / 2 / 20 | 256 / 512 / 1 / 4 |
| catalog | 512 / 1024 / 2 / 20 | 256 / 512 / 1 / 4 |
| matching | 1024 / 2048 / 2 / 30 | 512 / 1024 / 1 / 4 |
| booking | 512 / 1024 / 2 / 20 | 256 / 512 / 1 / 4 |
| payments | 256 / 512 / 2 / 10 | 256 / 512 / 1 / 2 |
| notifications | 256 / 512 / 1 / 4 | 256 / 512 / 1 / 2 |

The keys of `scale` are the list of services (`infra/platform/ecs.tf:9`):
adding a service starts there.

### `infra/platform/network.tf`: the VPC

- VPC `10.40.0.0/16` with DNS (`:10-15`).
- `az_count` public subnets (`/22` each, `:17-24`, no public IPs on launch)
  for the ALB and NAT gateways, and `az_count` private subnets (`/20` each,
  `:27-33`) for the tasks and the database.
- Internet gateway (`:35`); `nat_gateways` NAT gateways with Elastic IPs
  (`:39-48`). Each private route table uses NAT `index % nat_gateways`
  (`:64-71`): staging shares one, prod has one per AZ, so an AZ loss does not
  cut egress.
- An S3 gateway endpoint on the private route tables (`:80-85`): media and
  image layers skip the NAT. There are no interface endpoints: ECR API,
  Secrets Manager, CloudWatch Logs, SNS, SQS, Cognito, SES and Stripe traffic
  goes out through the NAT.

### `infra/platform/data.tf`: Aurora, secrets, the event fabric

- **Consumers** (`:6-11`): which event types each service's queue receives.
  Passed to `module "messaging"` (`:14-18`). The same map is copied into
  `infra/localstack/main.tf:27-32`, `infra/localstack/check.py:13-42` and
  `local/bootstrap.py:30-59`. Since `235eeaa` a test keeps them in step
  (`backend/libs/cappy_common/tests/test_subscriptions.py`, D-13): the four
  copies must be equal, and each service must handle every type it receives
  (sign-out and deletion are handled by every runtime) and receive every type
  it handles. `person.signed_out` goes to booking, payments and
  notifications; `payment.identity_verified` goes to booking and, since
  `235eeaa`, catalog (the profile's `verified`); `listing.idle` (catalog's
  "no free time next week", since `61b15b8`) goes to notifications.
- **Database services** (`:5`): catalog, booking, payments, notifications.
  Matching and the gateway have no database.
- DB subnet group on the private subnets (`:20-23`); security group allowing
  5432 only from the tasks' security group (`:25-36`).
- Parameter group `aurora-postgresql16` with `rds.force_ssl = 1` and
  `log_min_duration_statement = 500` ms (`:43-54`).
- **Cluster** `cappy-<env>` (`:56-80`): Aurora PostgreSQL 16.6, Serverless v2
  (`db_min_acu`..`db_max_acu`), storage encrypted, backups 14 days in prod and
  3 in staging, window 02:00-03:00 UTC, deletion protection and a final
  snapshot in prod only, Postgres logs exported to CloudWatch.
- **Instances** (`:82-93`): `db_instances` × `db.serverless`, all promotion
  tier 1 so readers scale with the writer and a failover lands on a warm one;
  Performance Insights on.
- **Secrets** (Secrets Manager):
  - `cappy-<env>/<svc>/database-url` per database service, writer endpoint,
    `ssl=require` (`:102-111`); the per-service password is
    `random_password.db_service` (`:95-99`).
  - `cappy-<env>/<svc>/database-read-url` for catalog and booking, the reader
    endpoint (`:115-127`).
  - `cappy-<env>/database-admin-url`, seen only by the migrate task (`:129-136`).
  - `cappy-<env>/internal-token/<svc>`, one per service except the gateway,
    holding `<svc>:<48 random characters>` for its own `/internal/*` calls
    (`:150-165`, P-10). Who may call whom is `local.internal_callers`
    (`:140-147`): catalog ← matching, booking; matching ← booking; booking ←
    matching, catalog; payments ← booking, catalog; notifications ← catalog.
    A callee gets only the sha256 of each caller's token (`INTERNAL_CALLERS`,
    `ecs.tf:71-74`), never the token.
  - `cappy-<env>/stripe`, an empty secret; its value is put in by hand
    (`:169-171`, runbook "First deploy" step 4).
- **Connection budget check** (`:173-191`), see [§6](#6-capacity-and-cost).
- **Replica lag alarm**: `AuroraReplicaLag` above 1 s for 5 minutes (`:193-206`).

### `infra/platform/identity.tf`: Cognito (ADR 0002)

- **User pool** `cappy-<env>` (`:4-69`): email is the username and is
  auto-verified; deletion protection in prod; MFA optional (TOTP), which the
  services require of staff accounts when deployed (`ADMIN_MFA_REQUIRED`,
  P-3); tier
  `PLUS` with `advanced_security_mode = ENFORCED` when
  `cognito_threat_protection` is on (prod), otherwise `ESSENTIALS` (`:10-17`).
  Password policy: 12 characters, no composition rules (NIST 800-63B,
  `:26-33`). An email change only applies once verified (`:36-38`). Recovery
  by verified email. Mail is sent through SES from `no-reply@<domain>`
  (`:47-51`); codes, not links (`:53-57`).
- **App client** `web` (`:71-98`): no secret (a browser cannot keep one), SRP,
  password and refresh flows, reads `email`, `email_verified`, `locale`,
  writes only `email` and `locale`, user-existence errors hidden, token
  revocation on. Access and ID tokens **15 minutes** (`:90-91`, P-24), refresh
  30 days.
- **Issuer** `https://cognito-idp.<region>.amazonaws.com/<pool>` (`:100-102`).
- **JWKS at deploy** (`:107-112`): a `data "http"` fetch of the pool's keys,
  passed to every task as `AUTH_JWKS_FALLBACK` so a task that starts while
  Cognito is unreachable still verifies tokens (resilience F5). This is also
  why a `terraform plan` needs network access to Cognito.
- **Group** `admin` for staff (`:116-120`); membership is granted by hand.
- **Cognito WAF** (`:124-180`), see [§4](#waf).

### `infra/platform/ecs.tf`: compute

- **Cluster** `cappy-<env>` with Container Insights `enhanced` and a Service
  Connect namespace (`:91-104`).
- **ECR** `cappy/<service>` per service: immutable tags, scan on push,
  force-delete outside prod (`:106-114`); keep the last 50 images (`:116-127`).
- **Log groups** `/cappy/<env>/<service>` and `/cappy/<env>/migrate`,
  90 days in prod, 14 in staging (`:129-133`).
- **Environment** (`:13-76`): common to all (`APP_ENV`, JSON logs, region,
  `EVENT_BUS_URL=sns://<topic>`, the auth issuer, client id and JWKS fallback,
  `USER_POOL_ID`, OTEL to `localhost:4318`, the Service Connect URLs and
  `FEATURE_FLAGS`, so the flag the app shows and the one a service enforces
  are the same: `:13-32`), per service (`:33-65`: gateway CORS for the
  Capacitor shells and `TRUSTED_PROXY_HOPS=2` (CloudFront, then the ALB);
  catalog `MEDIA_BUCKET`, `REQUIRE_PAYABLE_OWNERS`, `ACCEPTING_LISTINGS`,
  `CDN_DISTRIBUTION_ID`; booking `ACCEPTING_BOOKINGS`; payments
  `PAYMENTS_PROVIDER=stripe`, `PAYOUTS_ON`, the `legal` identity;
  notifications `MAILER=ses`, `MAIL_FROM`, the push app ARNs),
  `EVENT_QUEUE_URL` for consumers (`:70`), and `INTERNAL_CALLERS` (the hashes
  of the callers' tokens) for every service but the gateway (`:71-74`).
  Settings added in `235eeaa` that Terraform does not set, so their defaults
  hold when deployed: payments' `IDENTITY_PROVIDER` (empty follows
  `PAYMENTS_PROVIDER`, so Stripe Identity; `fake` is refused deployed) and
  `INVOICE_RETENTION_YEARS` (10), and every service's `STAFF_CLAIM` /
  `STAFF_VALUE` (`cognito:groups` / `admin`).
- **Secrets** injected by ECS (`:77-88`): `INTERNAL_TOKEN`, each service its
  own (all but the gateway), `DATABASE_URL`, `DATABASE_READ_URL`, and the
  three Stripe keys for payments (JSON keys of the one secret).
- **Task definitions** (`:264-324`): Fargate, x86_64, the size from `scale`,
  read-only root filesystem with a writable `/tmp` volume (uploads over 1 MB
  spool there), port 8000, container health check on `/healthz`, 30 s stop
  timeout. A second, non-essential container runs the ADOT collector
  `aws-otel-collector:v0.43.3` (`:306-323`), which forwards traces to X-Ray.
- **Services** (`:326-383`): `desired_count = min`, private subnets, the tasks
  security group, ECS Exec on. Rolling deploys at 100 % minimum / 200 %
  maximum, the deployment circuit breaker with rollback (`:341-346`), and
  **alarm-based rollback** on `api-5xx-rate` and the fast burn alarm
  (`:350-354`). Service Connect: every service is a client; catalog,
  matching, booking, payments and notifications are also servers at
  `http://<name>:8000` (`:11`, `:356-368`). Only the gateway is registered
  with the ALB target group (`:370-377`). Autoscaling owns `desired_count`
  after the first apply (`:379-382`).
- **Autoscaling** (`:385-449`): each service between `min` and `max`;
  target tracking on CPU 60 % (scale out 30 s, in 120 s); consumers also on
  their queue's visible messages, target 100 (`:413-434`); the gateway also
  on ALB requests per target, target 500 (`:436-449`).
- **Migrate task definitions** (`:453-480`): one per database service,
  256 CPU / 512 MiB, the service's own image running
  `python -m cappy_common.migrations <svc>` with `DATABASE_URL` and
  `ADMIN_DATABASE_URL`.
- IAM roles, security groups: see [§4](#4-security).

### `infra/platform/edge.tf`: CloudFront, WAF, ALB (ADR 0008)

- **Certificates** (`:16-55`): ACM in us-east-1 for `<domain>` (CloudFront)
  and in the cell region for `origin.<domain>` (ALB), DNS-validated in the
  hosted zone.
- **ALB** `cappy-<env>` (`:84-92`) in the public subnets; drops invalid
  header fields; deletion protection in prod; 30 s idle timeout. Its security
  group admits 443 only from the CloudFront origin-facing managed prefix list
  and sends only to the tasks on 8000 (`:59-82`).
- **Target group** for the gateway, IP targets, health check `/readyz`
  every 10 s, 20 s deregistration delay (`:94-108`).
- **Listener** 443 with `ELBSecurityPolicy-TLS13-1-2-2021-06`; the default
  action is a fixed 403 (`:110-124`). Only requests carrying the
  `X-Origin-Secret` header (a 40-character random value, `:9-12`) are
  forwarded (`:126-139`). DNS `origin.<domain>` aliases the ALB (`:141-150`).
- **WAF web ACL `edge`** (CLOUDFRONT scope, us-east-1, `:156-337`), see [§4](#waf).
- **CloudFront** (`:442-569`): HTTP/2 and 3, IPv6, `PriceClass_100`
  (North America and Europe edges), alias `<domain>`, TLS `TLSv1.2_2021`,
  the WAF attached. Origins: the web bucket and media bucket through origin
  access control (`:341-346`), and the ALB at `origin.<domain>` over HTTPS
  with the secret header (`:463-477`). Behaviours:

  | Path | Origin | Caching |
  |---|---|---|
  | default | web bucket | `Managed-CachingOptimized`; a CloudFront Function rewrites extension-less paths to `/index.html` (`:349-360`); security headers attached |
  | `/api/app-config`, `/api/categories`, `/api/groups`, `/api/ranking` (since `61b15b8`, `:527-535`: the ranker's published weights), `/api/review-tags` | ALB | `api_public` policy (`:365-383`): keyed on the query string only, no headers or cookies, TTL as the origin says (max 1 h) |
  | `/api/*` | ALB | `Managed-CachingDisabled`, all viewer headers except Host forwarded |
  | `/media/*` | media bucket | `Managed-CachingOptimized` |

- **DNS**: `A` and `AAAA` aliases for `<domain>` (`:571-581`).

### `infra/platform/storage.tf`: buckets (ADR 0007)

- `cappy-<env>-web-<account>` (the built app) and
  `cappy-<env>-media-<account>` (listing photos under `media/`, hand-over
  evidence under `private/`) (`:6-12`); public access blocked and ACLs
  disabled on both (`:14-29`).
- Media is versioned; old versions expire after 30 days and unfinished
  multipart uploads after a day (`:31-51`).
- Bucket policies let only this CloudFront distribution read (`:53-68`), and
  on the media bucket only `media/*` (`:62-64`): evidence under `private/` is
  never reachable through the CDN, only through booking's signed links (P-27).
  Only catalog writes media ([§4](#iam-per-service)).
- `data "aws_caller_identity" "me"` lives here (`:4`) and is used across the module.

### `infra/platform/email.tf`: SES (ADR 0006)

- SES v2 domain identity for `<domain>` with Easy DKIM, three CNAMEs
  (`:5-16`); MAIL FROM `mail.<domain>` with MX and SPF (`:18-37`); DMARC
  `p=quarantine` (`:39-45`).
- Account-level suppression of bounces and complaints (`:50-52`).
- Alarms: bounce rate above 2 % and complaint rate above 0.05 % over an hour
  (`:54-80`), well before SES reviews an account at 5 % / 0.1 %.
- SES production access is a manual request (runbook step 6).

### `infra/modules/messaging/main.tf`: SNS and SQS (ADR 0003)

- One topic `<name>-events`, encrypted with `alias/aws/sns` (`:24-27`).
- Per consumer: a DLQ `<name>-<svc>-dlq` keeping messages 14 days
  (`:29-34`), and a queue `<name>-<svc>` with visibility 120 s (above the
  slowest handler), 20 s long polling, SQS-managed encryption, and a redrive
  to the DLQ after **12** receives (`:36-47`).
- Queue policies accept `sqs:SendMessage` only from this topic (`:49-62`).
- Subscriptions with raw delivery and a filter policy on the `type`
  attribute (`:64-71`).
- Outputs: `topic_arn`, `queue_urls`, `queue_arns`, `queue_names`, `dlq_names`
  (`:73-91`).

### `infra/platform/analytics.tf`: product analytics

- Bucket `cappy-<env>-analytics-<account>`, private; Glacier Instant
  Retrieval after 90 days, deleted after two years (`:6-35`).
- Firehose `cappy-<env>-events` to S3 under `events/dt=YYYY-MM-DD/`, GZIP,
  buffered 5 minutes or 64 MB (`:61-85`); errors under `errors/`.
- **Scrub** (P-6): the Firehose runs every record through the Lambda
  `cappy-<env>-analytics-scrub` (`:74-84`), Python 3.12, 256 MB, 60 s
  (`:106-115`), zipped from `infra/platform/analytics/scrub.py` by
  `data "archive_file"` (`:87-91`, into `infra/platform/.build/`). It keeps
  the envelope and an allowlist of scalar fields, rewrites a `by` of
  `support:<who>` to `staff` (since `747ed6b`), and drops anything it cannot
  parse ([`DATA.md`](DATA.md) §3.1). Its role has only
  `AWSLambdaBasicExecutionRole` (`:93-104`).
- SNS subscribes the Firehose to **every** event, raw delivery (`:133-139`),
  through a role that can only put records (`:117-131`).
- Glue database and table `cappy_events` with date partition projection, so
  Athena needs no crawler (`:142-189`). Queries: [`analytics.md`](analytics.md).

### `infra/platform/observability.tf`: alarms

See [§5 Alarms](#alarms). One SNS topic `cappy-<env>-alarms` with an email
subscription to `alarm_email` (`:4-12`).

### `infra/platform/synthetics.tf` and `canary/`

A CloudWatch Synthetics canary `cappy-<env>-journeys` (the name is cut to 21
characters, `:48`), runtime `syn-nodejs-puppeteer-9.1`, every 5 minutes, 60 s
timeout (`:47-64`), with artifacts in a bucket that expires them after 14 days
(`:9-24`). The script is `infra/platform/canary/nodejs/node_modules/journeys.js`
(zipped by `data "archive_file"`, `:3-7`). See [§5 Canary](#the-canary).

### `infra/platform/outputs.tf`

`url`, `cluster`, `services`, `service_task_definitions` (the deploy checks
each service runs these), `migrate_task_definitions`, `private_subnets`,
`task_security_group`, `ecr`, `web_bucket`, `cloudfront_id`, and `web_config`
(`VITE_COGNITO_REGION`, `VITE_COGNITO_CLIENT_ID`; public values)
(`:1-48`). The env roots expose them all as `output "platform"`.

### `infra/envs/staging/main.tf` and `infra/envs/prod/main.tf`

Each sets the backend, the two providers (cell region and us-east-1), takes
`image_tag`, `zone_id`, `alarm_email`, `switches`, `legal`, `feature_flags`
as variables, and calls `../../platform` with the sizes in the tables above.
Prod additionally turns on `cognito_threat_protection` and `bot_control`
(`infra/envs/prod/main.tf:69`, `:85`). CD sets `legal`, `switches` and
`feature_flags` from the GitHub environment's variables `LEGAL`, `SWITCHES`
and `FEATURE_FLAGS` (`TF_VAR_*`, `.github/workflows/deploy.yml:71-74`), and
since `44a5520` the env roots' comments say so, with an example of each value
(`infra/envs/prod/main.tf:47-48`, `:54-55`, `:60-61`). A local apply passes the
same values with `-var` or a tfvars file.

### `infra/bootstrap/main.tf`

Run by hand once per account (`:1-4`), local state:

- State bucket `cappy-terraform-state`, `prevent_destroy`, versioned,
  SSE-KMS, public access blocked (`:22-51`).
- GitHub OIDC provider (`:53-56`).
- Four roles `cappy-github-<key>` (`:66-112`), see [§4](#github-oidc-roles).

### `infra/localstack/main.tf` and `check.py`

The messaging module with `name = "cappy-tf"`, the provider pointed at
`http://localhost:4566` with test credentials (`:11-33`). `check.py` holds
the expected map (`:13-42`), publishes one event of every type any queue
subscribes to plus `nobody.listens`, which must reach no queue (`:43-47`), and
asserts each queue received exactly the types its filter asks for
(`:48-56`). Since `235eeaa` the expected map is derived, not listed twice, and
it includes `payment.failed` for booking, which it had been missing. Run by
`make infra-local`.

---

## 3. Environments and cells

| | Local (compose) | LocalStack Terraform | Staging | Prod, EU cell | Prod, North America cell |
|---|---|---|---|---|---|
| Status | runs | applied (messaging only) | validated only | validated only | **planned** (ADR 0013, M-21) |
| Where | a laptop / CI runner | LocalStack on :4566 | eu-central-1 | eu-central-1 | ca-central-1 |
| Defined in | `compose.yaml`, `local/` | `infra/localstack/` | `infra/envs/staging/` | `infra/envs/prod/` | would be `infra/envs/prod-na/` |
| Domain | `localhost:8000` | n/a | `staging.cappy.app` | `cappy.app` | per ADR 0013: `<cell>.api.<domain>` |
| Demo data | yes (`make seed-demo`) | no | allowed (ADR 0010) | refused | refused |

**What "validated" means.** `make infra-validate` and the CI `infra` job run
`terraform fmt -check -recursive` and, in `bootstrap`, `envs/staging`,
`envs/prod` and `localstack`, `terraform init -backend=false` then
`terraform validate` (`Makefile:56-57`, `.github/workflows/ci.yml:79-90`).
That checks syntax, types and references. It does not evaluate `check`
blocks, data sources or provider-side rules, which only a plan against an
account would (and a plan against real AWS is out of scope, GOAL 12).
The deploy workflow (`.github/workflows/deploy.yml`) is written and
reviewed but has never run against an account.

### Local (compose)

`make up` builds the six service images and starts
(`compose.yaml`, ADR 0009):

| Container | Stands in for | Port on the host | Line |
|---|---|---|---|
| `postgres` (postgres:16-alpine) | Aurora; one database per service via `local/postgres-init.sql` | `127.0.0.1:5433` | 38-48 |
| `localstack` (localstack-pro, `SERVICES: s3,sns,sqs,ses`) | S3, SNS, SQS, SES v1 | `127.0.0.1:4566` | 50-56 |
| `cognito` (jagregory/cognito-local) | the Cognito user pool | `127.0.0.1:9229` | 58-64 |
| `bootstrap` (one-shot) | Terraform: creates topic, queues, DLQs, bucket, sender, pool, client, `admin` group, demo users | none | 66-72 |
| `catalog`, `matching`, `booking`, `payments`, `notifications` | ECS services | none (network only) | 74-123 |
| `gateway` | CloudFront + ALB + gateway | `127.0.0.1:8000` | 139-149 |
| `stripe` (stripe-cli, profile `stripe`) | Stripe calling the public webhook URL | none | 127-137 |

- `local/bootstrap.py` creates the resources idempotently with the names
  Terraform uses (`cappy-events`, `cappy-<svc>`, `cappy-<svc>-dlq`,
  `cappy-media`), and writes `.local/local.env` for the services and
  `.local/web.env` for the Vite dev server (`local/bootstrap.py:197-225`).
  Only `make up` copies `.local/web.env` to `web/.env.development.local`
  (`Makefile:12`). After bootstrap runs any other way (a plain `docker
  compose up`), copy it by hand and restart `npm run dev`; it matters when the
  pool was made afresh (a wiped `cognito` volume), because the pool and client
  ids in it change. On
  a stack made earlier it also updates each subscription's filter policy, so a
  newly consumed event type reaches its queue (`:104-121`).
- `local/run.sh` loads that env, picks the service's queue URL, runs its
  migrations, then starts uvicorn (`local/run.sh:1-15`).
- Local differences, all deliberate: `APP_ENV=local`, one fixed non-secret
  internal token shared by all services (no `INTERNAL_CALLERS`), LocalStack
  test credentials (`compose.yaml:23-35`); no staff MFA;
  `MIN_LEAD_MINUTES=5` on matching (since `61b15b8`, `compose.yaml:92`) so a
  booking can start 5 minutes out and testers can walk no-shows, disputes
  and reviews in minutes; `SWEEP_SECONDS=5` and `START_EARLY_MINUTES=100000`
  on booking so the e2e can walk a booking to payout in a minute
  (`compose.yaml:101-104`); `PAYMENTS_PROVIDER=fake` unless Stripe test keys
  are set (`:114`). Deployed, the services refuse to start with
  `MIN_LEAD_MINUTES` under 60, `START_EARLY_MINUTES` above 60 or
  `AUTO_COMPLETE_AFTER_HOURS` under 24 (`unsafe_reasons` in
  `matching/settings.py` and `booking/settings.py`, since `61b15b8`), so the
  shortcuts cannot reach staging or prod.
- **Stripe CLI profile.** With `COMPOSE_PROFILES=stripe`,
  `PAYMENTS_PROVIDER=stripe` and test keys in `.env`, the `stripe` container
  listens for the five webhook events the prod endpoint subscribes to and
  forwards them to `http://gateway:8000/api/payments/webhooks/stripe`
  (`compose.yaml:127-137`); `make seed-demo` then gives every demo owner a
  verified test connected account (`Makefile:29-33`).

### LocalStack Terraform

`make infra-local` (after `make up`) applies `infra/localstack` and runs
`check.py` (`Makefile:59-60`). CI does the same in the `e2e` job when the
`LOCALSTACK_AUTH_TOKEN` secret is set (`.github/workflows/ci.yml:94-116`).
Only the messaging module is applied: the LocalStack licence in use has no
Cognito, ECS, RDS, ELB, CloudFront, WAF, ECR or SES v2 (ADR 0009).

### Staging

Sized to be cheap: one NAT, one Aurora instance (so not multi-AZ) at
0.5-4 ACU, one task per service up to 2-4, no Bot Control, no Cognito threat
protection (`infra/envs/staging/main.tf:65-90`). Deployed automatically from
`main` by the deploy workflow. Demo data may be loaded with a one-off task
(runbook "Everyday operations").

### Prod, EU cell (eu-central-1)

The EEA, Switzerland and the UK (ADR 0013). Three NATs, a writer and a reader
at 1-64 ACU, the default `scale`, Bot Control and threat protection on
(`infra/envs/prod/main.tf:65-86`). Deployed by hand (`workflow_dispatch`,
`env=prod`) behind the `prod` GitHub environment's required reviewer. Region
loss: downtime until the region returns, RPO minutes, RTO hours (runbook "A
whole region goes down").

### Prod, North America cell (ca-central-1): planned

**Nothing of this exists in the repository yet.** ADR 0013 decides a second
cell, a full copy of the platform module in ca-central-1 for the US and
Canada, with its own Aurora, Cognito pool, SES, SNS/SQS, S3 and Stripe
secrets and no replication between cells. The tasks are M-21 (the env root),
M-10 (a Stripe client per platform, secrets per cell), M-7 (Amazon Location
Service per cell), M-22 (the app picks the cell) and M-45 (per-cell CD and
dashboards) in [`TASKS.md`](TASKS.md). Like everything else it would be
validated and applied to LocalStack only.

What the committed Terraform would need for it (found while writing this; not
yet in any task beyond M-21 and M-45):

- `var.env` accepts only `staging` or `prod` (`infra/platform/variables.tf:4-7`)
  and every name is `cappy-<env>` (`network.tf:6`). A second prod cell in the
  **same account** would collide on globally named resources: IAM roles
  (`cappy-prod-<svc>-task`, `ecs.tf:231-235`; `cappy-prod-analytics-scrub`,
  `analytics.tf:93-99`), the Lambda function name (`analytics.tf:107`), S3
  buckets (`storage.tf:6-12`, `analytics.tf:6`, `synthetics.tf:9`) and the us-east-1 WAF ACL name
  (`edge.tf:158`). Names need a cell component, or the cell needs its own
  account.
- The deploy workflow hard-codes `AWS_REGION: eu-central-1`
  (`.github/workflows/deploy.yml:25`) and pushes images to one registry; ECR
  is regional, so the NA cell needs its own push or ECR replication.
- The CSP's `connect-src` allows only this cell's Cognito endpoint
  (`edge.tf:413`). One web bundle serving both cells (ADR 0013) needs both
  Cognito regions and both API hosts in it, and the per-cell CloudFront and
  web bucket become one global piece.
- The VPC CIDR is fixed at `10.40.0.0/16` (`network.tf:11`); fine while cells
  are never peered.

---

## 4. Security

### Network

- Nothing in the private subnets has a public address (`network.tf:26-33`);
  the ALB is the only thing in the public subnets besides NAT.
- **ALB**: 443 only from CloudFront's origin-facing prefix list
  (`edge.tf:68-74`), and a request without the origin secret header gets a
  403 (`edge.tf:116-139`). So the WAF cannot be bypassed by calling the ALB.
- **Tasks**: port 8000 only from other tasks (Service Connect) and the ALB
  (`ecs.tf:143-157`). Egress is open to `0.0.0.0/0` (`ecs.tf:159-163`),
  needed for Stripe, Cognito, SES and the AWS APIs through the NAT.
- **Database**: 5432 only from the tasks' security group (`data.tf:30-36`);
  TLS forced (`data.tf:46-49`) and `ssl=require` in every URL.
- `/internal/*` routes between services carry `X-Internal-Token`, the
  calling service's own token; the callee checks its hash against the
  callers it allows (`backend/libs/cappy_common/cappy_common/auth.py:242-261`,
  P-10), so a task that can reach port 8000 still cannot call a route its
  service is not allowed to. The gateway does not forward them (the canary
  and CD smoke test check `/api/internal/busy` answers 404,
  `journeys.js:32`, `deploy.yml:207`).

### IAM per service

Every service has two roles (`ecs.tf:165-260`):

- **Execution role** `cappy-<env>-<svc>-execution`: the AWS managed ECS
  execution policy (pull images, write logs) plus
  `secretsmanager:GetSecretValue` on exactly the secrets that service is given
  (`ecs.tf:190-204`), so each service reads only its own internal token. The
  migrate role reads the admin URL and the service URLs.
- **Task role** `cappy-<env>-<svc>-task`: X-Ray write (`:237-241`), ECS Exec
  channels (`:257`), and:

| Service | Its code may | Line |
|---|---|---|
| gateway | nothing else | 212 |
| matching | nothing else | 213 |
| catalog | `s3:Put/Get/DeleteObject` on `media/*` and `private/*` of the media bucket; `cloudfront:CreateInvalidation` on this distribution; `cognito-idp:AdminGetUser` on this pool (staff MFA check, P-3); `sns:Publish` on the event topic; consume its queue | 214-218, 250-255 |
| booking | `cognito-idp:AdminGetUser` on this pool (staff MFA check for dispute resolution and evidence); `sns:Publish` on the event topic; consume its queue | 219, 250-255 |
| payments | `sns:Publish` on the event topic; consume its queue | 220, 250-255 |
| notifications | `ses:SendEmail`/`SendRawEmail` only from `no-reply@<domain>`; `cognito-idp:AdminGetUser`, `ListUsers`, `AdminUserGlobalSignOut`, `AdminDeleteUser` on this pool; `sns:CreatePlatformEndpoint` on the push apps and publish/manage/delete `endpoint/*` (never the event topic); consume its queue | 221-227 |

"Consume" is `sqs:ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`,
`GetQueueAttributes` on that service's queue only (`ecs.tf:251-255`).
Notifications does not publish events. Before the push apps exist,
`CreatePlatformEndpoint` is scoped to any `app/*` in the account (`ecs.tf:8`).

Other roles: Firehose may only write the analytics bucket and invoke the
scrub Lambda (`analytics.tf:45-59`); the scrub Lambda may only write its logs
(`analytics.tf:93-104`); SNS may only put records to that stream
(`analytics.tf:117-131`); the canary role writes its bucket, logs,
`CloudWatchSynthetics` metrics and X-Ray (`synthetics.tf:34-45`).

Known limit (runbook "Known limits"): every publisher may publish any event
type to the one topic.

### GitHub OIDC roles

Created by `infra/bootstrap/main.tf:66-112`, no long-lived AWS keys anywhere.
Each role trusts the GitHub OIDC provider only when **all** hold
(`:95-102`): audience `sts.amazonaws.com`, ref `refs/heads/main`, the
workflow is `.github/workflows/deploy.yml@refs/heads/main`, and the subject is
that GitHub environment. Sessions last at most an hour (`:105`).

| Role | Environment | Policy | Used by |
|---|---|---|---|
| `cappy-github-images-staging` / `-prod` | staging / prod | `AmazonEC2ContainerRegistryPowerUser` | the `images` job |
| `cappy-github-deploy-staging` / `-prod` | staging / prod | `AdministratorAccess` | the `deploy` and `publish` jobs |

Pull requests get no AWS access (`ci.yml` has only `contents: read`).

### The deploy workflow's jobs

`.github/workflows/deploy.yml`: a push to `main` deploys staging; prod is
`workflow_dispatch` with `env=prod` (`:5-14`). One deploy per environment at
a time, never cancelled midway (`:20-22`). Workflow permissions default to
`contents: read`; each job asks for `id-token` only if it needs AWS (`:17-18`).

| Job | AWS | What it does | Lines |
|---|---|---|---|
| `images` | images role (ECR push only) | Builds each service image with buildx and pushes `cappy/<svc>:<sha>`, skipping tags that already exist (tags are immutable) | 30-59 |
| `deploy` | deploy role | Terraform only, plus the AWS CLI. Reads `legal`, `switches` and `feature_flags` from the GitHub environment's variables `LEGAL`, `SWITCHES` and `FEATURE_FLAGS` as `TF_VAR_*` (`:71-74`; `SWITCHES` defaults to all on) and stops at once if `LEGAL` is unset (`:83-84`). Then registers the migrate task definitions (targeted apply), runs every migrate task and fails if any exits non-zero, then a full apply, waits for services to be stable and checks each runs the task definition this deploy registered with rollout `COMPLETED` (a rolled-back service fails the job); outputs the public web config | 61-139 |
| `web` | **none** | `npm ci --ignore-scripts && npm run build` with the web config; uploads `web/dist` | 141-158 |
| `publish` | deploy role | Syncs the build to the web bucket (hashed assets `immutable` for a year; `index.html`, `sw.js`, `registerSW.js`, `manifest.webmanifest` `no-cache`; `.well-known` deep-link files as JSON, 5 min), invalidates the entry points, then smoke-tests the URL: `/` 200, `/api/categories` 200, `/api/internal/busy` 404, `/api/bookings` 401 | 160-208 |

Third-party code (package installs, image builds) never runs holding the
deploy role (P-2, `bootstrap/main.tf:62-65`).

### WAF

**Edge ACL** (CloudFront, `edge.tf:156-337`). Default allow; sampled
requests off on every rule, because they would keep bearer tokens in
us-east-1 for three hours (`:154-155`).

| Priority | Rule | Action |
|---|---|---|
| 1 | `rate-per-ip`: `waf_rate_limit` (2000) requests per 5 min per IP, except `/api/payments/webhooks/` | block |
| 2 | `writes-per-ip`: 300 POSTs per 5 min per IP, except webhooks | block |
| 10 | `AWSManagedRulesAmazonIpReputationList` | managed |
| 11 | `AWSManagedRulesCommonRuleSet`, with `SizeRestrictions_BODY` counted, not blocked (photo uploads; the gateway and catalog enforce their own limits) | managed |
| 12 | `AWSManagedRulesKnownBadInputsRuleSet` | managed |
| 13 | `AWSManagedRulesBotControlRuleSet` (COMMON), prod only; `SignalNonBrowserUserAgent`, `CategoryHttpLibrary`, `CategoryMonitoring` counted (store apps, canary); never applied to webhooks | managed |

Stripe webhooks are exempt from rate limits and Bot Control because Stripe
sends from few addresses; the endpoint verifies signatures instead.

**Cognito ACL** (regional, `identity.tf:124-180`). Sign-in and sign-up go
from the client straight to Cognito, past CloudFront: `auth-per-ip` blocks
above 100 requests per 5 minutes per IP (`:132-149`), plus the IP reputation
list (`:151-168`). Sampled requests are off here too. In prod, Cognito threat protection (compromised
credentials, adaptive authentication) is enforced too (`identity.tf:10-17`,
`envs/prod/main.tf:69`).

### CSP and headers

CloudFront's response headers policy on the web app (`edge.tf:400-440`):

- **CSP**: `default-src 'self'`; scripts from self and `js.stripe.com`;
  styles self plus `'unsafe-inline'` (React style attributes; scripts never
  get it); fonts self-hosted; images self, `data:`, `blob:`, `*.stripe.com`,
  and `images.unsplash.com` outside prod only (demo photos, ADR 0010);
  `connect-src` self, this region's Cognito and `api.stripe.com`; frames
  Stripe only; `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`,
  `frame-ancestors 'none'`.
- HSTS two years with subdomains and preload; `nosniff`; `X-Frame-Options:
  DENY`; `Referrer-Policy: strict-origin-when-cross-origin`.

The API sets the same non-CSP headers itself
(`backend/libs/cappy_common/cappy_common/app.py:114-117`) and marks
signed-in answers `private, no-store` (`app.py:166-170`). The Capacitor
shells do not load the web app through CloudFront and so run without this
CSP today (P-5 in `TASKS.md`).

### Secrets: where each one lives

None is in git. `.gitignore`d `.env` holds local ones (`.env.example`).

| Secret | Where | Set by |
|---|---|---|
| Aurora admin password | `random_password.db_admin` → `cappy-<env>/database-admin-url` (`data.tf:38-41`, `:129-136`) | Terraform (in state) |
| Per-service DB passwords | `random_password.db_service` → `cappy-<env>/<svc>/database-url`, `database-read-url` (`data.tf:95-127`) | Terraform; the migrate task sets the role's password |
| Internal tokens, one per service | `cappy-<env>/internal-token/<svc>` (`data.tf:150-165`); callees hold only their hashes (`INTERNAL_CALLERS`, `ecs.tf:71-74`) | Terraform |
| CloudFront origin secret | `random_password.origin_secret`, in the ALB rule and the CloudFront origin header (`edge.tf:9-12`) | Terraform |
| Stripe secret, publishable and webhook keys | `cappy-<env>/stripe` (`data.tf:169-171`) | an operator, by hand (runbook step 4); never in state |
| APNs key, FCM service account | in the SNS platform applications, created by an operator; only their ARNs reach Terraform (`push_app_arns`) | an operator |
| `legal` (company identity, not secret) | the GitHub environment variable `LEGAL` for CD; an operator's local `*.tfvars` otherwise, which `.gitignore` excludes since `35a742c` | an operator |
| LocalStack auth token | `.env` locally; the `LOCALSTACK_AUTH_TOKEN` repository secret in CI | the developer |
| Local Stripe test keys | `.env` | the developer |

Terraform state holds the generated secrets, so the state bucket is
encrypted, versioned and private (`bootstrap/main.tf:22-51`) and pull requests
never get AWS credentials. Rotation: runbook "Everyday operations".

### Encryption

- In transit: CloudFront `TLSv1.2_2021` to viewers (`edge.tf:567`), TLS 1.2
  to the ALB origin (`:470`), the ALB on a TLS 1.3/1.2 policy (`:114`),
  Postgres `rds.force_ssl` (`data.tf:46-49`). Inside the VPC, Service Connect
  calls are plain HTTP on 8000 between tasks.
- At rest: Aurora `storage_encrypted` (default key, `data.tf:67`); SNS with
  `alias/aws/sns` (`messaging/main.tf:26`); SQS SSE (`:33`, `:42`); Secrets
  Manager (its default key); the state bucket SSE-KMS
  (`bootstrap/main.tf:36-43`). The web, media, analytics and canary buckets
  set no encryption configuration and so get S3's default SSE-S3.

---

## 5. Operations

### Alarms

All go to the `cappy-<env>-alarms` topic and `alarm_email`.

| Alarm | Condition | Where |
|---|---|---|
| `api-5xx-rate` | ALB target 5xx above 2 % of requests, 2 of 3 minutes | `observability.tf:18-55` |
| `api-p99-latency` | ALB `TargetResponseTime` p99 above 1.5 s, 3 of 5 minutes | `:57-72` |
| `<svc>-dead-letters` | any message in a DLQ | `:74-88` |
| `<svc>-queue-age` | oldest message older than 300 s for 5 minutes | `:90-104` |
| `db-cpu` | Aurora CPU above 80 % for 10 minutes | `:106-117` |
| `db-at-max-capacity` | `ServerlessDatabaseCapacity` at 90 % of `db_max_acu` for 15 minutes | `:119-131` |
| `chargeback` | a `CHARGEBACK` line in the payments log (metric filter) | `:134-157` |
| `outbox-set-aside` | an `OUTBOX_SET_ASIDE` line in any database service's log: an event failed to publish 20 times and will not go out by itself (metric filter per service, D-14, since `235eeaa`; the relay logs it at `cappy_common/events.py:278-286`) | `:159-186` |
| `replica-lag` | reader more than 1 s behind for 5 minutes | `data.tf:193-206` |
| `ses-bounce-rate`, `ses-complaint-rate` | above 2 % / 0.05 % | `email.tf:54-80` |
| `canary-failing` | canary success below 100 % for two runs, missing data breaches | `synthetics.tf:66-80` |
| `slo-burning-fast` (composite) | page: burn 14.4× over 1 h **and** 5 min | `observability.tf:238-244` |
| `slo-burning` (composite) | ticket: burn 6× over 6 h **and** 30 min | `:246-251` |

**SLO burn alarms.** The Terraform implements one API-wide availability
objective, 99.5 % (budget 0.5 % of requests as 5xx, `observability.tf:188-201`).
Four metric alarms compute the 5xx share over 5 min, 1 h, 30 min and 6 h
(`:203-236`) with thresholds 7.2 % (14.4 × 0.5 %) and 3 % (6 × 0.5 %); the two
composites pair them, Google SRE workbook style. The per-journey objectives
in [`slo.md`](slo.md) (browse under 800 ms at 99.5 %, book and owner answers
at 99.9 %, money within 15 minutes at 99.95 %) are not yet separate alarms.
First look for each alarm: runbook "Alarms".

### The canary

`journeys.js:26-34`, every 5 minutes against `https://<domain>`: the web app
loads (200), `/api/categories` (200), `/api/search` without a token (401:
signed-in only, GOAL 13), `/api/app-config` (200), `/api/internal/busy` (404:
internal routes stay private), `/api/bookings` without a token (401).

### Dashboards

No CloudWatch dashboard is defined in Terraform. What there is: Container
Insights (enhanced) on the cluster (`ecs.tf:93-96`), which gives per-service
CPU, memory and task views; Performance Insights on every Aurora instance
(`data.tf:91`); X-Ray's service map from the ADOT traces; the Synthetics
console for the canary. Dashboards per cell are planned (M-45).

### Kill switches and feature flags

**Kill switches** (`variables.tf:86-94`) become environment variables:
`ACCEPTING_BOOKINGS` on booking, `PAYOUTS_ON` on payments,
`ACCEPTING_LISTINGS` on catalog (`ecs.tf:43`, `:47`, `:50`). The services read
them at start (`booking/routes.py:135`, `catalog/routes.py:529`,
`payments/handlers.py:91`, `:120`). Since `35a742c` the GitHub environment's
`SWITCHES` variable is the one place they are set (`deploy.yml:73`): change it
(for example `{"bookings":false,"payouts":true,"listings":true}`), then run
the deploy workflow for that environment. The apply registers new task
definitions and rolls the services with the same image, and later deploys keep
the setting. What each one does when off: runbook "Kill switches".

**Feature flags** (`variables.tf:101-105`) go to every service as
`FEATURE_FLAGS="name:percent,..."` (`ecs.tf:31`), parsed by
`backend/libs/cappy_common/cappy_common/flags.py`, served to the apps by the
gateway's `/api/app-config` (cached up to 5 minutes at CloudFront) and
enforced by the service that owns the rule (booking reads
`paidCancellationPolicies`, where anything under 100 counts as off:
`booking/settings.py:38-47`). Roll out by setting the GitHub environment
variable `FEATURE_FLAGS` (`deploy.yml:74`) to `newcheckout:5`, then 25, 50,
100, each followed by a deploy run; `0` turns it off for everyone.

Locally, set the same variables on the service in `compose.yaml` (for
example `ACCEPTING_BOOKINGS: "false"` on booking) and `docker compose up -d`.

### Backups and restore

- Aurora continuous backups: 14 days in prod, 3 in staging, so any second in
  that window can be restored (`data.tf:68`). Deletion protection and a final
  snapshot in prod (`:71-73`).
- Media bucket versioning, old versions kept 30 days (`storage.tf:31-51`).
- Terraform state versioned (`bootstrap/main.tf:29-34`).
- Restore procedure (point-in-time to a new cluster, then copy back or
  repoint the `database-url` secrets): runbook "Restoring the database".
  It has never been rehearsed.

### Deploy and rollback

- **Deploy**: [the workflow above](#the-deploy-workflows-jobs). The same
  image sha goes to staging and then to prod.
- **Automatic rollback**: the ECS circuit breaker if new tasks fail health
  checks, and the deployment alarms (`api-5xx-rate`, `slo-burn-page_short`)
  if users' errors rise during the roll (`ecs.tf:341-354`). The deploy job
  then fails because the primary deployment is not the new task definition.
- **Manual rollback**: run the deploy workflow for the previous commit on
  `main` (its images already exist, so the `images` job skips the build), or
  apply the env root with `-var image_tag=<previous sha>`.
- A failed migration stops the deploy before any service rolls (runbook
  "A deploy failed").

### Migrations

Each database service has its own migrations, run by
`python -m cappy_common.migrations <svc>` with `ADMIN_DATABASE_URL`
(creates the database and role, sets its password) and `DATABASE_URL`
(`ecs.tf:453-480`). CD runs them as one-off Fargate tasks before rolling the
services (`deploy.yml:93-114`); locally `local/run.sh:12-14` runs them at
container start. Old code keeps running against the new schema until the roll
completes, so migrations are expand-then-contract.

---

## 6. Capacity and cost

### The connection budget check

Aurora Serverless v2's `max_connections` is fixed by the **maximum** ACU,
and ECS autoscaling is how it runs out (resilience F24). A Terraform `check`
block (`data.tf:173-191`) computes:

- per task 15 connections (pool 5 + overflow 10), twice for catalog and
  booking (writer and reader), times each service's task maximum, times 2
  because a deploy runs up to 200 % of tasks;
- `max_connections = min(5000, floor(db_max_acu × 2 GiB / 9531392))`;
- and fails when peak ≥ 80 % of that.

| | Peak connections | `max_connections` | 80 % | Headroom |
|---|---|---|---|---|
| Prod (64 ACU, default `scale`) | 2 × (600 + 600 + 150 + 60) = 2820 | 5000 | 4000 | ok |
| Staging (4 ACU) | 2 × (120 + 120 + 30 + 30) = 600 | 901 | 720 | ok |
| Module defaults (16 ACU, default `scale`) | 2820 | 3605 | 2884 | ok, barely |

Raising a task maximum or lowering `db_max_acu` can fail this check. The
answer is a higher `db_max_acu`, lower maxima, or RDS Proxy (T-24, deferred
until roughly 500 tasks or 70 % of the maximum). The check is evaluated at
plan time, so it is not exercised by `terraform validate`.

### Autoscaling

Recapped from `ecs.tf:385-449`: CPU 60 % for every service, SQS backlog
(100 visible messages per task) for the four consumers, ALB 500 requests per
target for the gateway; bounds from `scale`. Aurora scales between
`db_min_acu` and `db_max_acu`. In-process limits in front of that: the
gateway sheds above 400 in-flight requests and 200 per upstream
(`backend/services/gateway/gateway/settings.py:25`, `:29`; resilience F1, F3).

### Main cost drivers

The code and docs state only two prices; for everything else see AWS pricing
for the region. The quantities below come from the Terraform.

| Driver | Prod quantity | Staging quantity | Stated price |
|---|---|---|---|
| Fargate tasks | at minimum 13 tasks, 5.75 vCPU and 11.5 GiB; up to 104 tasks | 6 tasks, 1.75 vCPU, 3.5 GiB; up to 20 | see AWS pricing |
| Aurora Serverless v2 | 2 instances × 1-64 ACU, plus storage, I/O and 14 days of backups; Performance Insights | 1 instance × 0.5-4 ACU | see AWS pricing |
| NAT gateways | 3, plus data processed (all egress except S3) | 1 | see AWS pricing |
| CloudFront | PriceClass_100, requests and transfer | same | see AWS pricing |
| WAF | 2 web ACLs, 5-6 rules at the edge, 2 at Cognito, per request | 2 ACLs | Bot Control "about $10/month + $1 per million requests" (`variables.tf:108`), prod only |
| Cognito | monthly active users; Plus tier in prod | Essentials | Plus "about $0.02 per monthly active user" (`variables.tf:114`); `TASKS.md` T-06 puts that at about $20k/month at 1M users |
| ALB | 1, plus LCUs | 1 | see AWS pricing |
| CloudWatch | logs (90 days prod), Container Insights enhanced, ~20 alarms, canary runs (8,640 a month at one per 5 minutes) | logs 14 days | see AWS pricing |
| SES, SNS, SQS, Firehose, the analytics scrub Lambda, S3, X-Ray | per use | per use | see AWS pricing |

Levers already in the code: one NAT in staging (`variables.tf:35-39`), the S3
gateway endpoint (`network.tf:79-85`), Bot Control and threat protection as
switches, ECR keeping only 50 images, log retention, analytics data to
Glacier IR after 90 days. A second cell (ADR 0013) roughly doubles all of it.

---

## 7. Local development

Prerequisites: Docker, `uv`, Node 22, Terraform 1.12 (for the infra targets),
and `LOCALSTACK_AUTH_TOKEN` in `.env` (compose refuses to start without it,
`compose.yaml:53`).

### `make` targets (`Makefile`)

| Target | What it does | Line |
|---|---|---|
| `help` | Lists the targets (the default) | 6 |
| `up` | Builds and starts the stack, waits for health, copies `.local/web.env` to `web/.env.development.local`, then `seed-demo`; since `42c777c` it ends by printing all four demo accounts (`host@`, `host2@`, `buyer@`, `staff@demo.cappy.local`) with their password and a pointer to `docs/GUIDE.md` | 9-15 |
| `down` | Stops the stack, keeps data | 17 |
| `clean` | Stops it and deletes volumes and `.local/*.env` | 20-22 |
| `logs` | Follows the six services' logs | 24 |
| `seed-demo` | Loads the demo world (additive; refuses outside local and staging), creates the demo buyer, second host and staff profiles and the second host's three listings through the API (`local/demo_profiles.py`), and with real Stripe gives demo owners verified test accounts | 27-34 |
| `codes` | The last 20 sign-up and reset codes from cognito-local's log, each with the email it went to (since `61b15b8`) | 36-37 |
| `confirm` | `make confirm EMAIL=… [ADMIN=1]`: marks a local account's email verified, confirms it if unconfirmed, and with `ADMIN=1` adds it to the `admin` group (`local/confirm.py`, cognito-local on :9229 only; since `61b15b8`) | 39-40 |
| `test` | ruff check, ruff format check, pytest; no Docker | 42-43 |
| `test-pg` | pytest including the Postgres tests, against the compose Postgres on 5433 | 45-46 |
| `test-stripe` | Starts stripe-mock on 12111 and runs the Stripe contract tests | 48-50 |
| `e2e` | The whole journey against the running stack (`local/e2e.py`) | 52-53 |
| `web` | `npm ci && npm run build` in `web/` | 55-56 |
| `infra-validate` | `terraform fmt -check` and `validate` in every root | 60-61 |
| `infra-local` | Applies `infra/localstack` and runs `check.py` | 63-64 |
| `openapi` | Regenerates `docs/api/*.json` | 68-69 |
| `bench` | Since `42c777c`: builds a throwaway database `scale` on the compose Postgres (5433) with 100 000 synthetic listings, times candidate and free-text search (mean of 10 runs after a warm-up), then drops it (`backend/services/catalog/bench/candidates.py`; results in `docs/bench.md`) | 73-74 |
| `load` | 50 users for 60 s: no 5xx, one winner per contested window | 76-77 |
| `load-spike` | 10× arrival rate for 60 s; shedding may answer 503 | 81-82 |
| `load-mixed` | Open-model mix: 90 % browse, 8 % signed in, contested bookings | 84-85 |
| `load-soak` | An hour at a steady rate; connections, memory and queue ages stay flat | 87-88 |

The web dev server is `cd web && npm run dev` (Vite; it proxies `/api` to the
gateway, `web/vite.config.ts:13`, `:89`).

CI's `web` job does more than `make web` (since `44a5520`,
`.github/workflows/ci.yml:43-61`): `npm ci --ignore-scripts` (no package
install scripts run), `npx tsc --noEmit -p .`, the build, then
`check:size`, `check:i18n`, `check:flags`, `check:attempt` and `check:a11y`,
each failing the job when broken.

### Ports

| Port | What |
|---|---|
| 8000 | gateway: the API at `http://localhost:8000/api` |
| 9229 | cognito-local (the browser signs in against it) |
| 4566 | LocalStack |
| 5433 | Postgres (user `cappy`), one database per service |
| 12111 | stripe-mock, only during `make test-stripe` |

All are bound to `127.0.0.1`. The services themselves are reachable only
inside the compose network, as in AWS.

### Demo accounts

Created by `local/bootstrap.py:62-71` (`DEMO`), with verified emails; `make
up` prints all four with the password (since `42c777c`), which is also in that
file.

| Role | Email |
|---|---|
| Host (the seeded owner `o1`, one listing) | `host@demo.cappy.local` |
| Second host (since `61b15b8`, GD-5): a new German owner (EUR; not Swiss, because the demo world has no Swiss places yet) in Neukölln, whose three listings `local/demo_profiles.py` makes through the API: an instant-book workshop, a freight (batch) van run, and a studio above the market's review threshold, which is held on a fresh stack until staff approve it; all on weekly schedules | `host2@demo.cappy.local` |
| Buyer | `buyer@demo.cappy.local` |
| Staff (in the `admin` group, for the admin console) | `staff@demo.cappy.local` |

`VITE_DEMO_ACCOUNTS` offers one-tap sign-in to these in the local web build
only; it is never set in a deploy (`local/bootstrap.py:221-225`). The
staff account works with its password alone locally: `ADMIN_MFA_REQUIRED` is
off unless deployed (`cappy_common/settings.py:80-83`, `:125-127`), because
cognito-local has no MFA.

### Known quirks

- The LocalStack licence in use covers S3, SNS, SQS and SES v1; not Cognito,
  ECS, RDS, ELB, CloudFront, WAF, ECR or SES v2. Hence cognito-local, and
  hence only the messaging module is applied to LocalStack (ADR 0009).
- LocalStack must run with `SQS_ENDPOINT_STRATEGY=off` (`compose.yaml:55`);
  other URL styles break the Terraform provider.
- cognito-local needs `tty: true` or its log (which carries sign-up codes)
  is buffered (`compose.yaml:60-62`); it issues tokens with
  `iss=http://0.0.0.0:9229/<pool>`, which is why the expected issuer and the
  JWKS URL are separate settings (`local/bootstrap.py:204-205`); it does not
  set `email_verified` on confirmation; and it answers 500 on
  `GlobalSignOut`.
- Sign-up codes are not emailed locally: `make codes` (with the address each
  went to). A fresh account gets no email until `make confirm EMAIL=…`,
  because cognito-local leaves `email_verified` false.
- cognito-local cannot sign a person out on other devices (no global
  sign-out), so sign-out-everywhere does not end another browser's session
  locally once it refreshes (GD-4, a stated limitation). Since `42c777c`
  `docs/runbook.md` lists this with the other local-only differences (staff
  MFA off, the short windows) under "Local stack only: what behaves
  differently".
- Booking's `START_EARLY_MINUTES` is huge locally so the e2e can hand over
  at once, and matching's `MIN_LEAD_MINUTES` is 5; deployed, the defaults
  hold and settings refuse the local values (`compose.yaml:92`, `:104`).
- `make test-pg` and `make e2e` need `make up` first.

---

## 8. How to keep this file true

This is one of the living docs named in `CLAUDE.md`: any change that alters
what it says updates it **in the same commit**, by whoever makes the change,
agents included. In practice:

- **Changing anything under `infra/`, `compose.yaml`, `local/`, the
  `Makefile` or `.github/workflows/`**: update the matching section here and
  its `file:line` references. A new variable goes in the variables table with
  its default and any env override; a new resource goes under its file; a new
  alarm goes in the alarms table; a new IAM permission goes in the IAM table.
- **Adding a service**: `scale`, the IAM table, the connection budget (if it
  has a database), the consumers map in all four places listed under
  `data.tf`, the compose table and the diagram.
- **Adding a cell or environment**: section 3's table, and move the North
  America cell from "planned" to what it is once M-21 lands.
- **Anything that costs money** (a NAT, a managed rule group, a tier):
  section 6.
- **Never mark something applied that was only validated.** Nothing is
  applied to real AWS (GOAL 12); LocalStack is the only apply.
- A decision that changes why the infrastructure is shaped this way needs a
  new ADR, not only an edit here.
- Document the committed state. Line references drift: when a file changes,
  check the references into it (`git grep -n` for the resource name).
