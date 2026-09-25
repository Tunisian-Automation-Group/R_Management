"""What a renter gets back when a booking is cancelled.

    flexible  full refund until the booked time starts
    moderate  full refund until 24 h before, then half
    strict    full refund until 7 days before, half until 24 h, then nothing

An owner who cancels always refunds in full. Before the owner accepts,
nothing was charged, so there is nothing to keep. After the start there is
no cancelling at all (the renter disputes instead).
"""

from __future__ import annotations

from datetime import datetime, timedelta


def refund_share(policy: str, *, by_owner: bool, now: datetime, window_start: datetime) -> float:
    if by_owner or policy == "flexible":
        return 1.0
    ahead = window_start - now
    if policy == "moderate":
        return 1.0 if ahead >= timedelta(hours=24) else 0.5
    if policy == "strict":
        if ahead >= timedelta(days=7):
            return 1.0
        return 0.5 if ahead >= timedelta(hours=24) else 0.0
    return 1.0


def refund_amount(
    policy: str, amount: int, *, charged: bool, by_owner: bool, now: datetime, window_start: datetime
) -> int:
    if not charged:
        return amount
    return round(amount * refund_share(policy, by_owner=by_owner, now=now, window_start=window_start))


if __name__ == "__main__":
    t0 = datetime(2026, 1, 10, 12)
    day, week = timedelta(days=1), timedelta(days=7)
    assert refund_amount("strict", 1000, charged=True, by_owner=False, now=t0 - week, window_start=t0) == 1000
    assert refund_amount("strict", 1000, charged=True, by_owner=False, now=t0 - 2 * day, window_start=t0) == 500
    assert (
        refund_amount("strict", 1000, charged=True, by_owner=False, now=t0 - timedelta(hours=2), window_start=t0) == 0
    )
    assert refund_amount("strict", 1000, charged=True, by_owner=True, now=t0, window_start=t0) == 1000
    assert refund_amount("moderate", 1000, charged=False, by_owner=False, now=t0, window_start=t0) == 1000
