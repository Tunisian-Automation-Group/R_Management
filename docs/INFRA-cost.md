# What prod costs a month at launch (R2-4)

An estimate for one cell (EU, `eu-central-1`) with the sizes in
`infra/envs/prod/main.tf` and the platform defaults. **Not a quote.** Prices
are approximate on-demand list prices for Frankfurt as of 2026, in USD,
without the free tier, taxes, savings plans or Reserved capacity. Before the
first apply, put these lines into the
[AWS Pricing Calculator](https://calculator.aws/) and replace every "≈" with
its answer. AWS Budgets (`backup.tf`, `monthly_budget_usd = 4000`) and Cost
Anomaly Detection warn if reality drifts.

## Assumptions (launch in DE/AT/CH)

| | Value | Why |
|---|---|---|
| Monthly active members | 20,000 | first months of three markets |
| API requests | 15 million / month (≈ 6 per second on average, 60 at peak) | ~25 sessions × 30 calls per active member |
| Web and photo traffic out of CloudFront | 200 GB / month | pages, JS, photos in 400/800 px |
| Photos stored | 100 GB (three renditions each) | ~20,000 listings × 5 photos |
| Emails | 200,000 / month | bookings, messages, codes |
| Logs ingested | 50 GB / month | JSON access and service logs |
| Database | one Aurora Serverless v2 cluster, writer + 1 reader, 1–64 ACU; average ≈ 2 ACU each at launch | `db_instances = 2`, `db_min_acu = 1` |
| Services | the minimum task counts of `scale` (below), x86 Fargate | `platform/variables.tf` `scale` |

Fargate at the minimum counts: gateway, catalog and booking 2 × (0.5 vCPU,
1 GB); matching 2 × (1 vCPU, 2 GB); payments 2 × (0.25 vCPU, 0.5 GB);
notifications 1 × (0.25 vCPU, 0.5 GB). That is 5.75 vCPU and 11.5 GB,
always on. Autoscaling adds tasks only under load.

## The estimate

| Service | What | ≈ per month |
|---|---|---:|
| **Aurora Serverless v2** | 2 instances × ≈ 2 ACU × 730 h × ≈ $0.14/ACU-h, plus ≈ 20 GB storage and I/O | **≈ $420** |
| **Cognito Plus** (threat protection) | 20,000 MAU × ≈ $0.02 (`variables.tf`, T-06) | **≈ $400** |
| **Fargate** | 5.75 vCPU × 730 h × ≈ $0.047 + 11.5 GB × 730 h × ≈ $0.0051 | **≈ $240** |
| NAT gateways | 3 × 730 h × ≈ $0.052 + ≈ 100 GB processed | ≈ $120 |
| Private CA (Service Connect TLS, short-lived mode) | from `tls.tf` | ≈ $50 |
| WAF (edge + Cognito) | 2 web ACLs, ~8 rules, 15 M requests, Bot Control (≈ $10 + $1 per M) | ≈ $55 |
| CloudWatch | 50 GB logs (≈ $0.63/GB), alarms, metric filters, dashboards | ≈ $50 |
| GuardDuty | CloudTrail management events, DNS and VPC flow analysis | ≈ $40 |
| Load balancer | 1 ALB, hours and LCUs | ≈ $35 |
| CloudFront | 200 GB (≈ $0.085/GB) + HTTPS requests | ≈ $35 |
| Security Hub (+ the AWS Config recording it needs) | Foundational standard checks | ≈ $30 |
| SES | 200,000 mails × ≈ $0.10 per 1,000 | ≈ $20 |
| Synthetics canary | every 5 minutes | ≈ $10 |
| S3 | media 100 GB, web, logs, analytics, CloudTrail, requests | ≈ $10 |
| SNS, SQS, Firehose, Athena, Lambda | events, push, analytics | ≈ $10 |
| Secrets Manager, KMS, Route 53, ECR, X-Ray, Backup | small fixed costs | ≈ $20 |
| **Total** | | **≈ $1,550** |

The budget of $4,000 leaves room for a busy launch month, a traffic spike
and staging (a smaller copy: 1 NAT, 0.5–4 ACU, no Bot Control or Cognito
Plus, roughly a quarter of prod).

## What grows with users

- **Cognito Plus is the line that scales fastest:** about $0.02 per monthly
  active user, so ≈ $20,000 a month at 1 million (T-06). Revisit before
  that: keep threat protection on for staff and risky sign-ins only, or
  price it against the fraud it stops.
- **Aurora** follows real load (ACU-hours), then storage and I/O; readers
  scale reads (`db_instances`). Past ≈ 32 ACU, compare I/O-Optimized.
- **Fargate** follows traffic through autoscaling; Graviton (ARM) tasks cut
  it by about a fifth when the images are built for arm64.
- **CloudFront and NAT** follow bytes: photos are the bulk, which is why they
  are served as 400/800/1600 px renditions.
- **The fixed floor** (NAT hours, private CA, WAF ACLs, GuardDuty, Security
  Hub, the canary) is about $350 whatever the traffic.

## How to keep this true

When a Terraform change adds a priced resource or changes a size, update the
line here in the same commit (CLAUDE.md "Living docs"), and after the first
real month replace the estimates with the bill's figures.
