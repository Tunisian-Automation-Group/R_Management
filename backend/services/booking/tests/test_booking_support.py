"""Disputes the two sides settle (S-21), staff resolutions with four eyes
(H-6), the case view and its audit trail (H-7, H-9), late returns and
extensions (S-12)."""

# ruff: noqa: F811 - pytest fixtures are imported from test_booking_api and used as arguments
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from booking.jobs import sweep_once
from booking.tables import BookingRow, DisputeRow
from cappy_common.events import BOOKING_STATUS_CHANGED, DISPUTE_OFFER, STAFF_ACTION

from .test_booking_api import (  # noqa: F401 - fixtures
    BUYER,
    HOST,
    INTERNAL,
    _age,
    _body,
    _do,
    _events,
    _requested,
    app,
    broker,
    call,
    client,
    issuer,
    payments,
)


def _staff(issuer, sub: str = "staff-1", *groups: str) -> dict:
    return {"Authorization": f"Bearer {issuer.token(sub, **{'cognito:groups': ['admin', *groups]})}"}


def _disputed(client, app, issuer, amount: int | None = None) -> str:
    bid = _requested(client, app, issuer, start_h=40)
    _do(client, issuer, HOST, bid, "accept")
    started = datetime.now(UTC) - timedelta(minutes=5)
    fields = {"window_start": started, "window_end": started + timedelta(hours=2)}
    call(app, _age, app, bid, **fields, **({"amount": amount} if amount else {}))
    assert _do(client, issuer, BUYER, bid, "dispute", reason="The fence was broken").json()["status"] == "disputed"
    return bid


async def _set_dispute(app, bid: str, **fields) -> None:
    async with app.state.db.transaction() as s:
        d = await s.get(DisputeRow, bid)
        for k, v in fields.items():
            setattr(d, k, v)


def test_the_two_sides_settle_a_dispute_with_an_offer(client, app, issuer, broker):
    bid = _disputed(client, app, issuer)
    d = client.get(f"/bookings/{bid}/dispute", headers=issuer.headers(HOST)).json()
    assert d["openedBy"] == BUYER and d["reason"] == "The fence was broken" and "offer" not in d
    assert client.get(f"/bookings/{bid}/dispute", headers=issuer.headers("stranger")).status_code == 404

    offer = lambda who, amount: client.post(  # noqa: E731
        f"/bookings/{bid}/dispute/offer", json={"refundAmount": amount}, headers=issuer.headers(who)
    )
    assert offer(BUYER, 99_999).status_code == 422, "never more than the price"
    made = offer(BUYER, 2000).json()
    assert made["offer"]["refundAmount"] == 2000 and made["offer"]["by"] == BUYER and made["respondBy"] > d["openedAt"]
    assert _events(app, broker, DISPUTE_OFFER)[-1]["to"] == HOST

    accept = lambda who, amount: client.post(  # noqa: E731
        f"/bookings/{bid}/dispute/accept", json={"refundAmount": amount}, headers=issuer.headers(who)
    )
    assert accept(BUYER, 2000).json()["error"]["code"] == "own_offer"
    assert accept(HOST, 1500).json()["error"]["code"] == "offer_changed"
    settled = accept(HOST, 2000).json()
    assert settled["resolution"]["outcome"] == "partial" and settled["resolution"]["reasonCode"] == "agreement"
    b = settled["booking"]
    assert b["status"] == "completed" and b["refundAmount"] == 2000, "partial: completed, part refunded"
    assert _events(app, broker, BOOKING_STATUS_CHANGED)[-1]["refundAmount"] == 2000
    assert accept(HOST, 2000).status_code == 409, "settled once"


def test_a_dispute_nobody_settles_in_72_hours_goes_to_staff(client, app, issuer):
    bid = _disputed(client, app, issuer)
    staff = _staff(issuer)
    assert call(app, sweep_once, app) == 0
    call(app, _set_dispute, app, bid, respond_by=datetime.now(UTC) - timedelta(minutes=1))
    assert call(app, sweep_once, app) == 1
    page = client.get("/admin/bookings", params={"status": "disputed"}, headers=staff).json()
    [item] = page["items"]
    assert item["id"] == bid and item["dispute"]["escalatedAt"] and item["requesterId"] == BUYER
    assert client.get("/admin/bookings", headers=issuer.headers(BUYER)).status_code == 403


