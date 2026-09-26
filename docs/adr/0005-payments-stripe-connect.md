# 0005. Payments through Stripe Connect

## Context
No money moves. A marketplace has to charge buyers, hold funds while the
owner decides, pay owners out, take the platform fee, refund, and be compliant
(PSD2/SCA, KYC for payees) across the EU.

## Decision
Stripe Connect with Express connected accounts for owners.

1. **Owner onboarding.** `POST /payments/connect/onboarding` returns a Stripe
   account link; an owner cannot receive bookings until payouts are enabled.
2. **Request = authorise.** Creating a booking creates a PaymentIntent with
   `capture_method=manual` for the quoted total. The app confirms it with the
   Payment Element (SCA handled by Stripe). The booking only reaches the
   owner's inbox once the authorisation succeeds (webhook).
3. **Accept = capture.** Decline, cancel or expiry = cancel the intent (the
   hold is released, nothing is charged).
4. **Complete = transfer.** Separate charges and transfers: the owner's net
   (quote minus the 15% platform fee) is transferred to their connected
   account when the booking completes. Funds are held by the platform until
   the job is done.
5. **Webhooks are the source of truth**, signature-verified, idempotent on the
   Stripe event id.

A `fake` provider with the same interface is used in unit tests and, when no
Stripe keys are configured, in local development; stripe-mock covers API
contract tests.

## Rejected
- *Destination charges.* Pays the owner on capture, before the work is done.
- *Adyen for Platforms.* Comparable, heavier onboarding for a team this size.

## Consequences
Card authorisations expire after seven days: requests expire well before that
(ADR 0004). Bookings starting further out than the authorisation window are
the next piece of work (save the payment method, charge on accept).
