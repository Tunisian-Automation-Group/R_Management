from __future__ import annotations

import pytest

from booking.state import check_can_rate, next_status
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
        next_status("start", "accepted", OWN, REQ, OWN)
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
