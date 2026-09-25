# 0011. Booking time rules, disputes and failed captures

## Context
A review of the booking and money flows (2026-09-25) found that:
- either side could cancel an accepted booking at any time, for a full
  refund, even after the machine had been used;
- an owner could mark the hand-over days early, which blocked the buyer's
  cancel, and then be paid by the auto-completion sweep for a job never done;
- a declined capture left the booking accepted, so it later "completed"
  with nobody paid;
- the soonest window left the owner minutes, or nothing, to answer.

## Decision
- **Lead time.** Nothing can be booked to start sooner than 2 hours
  (matching `MIN_LEAD_MINUTES`), so the owner always has time to answer.
- **Hand-over.** `start` is allowed from 30 minutes before the window, by
  either side.
- **Cancel** is allowed only before the window starts, and refunds in full.
  After that the buyer **disputes** instead (`disputed`, requester only, from
  accepted or active). A disputed booking holds the captured money, never
  auto-completes, and is settled by support through
  `POST /internal/bookings/{id}/resolve` (pay the owner, or refund the buyer).
- **Failed capture.** A capture Stripe declines for good publishes
  `payment.failed`. Booking moves the booking from `accepted` to
  `payment_failed`, which releases the window; nothing was charged.
- **Payment start errors.** Only a definite refusal (4xx) from payments fails
  a new booking. On a 5xx or timeout the booking stays `awaiting_payment`:
  a retry with the same key gets the same intent, and the expiry sweep
  releases the window if nobody pays.

## Consequences
Buyers can't walk away from a booking after using it, and owners aren't
paid for work they didn't do. Disputes need a person. A support tool on top of
the resolve endpoint is the next step once disputes come in at any volume.
