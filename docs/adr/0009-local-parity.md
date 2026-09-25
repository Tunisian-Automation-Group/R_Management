# 0009. Local parity: LocalStack and stripe-mock

## Decision
`make up` starts Postgres, LocalStack (Cognito, S3, SNS, SQS, SES, Secrets
Manager), stripe-mock, every service and the gateway; a bootstrap step creates
the user pool, topic, queues and bucket exactly as Terraform names them.
`make seed-demo` loads the demo world and demo users on demand. Unit tests
need none of it (SQLite, in-memory bus, a local JWKS).

LocalStack Cognito needs a Pro auth token, read from `LOCALSTACK_AUTH_TOKEN`
in the untracked `.env`.
