# 0004. Double booking is prevented by a Postgres exclusion constraint

## Context
Nothing stops two buyers booking the same listing for overlapping hours. Any
check done in application code ("is it free?" then "insert") races across
requests and replicas.

## Decision
Bookings store their window as real `timestamptz` columns. A Postgres
exclusion constraint forbids two *holding* bookings (`requested`, `accepted`,
`active`) on the same listing whose windows overlap:

    EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end) WITH &&)
      WHERE (status IN ('requested','accepted','active'))

A violation becomes `409 conflict: that window was just taken`. Declined,
cancelled and expired bookings release the window by leaving the predicate.
Offers subtract the busy intervals (ADR 0001), so a buyer normally never sees
a taken window; the constraint is what makes it impossible rather than
unlikely. SQLite (unit tests) gets the same rule as an explicit overlap check.

Unanswered requests expire (default 24 h), releasing the window and the card
authorisation.

## Rejected
- *Advisory locks / SELECT … FOR UPDATE on the listing.* Correct only if every
  code path remembers to take them.
- *Carving the idle slot into pieces on accept.* Mutates supply to represent
  demand, and still races.

## Correction (2026-09-27)

The statuses that hold a window are wider than listed above: `awaiting_payment`,
`requested`, `accepted`, `active`, `completed` and `disputed` (booking migration
0003, `booking/state.py` `HOLDING`). A completed or disputed booking used its
time, so it stays sold. The decision stands.
