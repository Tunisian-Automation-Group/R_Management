# Infrastructure

> **Deploys are off by default.** `deploy.yml` runs only when the repository
> variable `DEPLOY_ENABLED` is `true` (since `9637675`); until the owner sets it,
> a push or merge to `main` runs CI only and nothing reaches AWS.

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
as of `969bef8` (`e2f6bea` to `969bef8`, plus `bed48cd`, which landed just
before the last sync and was not in it): a rollback that swaps only the
services' images (`rollback` input, Terraform and migrations from `main`'s
head) with migrations kept expand-only by a test, the SNS topic conditions
(`aws:SourceAccount` on the alarms and tickets topics, only the three
publishers on the event topic), a prod plan that **fails** without a pager
unless `allow_no_pager`, `check:release` in CI's web job, the cost estimate
in [`INFRA-cost.md`](INFRA-cost.md), and backup retention and the restore's
deletion replay (`e50a24a`, runbook and `retention.md`). The other commits
of the round are web and docs only. The sync before, as of `0a74b1c`
(`174028c` to `0a74b1c`), covered: account security
(`security.tf`: CloudTrail, GuardDuty, Security Hub, root-use and IAM-change
alarms), backups and budgets (`backup.tf`: AWS Backup into a locked vault,
a monthly budget, cost anomaly detection), two alarm severities (a
`…-tickets` topic beside the paging `…-alarms` topic, and `pager_endpoint`),
the operator's identity and the store-app values in `web_config` with the
`VITE_RELEASE` guard, deploys only from a green CI run on `main` with a
`release` input for rollback, the previous release's web assets kept 30
days, payments' `cognito-idp:AdminGetUser` (the staff chargeback routes),
the Stripe Link entries in the CSP, and `check:tokens` and `check:contrast`
in CI's web job. The sync before, as of `1cb2d67` (`090c890` to `1cb2d67`),
covered: `check:money` in CI's web job,
payments' local `LEGAL_VAT_ID` placeholder (refused deployed),
`VITE_MIN_LEAD_MINUTES` in `web/.env.example`, the demo listings without the
seed's dated windows, five German districts in the seed and the runbook's
local plain-sign-out note. The sync before, as of `9107ad2` (`e2e77ab` to
`9107ad2`), covered: the `admin-lead` Cognito group in
Terraform, `COGNITO_ENDPOINT_URL` in compose's shared env block, the local
dispute and late-return timers (`DISPUTE_OFFER_MINUTES=10`,
`LATE_RETURN_EARLY_MINUTES`), the analytics scrub keeping only what and when
of a `staff.action`, and matching's staff MFA check (the staff listing
preview's offers and quote, routed by the gateway to matching). The sync
before, as of `4e86866` (`7444e37` to `4e86866`), covered: TLS on every hop inside the VPC
(P-11: Service Connect TLS from a private CA, HTTPS from the ALB to the
gateway, Aurora `verify-full`), dependency audits in CI and Dependabot plus
an audited ECS Exec (P-32), per-journey burn alarms and SLI queue-age
thresholds (T-35c), the cell in every name and a region and cell per deploy
environment (M-46), booking's `cognito-idp:ListUsers`, the `staff.action`,
`booking.dispute_offer` and `booking.notice` subscriptions, and `make confirm
LEAD=1`. The private CA is a new cost ([§6](#main-cost-drivers)). The sync
before covered `42c777c` and `2257182`.

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
   |                     |                 | Service Connect (TLS) <svc>:8000    |
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
   Alarms: CloudWatch --> SNS cappy-<env>-alarms (page) --> email + pager
                      --> SNS cappy-<env>-tickets (ticket) --> email
   Account: CloudTrail (object-locked bucket), GuardDuty, Security Hub;
            AWS Backup vault (locked), a monthly budget, cost anomalies
```

Where each box is defined: CloudFront, WAF, ALB `infra/platform/edge.tf`;
Cognito and its WAF `infra/platform/identity.tf`; VPC `infra/platform/network.tf`;
ECS `infra/platform/ecs.tf`; Aurora and secrets `infra/platform/data.tf`;
SNS/SQS `infra/modules/messaging/main.tf`; SES `infra/platform/email.tf`;
buckets `infra/platform/storage.tf`; analytics `infra/platform/analytics.tf`;
alarms `infra/platform/observability.tf`; canary `infra/platform/synthetics.tf`;
CloudTrail, GuardDuty and Security Hub `infra/platform/security.tf`; AWS
Backup, the budget and cost anomaly detection `infra/platform/backup.tf`.

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
CI pins Terraform 1.12.2 (`.github/workflows/ci.yml:95`). State locking is
S3-native (`use_lockfile = true`, `infra/envs/prod/main.tf:9`).

All names start with `local.name = "cappy-${var.cell}-${var.env}"`
(`infra/platform/network.tf:6`; since `7444e37`, M-46: before, `cappy-<env>`),
so two cells can share an account without their IAM roles, buckets, Lambda or
us-east-1 WAF ACL colliding. Below, `cappy-<env>` in a name reads
`cappy-<cell>-<env>` (`cappy-eu-prod` today). Default tags `app`, `env`,
`cell`, `managed_by` come from the env roots' providers
(`infra/envs/prod/main.tf:19-24`).

### `infra/platform/variables.tf`: the inputs

| Variable | Default | Staging | Prod | Line |
|---|---|---|---|---|
| `env` | (required; `staging` or `prod` only) | `staging` | `prod` | 1 |
| `region` | `eu-central-1` | the env root's `var.region` (default `eu-central-1`; CD sets `TF_VAR_region` from the GitHub environment's `AWS_REGION`, since `7444e37`) | same | 10 |
| `cell` | `eu` (`eu` or `na` only, as in `markets.json`) | the env root's `var.cell` (default `eu`; CD sets `TF_VAR_cell` from the environment's `CELL`, since `7444e37`, M-46) | same | 18 |
| `domain` | (required) | `staging.cappy.app` | `cappy.app` | 27 |
| `zone_id` | (required) | `-var zone_id` from GitHub `vars.ZONE_ID` | same | 32 |
| `image_tag` | (required) | commit sha from CD | same | 37 |
| `az_count` | `3` | default | default | 42 |
| `nat_gateways` | `1` | `1` | `3` | 47 |
| `db_min_acu` | `0.5` | `0.5` | `1` | 53 |
| `db_max_acu` | `16` | `4` | `64` | 58 |
| `db_instances` | `2` (writer + reader) | `1` | `2` | 63 |
| `scale` | see below | smaller map | default | 69-85 |
| `alarm_email` | (required) | `vars.ALARM_EMAIL` | same | 87 |
| `waf_rate_limit` | `2000` per 5 min per IP | default | default | 92 |
| `switches` | all `true` | GitHub environment variable `SWITCHES` (JSON; all on when unset), as `TF_VAR_switches` | same | 98 |
| `legal` | (required: company, address, contact email, VAT ID, tax number; `register` optional, since `faebae7`: `email` and `register` feed the app's Impressum, privacy policy and DSA contact point, R2-1) | GitHub environment variable `LEGAL` (JSON), as `TF_VAR_legal` | same | 108 |
| `apps` | `{}` (Apple team id, Android release SHA-256, App Store and Play URLs, all `""`; since `faebae7`) | GitHub environment variable `APPS` (JSON), as `TF_VAR_apps` | same | 113 |
| `monthly_budget_usd` | `1000` (since `faebae7`, R2-4) | default | `4000` | 124 |
| `account_security` | `true`: CloudTrail, GuardDuty, Security Hub in this account (since `faebae7`, P-14); off only when the organisation runs them centrally | default | default | 130 |
| `pager_endpoint` | `""`, sensitive: the pager's SNS HTTPS integration URL (since `faebae7`, R2-6) | GitHub environment secret `PAGER_ENDPOINT`, as `TF_VAR_pager_endpoint` | same; since `bed48cd` a prod plan **fails** without it unless `allow_no_pager` (a `precondition`, `observability.tf:15-20`; before, a `check` block warned) | 142 |
| `allow_no_pager` | `false` (since `bed48cd`, R2-23): lets a prod apply go ahead without a pager, only on purpose | GitHub environment variable `ALLOW_NO_PAGER`, as `TF_VAR_allow_no_pager` | same | 136 |
| `feature_flags` | `""` | GitHub environment variable `FEATURE_FLAGS`, as `TF_VAR_feature_flags` | same | 149 |
| `bot_control` | `false` | default | `true` | 155 |
| `cognito_threat_protection` | `false` | default | `true` | 161 |
| `push_app_arns` | `{ ios = "", android = "" }` | default | default (set once the store apps exist) | 167 |

Env overrides: `infra/envs/staging/main.tf:62-138`, `infra/envs/prod/main.tf:62-137`.

`scale` (cpu units / MiB / min tasks / max tasks):

| Service | Default = prod (`variables.tf:77-84`) | Staging (`envs/staging/main.tf:82-89`) |
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
  `infra/localstack/main.tf:27-32`, `infra/localstack/check.py:13-46` and
  `local/bootstrap.py:30-63`. Since `235eeaa` a test keeps them in step
  (`backend/libs/cappy_common/tests/test_subscriptions.py`, D-13): the four
  copies must be equal, and each service must handle every type it receives
  (sign-out and deletion are handled by every runtime) and receive every type
  it handles. `person.signed_out` goes to booking, payments and
  notifications; `payment.identity_verified` goes to booking and, since
  `235eeaa`, catalog (the profile's `verified`); `listing.idle` (catalog's
  "no free time next week", since `61b15b8`) goes to notifications. Since
  `7444e37`, `staff.action` (booking's staff actions, for the one audit log)
  goes to catalog and `booking.dispute_offer` to notifications; since
  `22b5e0f`, `booking.notice` (how a dispute or a late-return claim ended)
  goes to notifications.
- **Who may publish** (since `bed48cd`, P-9): `aws_sns_topic_policy.events_publishers`
  (`:20-38`) denies `sns:Publish` on the event topic to every principal but
  the task roles of the services in `local.publishes` (catalog, booking,
  payments), so a leaked role elsewhere cannot forge `payment.authorised` or
  `booking.status_changed`. Reads and subscriptions in the account still go
  through IAM.
- **Database services** (`:5`): catalog, booking, payments, notifications.
  Matching and the gateway have no database.
- DB subnet group on the private subnets (`:40-43`); security group allowing
  5432 only from the tasks' security group (`:45-56`).
- Parameter group `aurora-postgresql16` with `rds.force_ssl = 1` and
  `log_min_duration_statement = 500` ms (`:63-74`).
- **Cluster** `cappy-<env>` (`:76-100`): Aurora PostgreSQL 16.6, Serverless v2
  (`db_min_acu`..`db_max_acu`), storage encrypted, backups 14 days in prod and
  3 in staging, window 02:00-03:00 UTC, deletion protection and a final
  snapshot in prod only, Postgres logs exported to CloudWatch.
- **Instances** (`:102-113`): `db_instances` × `db.serverless`, all promotion
  tier 1 so readers scale with the writer and a failover lands on a warm one;
  Performance Insights on.
- **Secrets** (Secrets Manager):
  - `cappy-<env>/<svc>/database-url` per database service, writer endpoint,
    `ssl=verify-full` (`:130`; `ssl=require` before `7444e37`, P-11: the
    certificate is now checked against the RDS CA bundle baked into the
    image, `backend/Dockerfile:17-20`); the per-service password is
    `random_password.db_service` (`:115-119`).
  - `cappy-<env>/<svc>/database-read-url` for catalog and booking, the reader
    endpoint (`:138-147`).
  - `cappy-<env>/database-admin-url`, seen only by the migrate task (`:149-156`).
  - `cappy-<env>/internal-token/<svc>`, one per service except the gateway,
    holding `<svc>:<48 random characters>` for its own `/internal/*` calls
    (`:170-185`, P-10). Who may call whom is `local.internal_callers`
    (`:160-167`): catalog ← matching, booking; matching ← booking; booking ←
    matching, catalog; payments ← booking, catalog; notifications ← catalog.
    A callee gets only the sha256 of each caller's token (`INTERNAL_CALLERS`,
    `ecs.tf:71-74`), never the token.
  - `cappy-<env>/stripe`, an empty secret; its value is put in by hand
    (`:189-191`, runbook "First deploy" step 4).
- **Connection budget check** (`:193-211`), see [§6](#6-capacity-and-cost).
- **Replica lag alarm**: `AuroraReplicaLag` above 1 s for 5 minutes (`:213-226`).

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
- **Groups** `admin` for staff and `admin-lead` for leads (`identity.tf`,
  `aws_cognito_user_group.admin` and `.admin_lead`); membership is granted by
  hand. A lead is in both: the services read a lead as the staff claim also
  holding `admin-lead` (`STAFF_LEAD_VALUE`, `cappy_common/settings.py`, H-6).
  Locally `make confirm … LEAD=1` creates and fills it.
- **Cognito WAF** (`:124-180`), see [§4](#waf).

### `infra/platform/ecs.tf`: compute

- **Cluster** `cappy-<env>` with Container Insights `enhanced` and a Service
  Connect namespace (`:93-115`). Since `7444e37` (P-32) ECS Exec sessions are
  logged (`execute_command_configuration`, `logging = "OVERRIDE"`, `:102-111`)
  to their own log group `/ecs/cappy-<env>/exec`, kept 365 days
  (`:117-120`); CloudTrail records who opened each session.
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
  `http://<name>:8000` (`:11`, `:357-410`). Since `7444e37` (P-11) Service
  Connect speaks **TLS** between the proxies, with short-lived certificates
  from the private CA in `tls.tf` (`tls {}`, `:400-407`); the code still
  calls `http://<name>:8000` on its own proxy. Only the gateway is registered
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
- The gateway's container gets `TLS_SELF_SIGNED=true` (`:40`): the image's
  start command then makes a key and self-signed certificate in `/tmp/tls`
  (`python -m cappy_common.selfsigned`) and uvicorn serves HTTPS
  (`backend/Dockerfile:25-27`); its health check calls
  `https://localhost:8000/healthz` without verifying (`ecs.tf:319`).
- IAM roles, security groups: see [§4](#4-security).

### `infra/platform/tls.tf`: encryption inside the VPC (P-11, since `7444e37`)

- A private CA `aws_acmpca_certificate_authority.internal`, ROOT, in
  `SHORT_LIVED_CERTIFICATE` mode, EC P-256, subject `cappy-<env>.internal`,
  7-day permanent deletion window (`:15-27`), with its self-signed root
  certificate (10 years) installed (`:29-45`).
- A KMS key for Service Connect to keep each task's private key encrypted,
  rotation on (`:47-51`).
- A role `cappy-<env>-service-connect-tls` that ECS assumes, with the managed
  `AmazonECSInfrastructureRolePolicyForServiceConnectTransportLayerSecurity`
  (`:53-71`).
- The ALB-to-gateway leg does not use this CA: the gateway's certificate is
  self-signed and the ALB encrypts without verifying it, as AWS documents for
  targets.

### `infra/platform/edge.tf`: CloudFront, WAF, ALB (ADR 0008)

- **Certificates** (`:16-55`): ACM in us-east-1 for `<domain>` (CloudFront)
  and in the cell region for `origin.<domain>` (ALB), DNS-validated in the
  hosted zone.
- **ALB** `cappy-<env>` (`:84-92`) in the public subnets; drops invalid
  header fields; deletion protection in prod; 30 s idle timeout. Its security
  group admits 443 only from the CloudFront origin-facing managed prefix list
  and sends only to the tasks on 8000 (`:59-82`).
- **Target group** for the gateway, IP targets, health check `/readyz`
  every 10 s, 20 s deregistration delay (`:94-110`). Protocol **HTTPS**
  for traffic and health checks since `7444e37` (P-11; HTTP before).
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
  `support:<who>` to `staff` (since `747ed6b`), keeps only `action`,
  `targetType` and `at` of a `staff.action` (since `b5cdd93`,
  `STAFF_ACTION_FIELDS`, with a self-check), and drops anything it cannot
  parse ([`DATA.md`](DATA.md) §3.1). Its role has only
  `AWSLambdaBasicExecutionRole` (`:93-104`).
- SNS subscribes the Firehose to **every** event, raw delivery (`:133-139`),
  through a role that can only put records (`:117-131`).
- Glue database and table `cappy_events` with date partition projection, so
  Athena needs no crawler (`:142-189`). Queries: [`analytics.md`](analytics.md).

### `infra/platform/observability.tf`: alarms

See [§5 Alarms](#alarms). Since `faebae7` (R2-6) two SNS topics, one per
severity: `cappy-<env>-alarms` pages, `cappy-<env>-tickets` is looked at in
working hours (`:9-16`). Both have an email subscription to `alarm_email`
(`:17-28`); the pages topic also gets an HTTPS subscription to
`pager_endpoint` when it is set (`:39-45`). Since `bed48cd` (R2-23) a
`precondition` on the alarms topic **fails** a prod plan without a pager
(`:12-20`), unless `allow_no_pager = true` says it is on purpose (a
rehearsal before on-call exists); before, a `check` block only warned.
`local.alarm_actions` and `local.ticket_actions` point alarms at the two
(`:47-50`).

### `infra/platform/security.tf`: account detection (since `faebae7`, P-14)

All behind `account_security` (count 0 when off, `:6-8`):

- **CloudTrail** `cappy-<env>-trail`: multi-region, global service events,
  log file validation (`:93-103`), into a bucket with **object lock in
  compliance mode for 365 days**, so nobody, the deploy role included, can
  delete or shorten a log (`:13-28`), public access blocked (`:30-37`), and a
  bucket policy for CloudTrail only (`:39-62`). A copy goes to CloudWatch Logs
  `/cappy/<env>/cloudtrail`, kept 90 days (`:65-91`).
- **GuardDuty** detector, findings every 15 minutes (`:105-109`); findings of
  severity 7 and above go to the pages topic through an EventBridge rule
  (`:123-137`, topic policy `:139-169`; since `bed48cd`, R2-23, CloudWatch may
  publish only with this account as `aws:SourceAccount`, and EventBridge only
  from this account's GuardDuty rule, `aws:SourceArn`).
- **Security Hub** with AWS Foundational Security Best Practices (`:111-119`).
- Two metric filters on the trail's log group and their alarms
  (`Cappy/Security`): `root-used` (the root user doing anything; pages) and
  `iam-changed` (policy attachments, inline policies, new access keys; a
  ticket, since deploys change IAM on purpose) (`:171-205`).

### `infra/platform/backup.tf`: backups and budgets (since `faebae7`)

- **AWS Backup** (R2-5): a vault `cappy-<env>-vault` under **Vault Lock in
  compliance mode** (35 to 400 days; the lock is fixed after 3 days, `:10-20`),
  a plan with a daily rule kept 35 days and a monthly rule kept 365 days in
  prod (35 in staging) (`:22-42`), a role with the managed backup and restore
  policies (`:44-61`), and a selection of the Aurora cluster and the media
  bucket (`:64-70`). A failed, aborted or expired backup job opens a ticket
  (EventBridge, `:71-84`).
- **Budget** (R2-4): `cappy-<env>-monthly`, `monthly_budget_usd` filtered on
  the `env` cost allocation tag (activated once in Billing, runbook step 1);
  a ticket at 80 % of the forecast and at 100 % of the actual (`:115-144`).
- **Cost anomaly detection**: a per-service monitor and an immediate
  subscription for anomalies of $50 or more, to the tickets topic
  (`:146-167`). The tickets topic's policy lets CloudWatch, EventBridge,
  Budgets and cost alerts publish (`:86-113`), since `bed48cd` (R2-23) only
  with this account as `aws:SourceAccount`.

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
(`:45-60`; public values): `VITE_COGNITO_REGION`, `VITE_COGNITO_CLIENT_ID`,
and since `faebae7` (R2-1) `VITE_RELEASE=1`, the operator's identity from
`legal` (`VITE_LEGAL_COMPANY`, `_ADDRESS`, `_EMAIL`, `_VAT` (the VAT ID, or
the tax number without one), `_REGISTER`) and the store values from `apps`
(`VITE_APPLE_TEAM_ID`, `VITE_ANDROID_SHA256`, `VITE_APP_STORE_URL`,
`VITE_PLAY_STORE_URL`). `VITE_RELEASE=1` switches on the web build's
release guard (`releaseProblems`, since `bed48cd` in `web/release.ts`, which
`web/vite.config.ts` imports and `npm run check:release` tests in CI): the build fails when
the company, address or email is empty, the email is not an address, the
Android fingerprint is not 32 colon-separated hex bytes (or all zeros), or
the Apple team id is not 10 characters. Without an Apple team id or Android
fingerprint the build publishes no `.well-known` app-link file at all (a
placeholder would verify nothing). The env roots expose every output as
`output "platform"`.

### `infra/envs/staging/main.tf` and `infra/envs/prod/main.tf`

Each sets the backend, the two providers (cell region and us-east-1), takes
`image_tag`, `zone_id`, `alarm_email`, `switches`, `legal`, `feature_flags`,
since `faebae7` `apps` and `pager_endpoint`, and since `bed48cd`
`allow_no_pager` (default `false`) (`:83-107`) as variables, and
calls `../../platform` with the sizes in the tables above. Prod additionally
turns on `cognito_threat_protection` and `bot_control`
(`infra/envs/prod/main.tf:112`, `:133`) and sets `monthly_budget_usd = 4000`
(`:136`). CD sets `legal`, `apps`, `switches`, `feature_flags` and
`allow_no_pager` from the GitHub environment's variables `LEGAL`, `APPS`,
`SWITCHES`, `FEATURE_FLAGS` and `ALLOW_NO_PAGER`, and `pager_endpoint` from
the secret `PAGER_ENDPOINT` (`TF_VAR_*`, `.github/workflows/deploy.yml:118-123`); the env roots'
comments say so, with an example of each value. A local apply passes the
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
`terraform validate` (`Makefile:56-57`, `.github/workflows/ci.yml:90-101`).
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
  shortcuts cannot reach staging or prod. Payments' `LEGAL_VAT_ID` defaults
  to the placeholder "DE000000000 (local)" since `1cb2d67` (V7-10), so a
  local invoice shows both issuer lines; a deployed payments refuses it
  ("LEGAL_VAT_ID must be the operator's", `payments/settings.py`). The web
  dev server assumes the local 5-minute lead for the listing plate's "free
  from" time, builds the deployed 120 (`VITE_MIN_LEAD_MINUTES`, in
  `web/.env.example` since `73610c4`).
- **Stripe CLI profile.** With `COMPOSE_PROFILES=stripe`,
  `PAYMENTS_PROVIDER=stripe` and test keys in `.env`, the `stripe` container
  listens for the five webhook events the prod endpoint subscribes to and
  forwards them to `http://gateway:8000/api/payments/webhooks/stripe`
  (`compose.yaml:127-137`); `make seed-demo` then gives every demo owner a
  verified test connected account (`Makefile:29-33`).

### LocalStack Terraform

`make infra-local` (after `make up`) applies `infra/localstack` and runs
`check.py` (`Makefile:59-60`). CI does the same in the `e2e` job when the
`LOCALSTACK_AUTH_TOKEN` secret is set (`.github/workflows/ci.yml:103-130`).
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

What the committed Terraform has for it, and still needs:

- Since `7444e37` (M-46) every name carries the cell, `cappy-<cell>-<env>`
  (`network.tf:6`, `var.cell` `eu` or `na`, `variables.tf:18-25`), so a
  second cell in the same account no longer collides on IAM roles, the
  Lambda, S3 buckets or the us-east-1 WAF ACL. The deploy workflow reads the
  region and cell from the GitHub environment's `AWS_REGION` and `CELL`
  variables (defaults `eu-central-1`, `eu`; `.github/workflows/deploy.yml:58-62`,
  `:100-105`, `:210-215`), passes them as `TF_VAR_region` and `TF_VAR_cell`, and
  a cell other than `eu` gets its own state key `<cell>/<env>/terraform.tfstate`
  (in the `deploy` and `publish` jobs' `terraform init`); `eu` keeps the first key.
- Still missing: an env root for the NA cell (M-21), and images: the workflow
  pushes to one registry and ECR is regional, so the NA cell needs its own
  push or ECR replication.
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
  TLS forced (`data.tf:46-49`) and `ssl=verify-full` in every URL (since
  `7444e37`; `PGSSLROOTCERT` is the RDS global bundle in the image).
- **Inside the VPC** (since `7444e37`, P-11, `tls.tf`): Service Connect TLS
  between tasks, HTTPS from the ALB to the gateway.
- `/internal/*` routes between services carry `X-Internal-Token`, the
  calling service's own token; the callee checks its hash against the
  callers it allows (`backend/libs/cappy_common/cappy_common/auth.py:242-261`,
  P-10), so a task that can reach port 8000 still cannot call a route its
  service is not allowed to. The gateway does not forward them (the canary
  and CD smoke test check `/api/internal/busy` answers 404,
  `journeys.js:32`, `deploy.yml:264`).

### IAM per service

Every service has two roles (`ecs.tf:165-260`):

- **Execution role** `cappy-<env>-<svc>-execution`: the AWS managed ECS
  execution policy (pull images, write logs) plus
  `secretsmanager:GetSecretValue` on exactly the secrets that service is given
  (`ecs.tf:190-204`), so each service reads only its own internal token. The
  migrate role reads the admin URL and the service URLs.
- **Task role** `cappy-<env>-<svc>-task`: X-Ray write (`:261-265`), ECS Exec
  channels and, since `7444e37`, writing the ECS Exec session log
  (`logs:DescribeLogGroups`, and `CreateLogStream`/`PutLogEvents` on
  `/ecs/cappy-<env>/exec` only, `:280-286`), and:

| Service | Its code may | Line |
|---|---|---|
| gateway | nothing else | 232 |
| matching | since `ad9dee9`, `cognito-idp:AdminGetUser` on this pool (the staff MFA check for its staff routes, the preview's offers and quote, V6-2) | 233-234 |
| catalog | `s3:Put/Get/DeleteObject` on `media/*` and `private/*` of the media bucket; `cloudfront:CreateInvalidation` on this distribution; `cognito-idp:AdminGetUser` on this pool (staff MFA check, P-3); `sns:Publish` on the event topic; consume its queue | 235-239, 268-280 |
| booking | `cognito-idp:AdminGetUser` on this pool (staff MFA check for the staff tools and evidence); since `7444e37`, `cognito-idp:ListUsers` on this pool (the staff case view finds a member by email, H-9); `sns:Publish` on the event topic; consume its queue | 240-244, 268-280 |
| payments | since `faebae7`, `cognito-idp:AdminGetUser` on this pool (the staff MFA check on its chargeback routes, R2-3); `sns:Publish` on the event topic; consume its queue | 246-248, 268-280 |
| notifications | `ses:SendEmail`/`SendRawEmail` only from `no-reply@<domain>`; `cognito-idp:AdminGetUser`, `ListUsers`, `AdminUserGlobalSignOut`, `AdminDeleteUser` on this pool; `sns:CreatePlatformEndpoint` on the push apps and publish/manage/delete `endpoint/*` (never the event topic); consume its queue | 246-253 |

"Consume" is `sqs:ReceiveMessage`, `DeleteMessage`, `ChangeMessageVisibility`,
`GetQueueAttributes` on that service's queue only (`ecs.tf:268-280`).
Notifications does not publish events. Before the push apps exist,
`CreatePlatformEndpoint` is scoped to any `app/*` in the account (`ecs.tf:8`).

Other roles: `cappy-<env>-service-connect-tls`, assumed by ECS, holds only
the managed Service Connect TLS policy (`tls.tf:63-71`); Firehose may only write the analytics bucket and invoke the
scrub Lambda (`analytics.tf:45-59`); the scrub Lambda may only write its logs
(`analytics.tf:93-104`); SNS may only put records to that stream
(`analytics.tf:117-131`); the canary role writes its bucket, logs,
`CloudWatchSynthetics` metrics and X-Ray (`synthetics.tf:34-45`); since
`faebae7`, `cappy-<env>-trail-logs` lets CloudTrail write only its log group
(`security.tf:72-91`) and `cappy-<env>-backup` holds the managed AWS Backup
and restore policies (`backup.tf:44-61`).

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

`.github/workflows/deploy.yml`: since `faebae7` (R2-8) a release is a commit
whose `ci` run passed on `main`. A **completed `ci` run on `main`**
(`workflow_run`) deploys it to staging; prod, or a rollback, is
`workflow_dispatch` with `env`, an optional `release` sha (empty = the
latest on `main`) and, since `bed48cd` (R2-19), a `rollback` flag
(`:7-27`). What is deployed is `TAG` = the `release` input, else the commit
CI just passed, else the workflow's sha (`:39`); the images and the web
build come from `TAG`. Terraform and the migrations come from `INFRA_REF`
(`:40-47`): the same sha, except with `rollback: true`, when it is `main`'s
head, so an old release never runs its own Terraform (it would destroy newer
resources, the locked backup vault among them) nor its own migrations
(Alembic would not know the newer revision). One deploy per environment at a time, never
cancelled midway. Workflow permissions default to `contents: read`; each job
asks for `id-token` only if it needs AWS.

| Job | AWS | What it does | Lines |
|---|---|---|---|
| `gate` | **none** | Runs only on `main` and only when the triggering CI run succeeded; asks the GitHub API for a successful `ci.yml` run on `main` for `TAG` and fails without one, so a red or untested sha never deploys | 50-63 |
| `images` | images role (ECR push only) | Needs `gate`. Builds each service image with buildx and pushes `cappy/<svc>:<sha>`, skipping tags that already exist (tags are immutable, so a rollback builds nothing) | 65-100 |
| `deploy` | deploy role | Terraform only, plus the AWS CLI; checks out `INFRA_REF`. Reads the region and cell (`AWS_REGION`, `CELL`) and `legal`, `apps`, `switches`, `feature_flags`, `allow_no_pager` from the GitHub environment's variables `LEGAL`, `APPS`, `SWITCHES`, `FEATURE_FLAGS` and `ALLOW_NO_PAGER`, and `pager_endpoint` from the secret `PAGER_ENDPOINT`, as `TF_VAR_*` (`:116-123`; `SWITCHES` defaults to all on, `APPS` to `{}`, `ALLOW_NO_PAGER` to `false`) and stops at once if `LEGAL` is unset (`:133-134`). `terraform init` uses the cell's own state key for a cell other than `eu`. Then, except on a rollback (`:144-167`), registers the migrate task definitions (targeted apply) and runs every migrate task, failing if any exits non-zero; then a full apply with `image_tag = TAG`, waits for services to be stable and checks each runs the task definition this deploy registered with rollout `COMPLETED` (a rolled-back service fails the job); outputs the public web config | 102-192 |
| `web` | **none** | Checks out `TAG` (a rollback builds the old release's web app). Writes the web config to `web/.env.production.local` as a dotenv file Vite reads (each value JSON-quoted, so addresses with spaces and commas survive; before `faebae7` an `export $(…)` broke them), then `npm ci --ignore-scripts && npm run build`; the config carries `VITE_RELEASE=1`, so the release guard applies; uploads `web/dist` | 194-214 |
| `publish` | deploy role | Checks out `INFRA_REF`. Syncs the build to the web bucket **without `--delete`** (since `faebae7`, R2-9): hashed assets `immutable` for a year, and an asset under `assets/` is removed only when it is both absent from this build and older than 30 days, so a tab opened before the release still finds its lazy chunks (`:250-262`); `index.html`, `sw.js`, `registerSW.js`, `manifest.webmanifest` `no-cache`; `.well-known` deep-link files, when built, as JSON, 5 min; invalidates the entry points, then smoke-tests the URL: `/` 200, `/api/categories` 200, `/api/internal/busy` 404, `/api/bookings` 401 | 216-280 |

Third-party code (package installs, image builds) never runs holding the
deploy role (P-2, `bootstrap/main.tf:62-65`).

**Dependency audits** (since `7444e37`, P-32). CI's backend job exports the
locked third-party packages and runs `pip-audit --strict` on them
(`.github/workflows/ci.yml:37-40`); the web job runs `npm audit --omit=dev
--audit-level=high` (`:60`), so what ships to browsers and phones fails the
build on a high advisory. `.github/dependabot.yml` proposes weekly updates
as pull requests for GitHub Actions (grouped), the `uv` workspace in
`/backend`, npm in `/web` and the Docker base image in `/backend`, at most 5
open per ecosystem. Actions stay pinned to tags (their commit SHAs could not
be resolved offline when this was set up).

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

CloudFront's response headers policy on the web app (`edge.tf:402-448`):

- **CSP**: `default-src 'self'`; scripts from self, `js.stripe.com` and,
  since `faebae7` (R2-2, as Stripe's security guide lists it),
  `*.js.stripe.com`; styles self plus `'unsafe-inline'` (React style
  attributes; scripts never get it); fonts self-hosted; images self, `data:`,
  `blob:`, `*.stripe.com`, `*.link.com`, and `images.unsplash.com` outside
  prod only (demo photos, ADR 0010); `connect-src` self, this region's
  Cognito, `api.stripe.com`, `link.com` and `*.link.com`; frames
  `js.stripe.com`, `*.js.stripe.com`, `hooks.stripe.com` (3D Secure),
  `link.com` and `*.link.com` (Stripe Link); `object-src 'none'`,
  `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'`. The
  theme is set before first paint by `web/public/theme-init.js`, a script
  from the app's own origin, so `script-src 'self'` covers it. The walk
  through the card form with test keys under this CSP is still open (R2-2).
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
| Pager integration URL | the GitHub environment secret `PAGER_ENDPOINT` → `pager_endpoint` (sensitive; it ends up in state as the SNS subscription's endpoint) | an operator (runbook step 1) |
| LocalStack auth token | `.env` locally; the `LOCALSTACK_AUTH_TOKEN` repository secret in CI | the developer |
| Local Stripe test keys | `.env` | the developer |

Terraform state holds the generated secrets, so the state bucket is
encrypted, versioned and private (`bootstrap/main.tf:22-51`) and pull requests
never get AWS credentials. Rotation: runbook "Everyday operations".

### Encryption

- In transit: CloudFront `TLSv1.2_2021` to viewers, TLS 1.2 to the ALB
  origin (`edge.tf:471-472`), the ALB on a TLS 1.3/1.2 policy, and since
  `7444e37` (P-11) every hop inside the VPC too: HTTPS from the ALB to the
  gateway (a self-signed certificate made at task start, not verified by the
  ALB; `edge.tf:98`, `:103`), Service Connect TLS between tasks with
  certificates from the private CA (`ecs.tf:400-407`, `tls.tf`), and Postgres
  `rds.force_ssl` (`data.tf:46-49`) with `sslmode=verify-full` against the RDS
  CA bundle (`data.tf:110`, `:126`, `:135`; `backend/Dockerfile:17-20`).
- At rest: Aurora `storage_encrypted` (default key, `data.tf:67`); SNS with
  `alias/aws/sns` (`messaging/main.tf:26`); SQS SSE (`:33`, `:42`); Secrets
  Manager (its default key); the state bucket SSE-KMS
  (`bootstrap/main.tf:36-43`). The web, media, analytics and canary buckets
  set no encryption configuration and so get S3's default SSE-S3; so does
  the CloudTrail bucket (since `faebae7`), which is object-locked instead.
  The AWS Backup vault uses its default key.

---

## 5. Operations

### Alarms

Two severities since `faebae7` (R2-6; runbook "Severity and on-call"): a
**page** goes to `cappy-<env>-alarms` (mail to `alarm_email`, and the pager
when `pager_endpoint` is set); a **ticket** goes to `cappy-<env>-tickets`
(mail only). Before `faebae7` everything went to the one alarms topic.
Since `bed48cd` (R2-23) a prod plan fails without `pager_endpoint` unless
`allow_no_pager = true` (`observability.tf:12-20`), and both topics accept
alarms and rules from this account only (`aws:SourceAccount`).

| Alarm | Condition | Severity | Where |
|---|---|---|---|
| `api-5xx-rate` | ALB target 5xx above 2 % of requests, 2 of 3 minutes | page | `observability.tf:52-89` |
| `api-p99-latency` | ALB `TargetResponseTime` p99 above 1.5 s, 3 of 5 minutes | ticket | `:91-106` |
| `<svc>-dead-letters` | any message in a DLQ | page | `:108-122` |
| `<svc>-queue-age` | oldest message older than the queue's SLI for 5 minutes: payments 900 s, notifications 600 s (T-35c; `slo.md`), catalog and booking 300 s | ticket | `:124-140` |
| `db-cpu` | Aurora CPU above 80 % for 10 minutes | ticket | `:142-153` |
| `db-at-max-capacity` | `ServerlessDatabaseCapacity` at 90 % of `db_max_acu` for 15 minutes | ticket | `:155-167` |
| `chargeback` | a `CHARGEBACK` line in the payments log (metric filter): a chargeback opened, or one was lost | ticket | `:170-193` |
| `outbox-set-aside` | an `OUTBOX_SET_ASIDE` line in any database service's log: an event failed to publish 20 times and will not go out by itself (metric filter per service, D-14; the relay logs it at `cappy_common/events.py:278-286`) | ticket | `:198-222` |
| `replica-lag` | reader more than 1 s behind for 5 minutes | ticket | `data.tf:213-226` |
| `ses-bounce-rate`, `ses-complaint-rate` | above 2 % / 0.05 % | ticket | `email.tf:54-80` |
| `canary-failing` | canary success below 100 % for two runs, missing data breaches | page | `synthetics.tf:66-80` |
| `slo-burning-fast` (composite) | burn 14.4× over 1 h **and** 5 min | page | `observability.tf:274-280` |
| `slo-burning` (composite) | burn 6× over 6 h **and** 30 min | ticket | `:282-287` |
| `slo-<journey>-burning-fast`, `slo-<journey>-burning` (composites; journeys `browse`, `book`, `answer`) | per journey, the same page and ticket pairs (T-35c) | page / ticket | `:295-381` |
| `root-used` (since `faebae7`, P-14) | any root-user action in CloudTrail (metric filter `Cappy/Security`) | page | `security.tf:171-205` |
| `iam-changed` (since `faebae7`) | a policy attached or put, a policy version or access key created (deploys do this on purpose) | ticket | `security.tf:171-205` |
| GuardDuty finding, severity 7+ (since `faebae7`) | EventBridge rule to the pages topic | page | `security.tf:123-137` |
| Backup job failed, aborted or expired (since `faebae7`) | EventBridge rule | ticket | `backup.tf:72-84` |
| Budget: forecast above 80 %, actual above 100 % (since `faebae7`, R2-4) | `aws_budgets_budget` notifications | ticket | `backup.tf:115-144` |
| Cost anomaly of $50 or more (since `faebae7`) | Cost Explorer anomaly subscription, immediate | ticket | `backup.tf:146-167` |

**SLO burn alarms.** The Terraform implements one API-wide availability
objective, 99.5 % (budget 0.5 % of requests as 5xx, `observability.tf:229-237`).
Four metric alarms compute the 5xx share over 5 min, 1 h, 30 min and 6 h
(`:239-272`) with thresholds 7.2 % (14.4 × 0.5 %) and 3 % (6 × 0.5 %); the two
composites pair them, Google SRE workbook style.

**Per-journey burn alarms** (since `7444e37`, T-35c). Each gateway access
log line names its journey (`cappy_common/observability.py` `journey`:
`browse` for search, browse, a listing, its offers and reviews and `POST
/matches`; `book` for `POST /bookings`; `answer` for accept and decline).
Two log metric filters per journey on the gateway's log group count every
request and the bad ones (`Cappy/<env>` `JourneyRequests-<j>` and
`JourneyBad-<j>`, `:307-331`): bad is a 5xx, and for browse also slower than
800 ms. Budgets 0.5 % (browse) and 0.1 % (book, answer) (`:295-305`), the
same four windows and factors as the API-wide alarms (`:333-364`), paired
into a page and a ticket composite per journey (`:366-381`). The two event
journeys ([`slo.md`](slo.md): money within 15 minutes, mail within 10) are
alarmed on queue age at those thresholds. First look for each alarm:
runbook "Alarms".

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
`SWITCHES` variable is the one place they are set (`deploy.yml:109`): change it
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
variable `FEATURE_FLAGS` (`deploy.yml:110`) to `newcheckout:5`, then 25, 50,
100, each followed by a deploy run; `0` turns it off for everyone.

Locally, set the same variables on the service in `compose.yaml` (for
example `ACCEPTING_BOOKINGS: "false"` on booking) and `docker compose up -d`.

### Backups and restore

- Aurora continuous backups: 14 days in prod, 3 in staging, so any second in
  that window can be restored (`data.tf:88`). Deletion protection and a final
  snapshot in prod (`:91-93`).
- Media bucket versioning, old versions kept 30 days (`storage.tf:31-51`).
- Terraform state versioned (`bootstrap/main.tf:29-34`).
- Since `faebae7` (R2-5), **AWS Backup** copies the Aurora cluster and the
  media bucket into the vault `cappy-<env>-vault`, daily (kept 35 days) and
  monthly (kept a year in prod, 35 days in staging), under Vault Lock in
  compliance mode: no role in the account, the deploy role included, can
  delete a recovery point or shorten its retention (`backup.tf:10-70`). A
  failed job opens a ticket. The vault is in the cell's own region (EU data
  stays in the EU, ADR 0013); a copy to a second region or a separate backup
  account is not built (`backup.tf:6-8`).
- Restore procedure (point-in-time to a new cluster, then copy back or
  repoint the `database-url` secrets; or restore a recovery point from the
  vault when the cluster itself is gone): runbook "Restoring the database".
  Since `e50a24a` its step 3: before anyone uses restored data, publish
  again every `profile.deleted` event since the restore point (from the
  damaged cluster's outbox tables or the analytics lake), so every service
  forgets those people again, idempotently; only then point traffic at it.
  It has never been rehearsed.
- **Locked backups and erasure** (since `e50a24a`, `docs/retention.md`
  "Backups"): recovery points cannot be deleted early by anyone, so a deleted
  person's rows and photos stay in them until they expire (35 days daily, at
  most a year monthly in prod). They are never restored into the live system
  without that replay; the privacy notice must say so.

### Deploy and rollback

- **Deploy**: [the workflow above](#the-deploy-workflows-jobs). Since
  `faebae7` (R2-8) only a commit with a successful `ci` run on `main` is
  deployed: a green CI run deploys it to staging by itself, and prod is a
  manual run naming the release. The same image sha goes to staging and then
  to prod.
- **Automatic rollback**: the ECS circuit breaker if new tasks fail health
  checks, and the deployment alarms (`api-5xx-rate`, `slo-burn-page_short`)
  if users' errors rise during the roll (`ecs.tf:341-354`). The deploy job
  then fails because the primary deployment is not the new task definition.
- **Manual rollback** (since `bed48cd`, R2-19): Actions → deploy → Run
  workflow with the environment, `release:` the previous release's sha **and
  `rollback: true`**. Only the services' images (and the web build) change:
  Terraform comes from `main`'s head, no migrate task runs and the database
  stays where it is. Its images already exist, so the `images` job skips the
  build (minutes). Deploying an older sha *without* `rollback` runs that
  sha's own migrations and Terraform and stops safely at the migrate step.
  Or apply the env root from `main` with `-var image_tag=<previous sha>`.
  When the bad release migrated data the old code cannot read, or a contract
  step went out, fix forward on `main` instead (the kill switches hold the
  damage meanwhile). The web app's previous hashed assets stay in the bucket
  for 30 days, so open tabs keep working across a release and a rollback.
- A failed migration stops the deploy before any service rolls (runbook
  "A deploy failed").

### Migrations

Each database service has its own migrations, run by
`python -m cappy_common.migrations <svc>` with `ADMIN_DATABASE_URL`
(creates the database and role, sets its password) and `DATABASE_URL`
(`ecs.tf:453-480`). CD runs them as one-off Fargate tasks before rolling the
services (`deploy.yml:144-167`), never on a rollback; locally
`local/run.sh:12-14` runs them at container start. Old code keeps running
against the new schema until the roll completes, and a rollback runs the
previous release against the newer schema, so migrations **only expand**
(runbook "Releasing and rolling back": add nullable columns or columns with
defaults and write both, backfill in a later release, contract at least one
release after the last code that read it; that release cannot be rolled
back past). Since `bed48cd` a test enforces it:
`backend/libs/cappy_common/tests/test_migrations_expand_only.py` (in `make
test`, so in CI) parses every `upgrade()` and refuses `drop_column`,
`drop_table`, `rename_table` and a renaming `alter_column` unless the
migration carries `# contract: <release that stopped using it>`.
`downgrade()` may drop. Settings follow the same rule: a release may add an
environment variable with a default, never require one the previous release
lacks.

---

## 6. Capacity and cost

### The connection budget check

Aurora Serverless v2's `max_connections` is fixed by the **maximum** ACU,
and ECS autoscaling is how it runs out (resilience F24). A Terraform `check`
block (`data.tf:193-211`) computes:

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

The quantities below come from the Terraform. Since `bed48cd` (R2-4)
[`INFRA-cost.md`](INFRA-cost.md) estimates prod in the EU cell at **about
$1,550 a month at launch** (20,000 monthly active members; approximate
on-demand Frankfurt list prices, not a quote): Aurora ≈ $420, Cognito Plus
≈ $400, Fargate ≈ $240, NAT ≈ $120, then WAF, the private CA, CloudWatch,
GuardDuty and smaller lines; a fixed floor of about $350 whatever the
traffic, and Cognito Plus the line that grows fastest. Staging is roughly a
quarter of prod. It is to be checked in the AWS Pricing Calculator before
the first apply and replaced by the bill after the first month.

| Driver | Prod quantity | Staging quantity | Stated price |
|---|---|---|---|
| Fargate tasks | at minimum 13 tasks, 5.75 vCPU and 11.5 GiB; up to 104 tasks | 6 tasks, 1.75 vCPU, 3.5 GiB; up to 20 | see AWS pricing |
| Aurora Serverless v2 | 2 instances × 1-64 ACU, plus storage, I/O and 14 days of backups; Performance Insights | 1 instance × 0.5-4 ACU | see AWS pricing |
| NAT gateways | 3, plus data processed (all egress except S3) | 1 | see AWS pricing |
| CloudFront | PriceClass_100, requests and transfer | same | see AWS pricing |
| WAF | 2 web ACLs, 5-6 rules at the edge, 2 at Cognito, per request | 2 ACLs | Bot Control "about $10/month + $1 per million requests" (`variables.tf:108`), prod only |
| Cognito | monthly active users; Plus tier in prod | Essentials | Plus "about $0.02 per monthly active user" (`variables.tf:114`); `TASKS.md` T-06 puts that at about $20k/month at 1M users |
| ALB | 1, plus LCUs | 1 | see AWS pricing |
| CloudWatch | logs (90 days prod; the ECS Exec session log a year), Container Insights enhanced, ~40 alarms since the per-journey burn alarms (`7444e37`: 12 metric alarms and 6 composites more) and 6 more log metric filters, canary runs (8,640 a month at one per 5 minutes) | logs 14 days | see AWS pricing |
| AWS Private CA (since `7444e37`, P-11) | 1 CA in short-lived-certificate mode, plus a KMS key | same | "~$50 a month" for the short-lived mode (`tls.tf:12-13`) |
| CloudTrail, GuardDuty, Security Hub (since `faebae7`, P-14; `account_security`) | one multi-region trail (the first management trail is free; S3 for a year of object-locked logs, CloudWatch Logs 90 days), GuardDuty per analysed event, Security Hub per check | same | see AWS pricing |
| AWS Backup (since `faebae7`, R2-5) | Aurora and media recovery points, 35 daily and 12 monthly | 35 daily, 1 monthly | see AWS pricing |
| SES, SNS, SQS, Firehose, the analytics scrub Lambda, S3, X-Ray | per use | per use | see AWS pricing |

**Budgets** (since `faebae7`, R2-4): `monthly_budget_usd`, $1,000 by default
(staging) and $4,000 in prod (`infra/envs/prod/main.tf:134-136`: Aurora with
a reader, 3 NATs, Cognito Plus, Bot Control, the private CA at launch
traffic; `INFRA-cost.md` puts launch at about $1,550, so it leaves room for
a busy month and staging; raise it with real numbers). A forecast above 80 % or an actual
above 100 % opens a ticket, and so does a cost anomaly of $50 or more.

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
| `confirm` | `make confirm EMAIL=… [ADMIN=1] [LEAD=1]`: marks a local account's email verified, confirms it if unconfirmed, with `ADMIN=1` adds it to the `admin` group, and with `LEAD=1` (since `22b5e0f`) to `admin` and `admin-lead`, creating a group that does not exist yet (`local/confirm.py`, cognito-local on :9229 only; since `61b15b8`) | 39-40 |
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
gateway, `web/vite.config.ts:14-16`, `:106-107`).

CI's `web` job does more than `make web` (since `44a5520`,
`.github/workflows/ci.yml:49-73`): `npm ci --ignore-scripts` (no package
install scripts run), `npm audit`, `npx tsc --noEmit -p .`, the build, then
`check:size`, `check:i18n`, `check:flags`, `check:attempt`, `check:a11y`,
`check:money` (since `73610c4`), `check:contrast` (since `0a74b1c`: every
text colour token on the backgrounds it is used on, light and dark, WCAG AA,
`web/scripts/check-contrast.ts`; since `a2ed987` translucent colours are
measured over their background, 70 pairs), `check:release` (since
`bed48cd`, R2-21: the release guard, `releaseProblems` in `web/release.ts`,
refuses a `VITE_RELEASE=1` build without the operator's company, address or
a well-formed contact email, or with a malformed or all-zero Android
SHA-256 or Apple team id; `web/scripts/check-release.ts`) and
`check:tokens` (since `7051660`: no
literal text size, radius, hex or rgb colour, named Tailwind colour or
inline font size outside `theme.css`; the counts in
`web/scripts/tokens-allowlist.json` may only go down), each failing the job
when broken.

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

Created by `local/bootstrap.py:65-74` (`DEMO`), with verified emails; `make
up` prints all four with the password (since `42c777c`), which is also in that
file.

| Role | Email |
|---|---|
| Host (the seeded owner `o1`, one listing) | `host@demo.cappy.local` |
| Second host (since `61b15b8`, GD-5): a new German owner (EUR) in Neukölln, whose three listings `local/demo_profiles.py` makes through the API: an instant-book workshop (open every day 08:00-22:00 since `22b5e0f`), a freight (batch) van run (at most 2 pallets a booking), and a studio above the market's review threshold, which is held on a fresh stack until staff approve it; all on weekly schedules. Since `1cb2d67` (V7-11) `demo_profiles.py` also deletes the seed's dated windows (`w1`, `w2`…) on the plunge saw `l9` and the bandsaw before giving them the every-day schedule, so both are open 08:00-22:00 every day on a clean stack. The seed has had Swiss and Austrian places and owners since `7444e37` (a CHF listing in Zürich, no sign-in), and since `1cb2d67` (V7-29) five more German districts without listings: Altona (Hamburg), Maxvorstadt (München), Ehrenfeld (Köln), Bockenheim (Frankfurt am Main) and Plagwitz (Leipzig) | `host2@demo.cappy.local` |
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
  differently". Since `1cb2d67` it also notes (V7-28) that a plain **Sign
  out** leaves the access token working locally: cognito-local ignores
  `RevokeToken` for access tokens and issues them for 24 hours (real
  Cognito: 15 minutes, and revoked with their refresh token).
- Booking's `START_EARLY_MINUTES` is huge locally so the e2e can hand over
  at once, and matching's `MIN_LEAD_MINUTES` is 5; deployed, the defaults
  hold and settings refuse the local values (`compose.yaml:92`, `:104`).
- `COGNITO_ENDPOINT_URL` is in the shared env block of `compose.yaml`, so
  every service that asks Cognito (the staff MFA check, booking's case search
  by email, sign-out) goes to cognito-local, never to LocalStack.
- Local compose also sets `DISPUTE_OFFER_MINUTES=10` (a dispute goes to
  staff after 10 minutes without agreement) and
  `LATE_RETURN_EARLY_MINUTES=100000` (an owner may report a late return
  before the booked end); deployed settings refuse both
  (`booking/settings.py` `unsafe_reasons`).
- `make test-pg` and `make e2e` need `make up` first. Since `32338dd` the
  e2e signs up a second buyer of its own (`rival-<run>@example.com`) and
  deletes it at the end, so it no longer changes the demo buyer's home or
  uses up their daily booking limit.

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
  section 6, and its line in [`INFRA-cost.md`](INFRA-cost.md).
- **Never mark something applied that was only validated.** Nothing is
  applied to real AWS (GOAL 12); LocalStack is the only apply.
- A decision that changes why the infrastructure is shaped this way needs a
  new ADR, not only an edit here.
- Document the committed state. Line references drift: when a file changes,
  check the references into it (`git grep -n` for the resource name).