def test_a_refund_above_the_staff_limit_needs_a_second_pair_of_eyes(client, app, issuer, broker):
    # DE: support may refund €250 alone, a lead €2,500 (markets.json).
    bid = _disputed(client, app, issuer, amount=40_000)
    support, other, lead = _staff(issuer, "staff-1"), _staff(issuer, "staff-2"), _staff(issuer, "lead-1", "admin-lead")
    body = {"outcome": "partial", "refundAmount": 30_000, "reasonCode": "damage", "note": "Cracked guard, photos"}
    h = {**support, "Idempotency-Key": "resolve-1"}
    first = client.post(f"/admin/bookings/{bid}/resolve", json=body, headers=h).json()
    assert first["resolution"]["status"] == "pending_approval" and first["booking"]["status"] == "disputed"
    assert client.post(f"/admin/bookings/{bid}/resolve", json=body, headers=h).json() == first, "a retry replays"
    again = client.post(f"/admin/bookings/{bid}/resolve", json={**body, "refundAmount": 100}, headers=support)
    assert again.json()["error"]["code"] == "approval_pending"

    [pending] = client.get("/admin/resolutions", headers=other).json()
    rid = pending["id"]
    approve = lambda h: client.post(f"/admin/resolutions/{rid}/approve", json={"note": "ok"}, headers=h)  # noqa: E731
    assert approve(support).json()["error"]["code"] == "four_eyes"
    assert approve(other).json()["error"]["code"] == "needs_lead"
    done = approve(lead).json()
    assert done["resolution"]["status"] == "done" and done["resolution"]["approvedBy"] == "lead-1"
    assert done["booking"]["status"] == "completed" and done["booking"]["refundAmount"] == 30_000
    assert approve(lead).status_code == 409
    actions = [(e["actorId"], e["action"]) for e in _events(app, broker, STAFF_ACTION)]
    assert ("staff-1", "propose_resolution") in actions and ("lead-1", "approve_resolution") in actions


def test_within_the_limit_staff_settle_alone_and_partials_are_checked(client, app, issuer):
    bid = _disputed(client, app, issuer)  # €46
    staff = _staff(issuer)
    bad = {"outcome": "partial", "refundAmount": 4600, "reasonCode": "damage"}
    assert (
        client.post(f"/admin/bookings/{bid}/resolve", json=bad, headers=staff).json()["error"]["code"]
        == "invalid_refund"
    )
    assert (
        client.post(f"/admin/bookings/{bid}/resolve", json={**bad, "reasonCode": "vibes"}, headers=staff).status_code
        == 422
    )
    ok = client.post(f"/admin/bookings/{bid}/resolve", json={**bad, "refundAmount": 1000}, headers=staff).json()
    assert ok["resolution"]["status"] == "done" and ok["booking"]["refundAmount"] == 1000


def test_the_case_view_shows_everything_and_is_logged(client, app, issuer, broker):
    bid = _disputed(client, app, issuer)
    client.post(f"/bookings/{bid}/messages", json={"body": "call me on 0151 2345 6789"}, headers=issuer.headers(BUYER))
    staff = _staff(issuer)
    assert client.get(f"/admin/bookings/{bid}/case", headers=issuer.headers(HOST)).status_code == 403
    case = client.get(f"/admin/bookings/{bid}/case", headers=staff).json()
    assert case["requesterId"] == BUYER and case["ownerId"] == HOST
    assert [t["toStatus"] for t in case["timeline"]][-1] == "disputed"
    assert case["dispute"]["reason"] == "The fence was broken"
    assert case["payment"]["status"] == "captured"
    assert "0151 2345 6789" in case["messages"][0]["body"], "staff read what was written"
    assert [e["action"] for e in _events(app, broker, STAFF_ACTION)] == ["read_case"]
    # Staff reading the hand-over photos is logged too.
    assert client.get(f"/bookings/{bid}/evidence", headers=staff).status_code == 200
    assert _events(app, broker, STAFF_ACTION)[-1]["action"] == "read_evidence"
    assert client.get(f"/bookings/{bid}/evidence", headers=issuer.headers(BUYER)).status_code == 200
    assert _events(app, broker, STAFF_ACTION)[-1]["action"] == "read_evidence", "a party's own read is not staff"


def test_staff_find_a_case_by_booking_member_or_email(client, app, issuer):
    bid = _disputed(client, app, issuer)
    staff = _staff(issuer)

    class People:
        async def sub_of(self, email):  # noqa: ANN001
            return BUYER if email == "buyer@example.com" else None

    app.state.people = People()
    find = lambda **q: [c["id"] for c in client.get("/admin/bookings", params=q, headers=staff).json()["items"]]  # noqa: E731
    assert find(booking=bid) == [bid]
    assert find(member=HOST) == [bid] and find(member="buyer@example.com") == [bid]
    assert find(member="nobody@example.com") == []


