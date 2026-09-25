# Architecture decision records

One decision per file: the context, what we chose, what we rejected and why,
and what it costs. Status is `accepted` unless a later ADR supersedes it.

| ADR | Decision |
|-----|----------|
| [0001](0001-service-boundaries-and-search.md) | Keep the service split; search is an indexed candidate query, never the whole world |
| [0002](0002-identity-cognito.md) | Identity from Amazon Cognito; every service verifies the JWT |
| [0003](0003-events-outbox-sns-sqs.md) | Transactional outbox → SNS → one SQS queue per consumer, with DLQs |
| [0004](0004-no-double-booking.md) | Double booking is prevented by a Postgres exclusion constraint |
| [0005](0005-payments-stripe-connect.md) | Stripe Connect: authorise, capture on accept, transfer on completion |
| [0006](0006-notifications-ses.md) | Notifications by email through Amazon SES |
| [0007](0007-media-s3.md) | Photos re-encoded and stored in S3, served through CloudFront |
| [0008](0008-aws-runtime.md) | CloudFront + WAF → ALB → ECS Fargate, Aurora Serverless v2, Terraform |
| [0009](0009-local-parity.md) | Local parity: LocalStack + stripe-mock, one `make up` |
| [0010](0010-no-demo-in-prod.md) | Demo data is a dev-only seeding tool, never a runtime behaviour |
