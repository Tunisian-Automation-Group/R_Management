from __future__ import annotations

import pytest

from booking.state import HOLDING, check_can_rate, next_status, system_status
from cappy_common.errors import Conflict, Forbidden

REQ, OWN = "buyer", "host"


def test_happy_path():
    s = "requested"
    s = next_status("accept", s, OWN, REQ, OWN)
    assert s == "accepted"
    s = next_status("start", s, REQ, REQ, OWN)
    assert s == "active"
    s = next_status("complete", s, REQ, REQ, OWN)
    assert s == "completed"
    check_can_rate(s, False, REQ, REQ)


def test_decline_and_cancel():
    assert next_status("decline", "requested", OWN, REQ, OWN) == "declined"
    assert next_status("cancel", "requested", REQ, REQ, OWN) == "cancelled"
    assert next_status("cancel", "accepted", OWN, REQ, OWN) == "cancelled"


def test_wrong_role():
    with pytest.raises(Forbidden):
        next_status("accept", "requested", REQ, REQ, OWN)
    with pytest.raises(Forbidden):
        next_status("complete", "active", OWN, REQ, OWN)
    with pytest.raises(Forbidden):
        next_status("accept", "requested", "stranger", REQ, OWN)
    with pytest.raises(Forbidden):
        check_can_rate("completed", False, OWN, REQ)


def test_wrong_state():
    with pytest.raises(Conflict):
        next_status("accept", "accepted", OWN, REQ, OWN)
    with pytest.raises(Conflict):
        next_status("start", "requested", REQ, REQ, OWN)
    with pytest.raises(Conflict):
        next_status("cancel", "completed", REQ, REQ, OWN)
    with pytest.raises(Conflict):
        check_can_rate("active", False, REQ, REQ)
    with pytest.raises(Conflict):
        check_can_rate("completed", True, REQ, REQ)


def test_either_side_can_mark_the_handover():
    assert next_status("start", "accepted", OWN, REQ, OWN) == "active"
    assert next_status("start", "accepted", REQ, REQ, OWN) == "active"


def test_payment_and_sweeps():
    assert system_status("authorised", "awaiting_payment") == "requested"
    assert system_status("payment_failed", "awaiting_payment") == "payment_failed"
    # A payment result for a booking that already moved on changes nothing.
    assert system_status("authorised", "cancelled") is None
    assert system_status("expire", "requested") == "expired"
    assert system_status("expire", "accepted") is None
    assert system_status("auto_complete", "active") == "completed"


def test_only_bookings_that_never_happened_release_their_window():
    # Used time stays sold (a job finished early); unused time is freed.
    assert {"completed", "disputed"} <= HOLDING
    assert HOLDING.isdisjoint({"declined", "cancelled", "expired", "payment_failed"})


def test_masking_keeps_dates_and_catches_contact_details():
    from booking.messages import mask

    kept = [
        "from 12.10.2026 to 14.10.2026",
        "2026-10-12 to 2026-10-14",
        "weights 100 200 300 kg",
        "order #1234567",
        "the signal light on the machine is broken, it blinks red",
        "2 saws at 14:00 for 3 hours",
        "1.250,00 EUR",
        "Hauptstr. 12, 10115 Berlin",
        "z.B. morgen",
    ]
    hidden = [
        "Call me on +49 151 2345 6789",
        "ring 0151 23456789",
        "mail erin@example.com",
        "bob at gmail dot com",
        "bob(at)gmail.com",
        "see www.mydeals.com",
        "shop at example.berlin",
        "whatsapp me +49 151 234 5678",
        "insta @erin.makes",
        "IBAN DE89 3704 0044 0532 0130 00",
        "send it to DE89370400440532013000",
        "details on https://pay.example/erin",
    ]
    assert [t for t in kept if mask(t) != t] == []
    assert [t for t in hidden if mask(t) == t] == []


def test_asking_to_pay_around_cappy_is_flagged_not_blocked():
    from booking.messages import flagged

    asks = [
        "can you pay me directly?",
        "I prefer PayPal",
        "bank transfer is cheaper for both of us",
        "Lieber per Überweisung",
        "wir machen das außerhalb von Cappy",
        "let's pay outside the app",
    ]
    fine = ["I paid through the app", "the transfer of the van is at 10:00", "direct sunlight in the workshop"]
    assert [t for t in asks if not flagged(t)] == []
    assert [t for t in fine if flagged(t)] == []