def test_the_owner_claims_a_late_return_and_staff_decide(client, app, issuer, broker):
    bid = _requested(client, app, issuer, start_h=40)
    _do(client, issuer, HOST, bid, "accept")
    ended = datetime.now(UTC) - timedelta(hours=1)
    call(app, _age, app, bid, window_start=ended - timedelta(hours=2), window_end=ended, status="completed")
    claim = lambda who, minutes: client.post(  # noqa: E731
        f"/bookings/{bid}/late-return",
        json={"minutesLate": minutes, "note": "Back at 19:35"},
        headers=issuer.headers(who),
    )
    assert claim(BUYER, 95).status_code == 403
    assert claim(HOST, 20).json()["error"]["code"] == "within_grace"
    # €20/h: 65 billable minutes round up to 75 (€25), plus one hour as the fee (€20).
    c = claim(HOST, 95).json()
    assert c["amount"] == 4500 and c["status"] == "open" and c["currency"] == "EUR"
    assert claim(HOST, 95).json()["error"]["code"] == "claim_exists"
    assert [x["id"] for x in client.get(f"/bookings/{bid}/claims", headers=issuer.headers(BUYER)).json()] == [c["id"]]

    staff = _staff(issuer)
    assert [
        x["id"] for x in client.get("/admin/bookings", params={"claims": "open"}, headers=staff).json()["items"]
    ] == [bid]
    decided = client.post(
        f"/admin/claims/{c['id']}/decide", json={"decision": "confirm", "note": "Photos match"}, headers=staff
    )
    assert decided.json()["status"] == "confirmed" and decided.json()["decidedBy"] == "staff-1"
    assert client.post(f"/admin/claims/{c['id']}/decide", json={"decision": "reject"}, headers=staff).status_code == 409
    assert _events(app, broker, STAFF_ACTION)[-1]["action"] == "confirm_claim"

    other = _requested(client, app, issuer, start_h=60)
    _do(client, issuer, HOST, other, "accept")
    gone = datetime.now(UTC) - timedelta(hours=25)
    call(app, _age, app, other, window_start=gone - timedelta(hours=2), window_end=gone, status="completed")
    r = client.post(f"/bookings/{other}/late-return", json={"minutesLate": 90}, headers=issuer.headers(HOST))
    assert r.json()["error"]["code"] == "claim_window", "within 24 hours of the end"


def test_the_renter_extends_a_booking_that_is_on(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=24)
    assert client.post(f"/bookings/{bid}/extend", json={"hours": 1}, headers=issuer.headers(BUYER)).status_code == 409
    _do(client, issuer, HOST, bid, "accept")
    assert client.post(f"/bookings/{bid}/extend", json={"hours": 1}, headers=issuer.headers(HOST)).status_code == 403
    r = client.post(
        f"/bookings/{bid}/extend", json={"hours": 1}, headers={**issuer.headers(BUYER), "Idempotency-Key": "ext-1"}
    )
    assert r.status_code == 201, r.text
    new = r.json()["booking"]
    assert new["id"] != bid and new["status"] == "awaiting_payment"
    old = client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    assert new["match"]["start"] == old["match"]["end"], "the time straight after it"
    assert app.state.matching.extension is True, "no lead time for an extension"

    async def extends_id():
        async with app.state.db.session() as s:
            return (await s.get(BookingRow, new["id"])).extends_id

    assert call(app, extends_id) == bid
    again = client.post(
        f"/bookings/{bid}/extend", json={"hours": 1}, headers={**issuer.headers(BUYER), "Idempotency-Key": "ext-1"}
    )
    assert again.json()["booking"]["id"] == new["id"], "a retry is the same extension"


def test_what_people_are_told_reads_in_the_listings_time_zone(client, app, issuer, broker):
    bid = _requested(client, app, issuer)
    assert _events(app, broker, BOOKING_STATUS_CHANGED)[-1]["timeZone"] == "Europe/Berlin", "a German owner"
    fake = app.state.matching
    fake.owner = fake.owner.model_copy(update={"country": "CH"})
    fake.listing = fake.listing.model_copy(update={"currency": "CHF"})
    other = client.post("/bookings", json=_body(start_h=60), headers=issuer.headers(BUYER)).json()["booking"]
    assert other["listing"]["timeZone"] == "Europe/Zurich" and other["currency"] == "CHF"
    assert _events(app, broker, BOOKING_STATUS_CHANGED)[-1]["timeZone"] == "Europe/Zurich"
    assert bid != other["id"]
