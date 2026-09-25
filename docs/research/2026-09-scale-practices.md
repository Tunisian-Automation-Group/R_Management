# Scale and resilience practices for a two-sided marketplace (2026-09)

This is research done for Cappy. It draws on primary sources wherever
possible: the AWS Builders' Library and docs, Stripe, the Uber, Netflix,
Airbnb, Figma, Instacart and Shopify engineering blogs, Apple and Google
policy pages, and the Google SRE workbook. The tasks that came out of it are
in [`../TASKS.md`](../TASKS.md) (R-nn).

## Findings that changed our plan

| Finding | Source | What we do |
|---|---|---|
| Retry at one layer only, with capped exponential backoff and **full jitter**. Jitter periodic jobs too. | https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/ | R-3: jitter in relay, sweeps and client backoff. Only the calling edge retries. |
| An idempotency key replayed with **different parameters must be rejected**. Never hold a DB transaction open across the external call. | https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/ · https://medium.com/airbnb-engineering/avoiding-double-payments-in-a-distributed-payments-system-2981f6b070bb | R-2: booking stores a hash of the request next to its key. Intents are already created outside transactions. |
| Stripe webhooks are at-least-once and **unordered**. Re-fetch the object, and **reconcile** periodically. | https://docs.stripe.com/webhooks | R-1: a reconciliation sweep for payments stuck in an intermediate state. (Dedupe and re-fetch are already in place.) |
| Card authorisations expire after about 7 days. | https://docs.stripe.com/payments/place-a-hold-on-a-payment-method | Already safe: capture happens at accept, at most 24 h after the request. |
| Shed load at the server so accepted work still finishes. Prioritise user-initiated writes (booking, payment) over browsing. | https://aws.amazon.com/builders-library/using-load-shedding-to-avoid-overload/ · https://netflixtechblog.com/enhancing-netflix-reliability-with-service-level-prioritized-load-shedding-e735e6ce8f7d | T-01: bounded in-flight requests per gateway task, with writes reserved headroom. |
| A separate pool or budget per dependency (bulkheads). | https://aws.amazon.com/builders-library/workload-isolation-using-shuffle-sharding/ | T-03 |
| CloudFront honours `stale-while-revalidate` and `stale-if-error`: edge request coalescing, and the site survives origin errors. | https://aws.amazon.com/about-aws/whats-new/2023/05/amazon-cloudfront-stale-while-revalidate-stale-if-error-cache-control-directives/ | R-4 / T-07: public GETs say `s-maxage=30, stale-while-revalidate=60, stale-if-error=600`. |
| Caches create modal behaviour: the database must survive a cold cache. | https://aws.amazon.com/builders-library/caching-challenges-and-strategies/ | No application cache (Redis) until reader CPU calls for it. The load test runs uncached. |
| Aurora Serverless v2 `max_connections` is fixed by the **maximum** ACU (about 5,000 at 64 ACU). ECS autoscaling is the classic way to exhaust it. RDS Proxy when tasks × pool gets near the limit. | https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-serverless-v2.setting-capacity.html · https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-proxy.html | R-5: connection budget written down and checked in Terraform. Replica-lag alarm. Reader in promotion tier 1. T-24 (proxy) at the trigger. |
| Read-your-writes: reads that must see your own write go to the writer. | https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/Aurora.Replication.html | Already the case: `/me` and my bookings read the writer. Public reads use the reader. |
| Figma sharded only at several TB and billions of rows. | https://www.figma.com/blog/how-figma-scaled-to-multiple-databases/ | No sharding. A database per service already exists. Time-partition bookings and the outbox at ~100M rows. |
| Instacart moved search **off Elasticsearch onto Postgres** (FTS + pgvector). | https://tech.instacart.com/how-instacart-built-a-modern-search-infrastructure-on-postgres-c528fa601d54 | Stay on Postgres (trigram + GiST). OpenSearch at about 1M listings or when multilingual relevance matters. |
| PostGIS or GiST for radius and nearest queries. Uber uses H3 for bucketing and analytics. | https://www.uber.com/us/en/blog/h3/ | T-10: nearest-first index. H3 when pricing or demand analytics arrive. |
| Stripe's own limiters: token buckets per user and endpoint, a concurrency limiter, fleet shedding. | https://stripe.com/blog/rate-limiters | T-20 for card testing now. Redis token buckets at the first abuse signal. |
| Card testing: rate-limit intent creation per account, use Payment Element and Radar. | https://docs.stripe.com/disputes/prevention/card-testing | T-20, plus Radar on (the default). |
| Connect risk: the platform carries negative balances. Pause payouts for suspicious hosts. | https://docs.stripe.com/connect/risk-management | T-19 (chargebacks hold the payout). A first-payout hold is recorded as a business decision. |
| SLOs per journey with multi-window burn-rate alerts, and an error budget policy. | https://sre.google/workbook/implementing-slos/ · https://sre.google/workbook/alerting-on-slos/ | T-35 |
| ECS has native blue/green (2025-07) and canary or linear deployments (2025-10) with alarm rollback. | https://aws.amazon.com/about-aws/whats-new/2025/10/amazon-ecs-built-in-linear-canary-deployments | T-36 |
| AWS FIS game days: Aurora failover, stopping ECS tasks. | https://docs.aws.amazon.com/fis/latest/userguide/fis-actions-reference.html | R-11: a game-day runbook. |
| Aurora Global Database: RPO about 1 s and RTO minutes across regions. Cognito pools are regional, which is the hard part. | https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html | T-26: single region plus cross-region backup copies now; Global Database later. |
| Apple 5.1.1(v): deletion must be possible in the app. Google Play also needs a **web deletion URL**. | https://developer.apple.com/news/?id=12m75xbj · https://support.google.com/googleplay/android-developer/answer/13327111 | Deletion done in the API. R-13: a web deletion page. |
| Old app builds live for months: send a version header, keep a minimum supported version, show a forced-update screen, and make only additive API changes. | https://stripe.com/blog/api-versioning | T-29 / T-04, in the first store build. |
| Push through SNS Mobile Push with FCM HTTP v1 and APNs. Clean up device tokens. | https://docs.aws.amazon.com/sns/latest/dg/sns-fcm-v1-payloads.html · https://capacitorjs.com/docs/apis/push-notifications | T-31 |
| Load testing: smoke, average, stress, spike, soak and breakpoint tests, with an open arrival-rate model. Shopify rehearses at 150% of last peak. | https://grafana.com/docs/k6/latest/testing-guides/api-load-testing/ · https://shopify.engineering/bfcm-readiness-2025 | L-1 to L-4 |
