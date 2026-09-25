# 0006. Notifications by email through Amazon SES

## Context
An owner only learns about a request if the app is open and polling.

## Decision
A `notifications` service consumes booking and payment events from its SQS
queue and sends transactional email through Amazon SES (a new request, an
accepted or declined request, a completed booking to rate). Recipient
addresses come from Cognito. Idempotent on event id. Locally, LocalStack
captures the mail.

## Rejected
- *Push notifications first.* Needs a native shell or Web Push subscription
  management; email reaches everyone today. Push is a second channel in the
  same service.
- *Sending from the booking service.* Couples a user-facing request path to a
  third party's latency and failure modes.
