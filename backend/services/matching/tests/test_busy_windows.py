"""Offers never overlap a booking, and sold hours come out of a window."""

from __future__ import annotations

from cappy_common.models import Slot
from cappy_common.timeutil import HOUR_MS, iso_from_ms, ms_from_iso
from matching.domain.availability import offers_for

T0 = ms_from_iso("2026-10-01T08:00:00.000Z")


def _slot(start_h: float, end_h: float, usable: float) -> Slot:
    return Slot(
        id="s1",
        listing_id="l1",
        start=iso_from_ms(T0 + int(start_h * HOUR_MS)),
        end=iso_from_ms(T0 + int(end_h * HOUR_MS)),
        hours_usable=usable,
    )


def _h(h: float) -> int:
    return T0 + int(h * HOUR_MS)


def test_no_offer_overlaps_a_booking():
    slot = _slot(0, 10, 10)
    booked = [(_h(2), _h(4))]
    offers = offers_for([slot], 2, iso_from_ms(T0), iso_from_ms(_h(10)), limit=100, busy=booked)
    assert offers
    for o in offers:
        s, e = ms_from_iso(o.start), ms_from_iso(o.end)
        assert e <= booked[0][0] or s >= booked[0][1], (o.start, o.end)
    # The first offer after the booking starts exactly when it ends.
    assert any(ms_from_iso(o.start) == _h(4) for o in offers)


def test_sold_hours_come_out_of_the_window():
    # A 72-hour factory gap with 30 usable machine-hours, 20 of them sold.
    slot = _slot(0, 72, 30)
    booked = [(_h(0), _h(20))]
    until = iso_from_ms(_h(72))
    assert offers_for([slot], 10, iso_from_ms(T0), until, busy=booked)
    assert offers_for([slot], 11, iso_from_ms(T0), until, busy=booked) == []


def test_nothing_booked_changes_nothing():
    slot = _slot(0, 10, 10)
    a = offers_for([slot], 2, iso_from_ms(T0), iso_from_ms(_h(10)), limit=100)
    b = offers_for([slot], 2, iso_from_ms(T0), iso_from_ms(_h(10)), limit=100, busy=[])
    assert a == b and len(a) > 5
