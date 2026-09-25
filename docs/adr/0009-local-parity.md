# 0009. Local parity: LocalStack, cognito-local and stripe-mock

## Context
We want the system to run locally against the same AWS APIs it uses in
production, with no cloud account. The LocalStack token available to the team
is a tier that covers S3, SNS, SQS, SES (v1), Secrets Manager, KMS, IAM, EC2
networking, CloudWatch and Logs, but not Cognito, ECS, RDS, ELB, CloudFront,
WAF, ECR or Cloud Map (probed 2026-09-25 against LocalStack Pro 2026.8.4).

## Decision
`make up` starts:

| Production | Local |
|---|---|
| Aurora PostgreSQL | `postgres:16` |
| SNS, SQS, S3, SES, Secrets Manager | LocalStack (auth token from the untracked `.env`) |
| Cognito user pool | `jagregory/cognito-local` — same API, RS256 access tokens with the same claims (`token_use`, `client_id`, `sub`, `iss`) and a JWKS endpoint |
| Stripe | Stripe test mode when keys are set, otherwise the `fake` provider; `stripe/stripe-mock` for API contract tests |
| ECS services | the same images under compose |
| CloudFront + ALB | the gateway on :8000 (the Vite dev server proxies `/api`) |

A bootstrap step creates the user pool, app client, topic, queues and bucket
with the names Terraform uses. `make seed-demo` loads the demo world and demo
users on demand. Unit tests need none of it: SQLite, an in-memory bus, and a
throwaway JWKS.

Terraform for services LocalStack does not emulate is checked with
`terraform validate` and plan-only runs; the messaging and storage modules can
be applied to LocalStack.

## Consequences
The expected token issuer and the JWKS URL are separate settings, because
cognito-local names itself differently from the address services reach it on.
Confirmation codes for sign-up appear in `docker compose logs cognito` (and
`make codes`), standing in for the email Cognito sends.
