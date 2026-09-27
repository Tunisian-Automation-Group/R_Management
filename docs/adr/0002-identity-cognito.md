# 0002. Identity from Amazon Cognito; every service verifies the JWT

## Context
The accounts service is hand-rolled: scrypt passwords, opaque session tokens,
no email verification, password reset, MFA, lockout or rate limiting, and an
HTTP round trip from the gateway on every signed request. The gateway then
tells the services who the caller is with a plain `X-Cappy-User` header they
trust unconditionally.

## Decision
Amazon Cognito user pools own sign-up, verification, sign-in, password reset,
MFA and brute-force protection. The app talks to Cognito directly and sends
the access token as a bearer token. Every service verifies it locally (RS256
against the pool's cached JWKS: issuer, audience/client, `token_use`,
expiry). The caller's identity is the token's `sub`; there is no identity
header. A person's owner profile is created on first use with an idempotent
`PUT /me`, so there is no cross-service transaction at sign-up.

The accounts service is removed.

## Rejected
- *Harden the accounts service.* Email verification, reset flows, MFA,
  credential-stuffing defence and breach response are a product in
  themselves; building them is not our business.
- *Auth0 / Clerk.* Excellent, but a second vendor and a data processor outside
  the AWS account, for no capability Cognito lacks here.
- *Keep a trusted header between services.* One misconfigured security group
  and everyone is everyone. Verifying a signature is microseconds.

## Consequences
Local development needs Cognito: LocalStack emulates it (ADR 0009). Tokens
live in the browser (access token in memory, refresh token in storage) —
mitigated by a strict Content-Security-Policy; a cookie-based BFF is the
upgrade if the threat model changes.

## Correction (2026-09-27)

Locally, Cognito is emulated by `cognito-local`, not LocalStack (ADR 0009,
`compose.yaml`). The decision stands.
