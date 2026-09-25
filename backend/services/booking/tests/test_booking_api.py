"""The booking API against fake matching and payments services."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from booking.clients import Matching, Payments, PaymentStart
from booking.jobs import sweep_once
from booking.main import build_app
from booking.settings import Settings
from booking.tables import BookingRow
from cappy_common.errors import Conflict, Unavailable
from cappy_common.events import (
    BOOKING_RATED,
    BOOKING_STATUS_CHANGED,
    PAYMENT_AUTHORISED,
    PAYMENT_FAILED,
    Event,
    reset_memory_broker,
)
from cappy_common.fixtures import build_world
from cappy_common.ids import new_id
from cappy_common.models import Match, MatchView, Quote
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import HOUR_MS, iso_from_ms, now_iso, now_ms

INTERNAL = {"X-Internal-Token": "i" * 40}
BUYER, HOST = "buyer-sub", "o1"


class FakeMatching(Matching):
    def __init__(self) -> None:
        w = build_world()
        self.listing = next(l for l in w.listings if l.id == "l9")
        self.owner = next(o for o in w.owners if o.id == self.listing.owner_id)

    async def match_for_offer(self, requirement, listing_id, slot_id, start, end) -> MatchView:  # noqa: ANN001
        q = Quote(hours=2, base=4000, extra=0, extra_label="", total=4600, platform_fee=600, owner_net=4000)
        m = Match(
            listing_id=listing_id,
            owner_id=self.owner.id,
            slot_id=slot_id,
            start=start,
            end=end,
            score=1,
            confidence=1,
            reasons=[],
            quote=q,
            distance_km=1.0,
        )
        return MatchView(match=m, listing=self.listing, owner=self.owner)


class FakePayments(Payments):
    def __init__(self) -> None:
        self.started: list[str] = []
        self.down = False
        self.refuse = False

    async def start(self, *, booking_id, requester_id, owner_id, amount, owner_net, currency) -> PaymentStart:  # noqa: ANN001
        if self.down:
            raise Unavailable("stripe is down")
        if self.refuse:
            raise Conflict("this owner cannot take payments yet")
        assert owner_net < amount
        self.started.append(booking_id)
        return PaymentStart(client_secret=f"pi_{booking_id}_secret", intent_id=f"pi_{booking_id}")


class FakeCatalog:
    kept: list = []

    async def handover(self, listing_id):  # noqa: ANN001
        return {"address": "Tempelhofer Damm 1, 12101 Berlin", "instructions": "Ring the workshop bell"}

    async def keep_evidence(self, owner_id, urls):  # noqa: ANN001
        from cappy_common.errors import Invalid

        if any("not-mine" in u for u in urls):
            raise Invalid("those photos were not uploaded by you")
        self.kept.append((owner_id, urls))

    async def aclose(self) -> None:
        pass


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def broker():
    return reset_memory_broker()


@pytest.fixture()
def payments():
    return FakePayments()


@pytest.fixture()
def app(issuer, broker, payments):
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    return build_app(
        settings, matching=FakeMatching(), payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier()
    )


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        app.state._portal = c.portal
        yield c


def call(app, fn, *args, **kwargs):
    return app.state._portal.call(lambda: fn(*args, **kwargs))


def _body(start_h: float = 24, hours: float = 2):
    start = now_ms() + int(start_h * HOUR_MS)
    return {
        "requirement": {
            "mode": "window",
            "category": "workshop",
            "hours": hours,
            "earliest": now_iso(),
            "latest": iso_from_ms(now_ms() + 7 * 24 * HOUR_MS),
            "district": "Kreuzberg",
            "maxDistanceKm": 25,
        },
        "listingId": "l9",
        "slotId": "w8",
        "start": iso_from_ms(start),
        "end": iso_from_ms(start + int(hours * HOUR_MS)),
    }


def _authorise(app, booking_id: str, type_: str = PAYMENT_AUTHORISED) -> bool:
    ev = Event(id=new_id("ev"), type=type_, source="payments", occurred_at=now_iso(), data={"bookingId": booking_id})
    return call(app, app.state.dispatcher.handle, ev)


def _book(client, issuer, **kw) -> dict:
    r = client.post("/bookings", json=_body(**kw), headers=issuer.headers(BUYER))
    assert r.status_code == 201, r.text
    return r.json()


def _requested(client, app, issuer, **kw) -> str:
    bid = _book(client, issuer, **kw)["booking"]["id"]
    assert _authorise(app, bid)
    return bid


def _do(client, issuer, sub, bid, action, **json):
    return client.post(f"/bookings/{bid}/{action}", headers=issuer.headers(sub), json=json or None)


def test_booking_starts_awaiting_payment_with_a_client_secret(client, issuer, payments):
    out = _book(client, issuer)
    b = out["booking"]
    assert b["status"] == "awaiting_payment" and b["id"].startswith("bk_")
    assert out["payment"]["clientSecret"] == f"pi_{b['id']}_secret"
    assert b["listing"]["title"] and b["listing"]["ownerName"] and b["expiresAt"]
    assert b["match"]["quote"]["total"] == 4600


def test_sign_in_required_and_the_old_header_means_nothing(client):
    assert client.post("/bookings", json=_body()).status_code == 401
    assert client.get("/bookings", headers={"X-Cappy-User": BUYER}).status_code == 401


def test_you_cannot_book_yourself(client, issuer):
    r = client.post("/bookings", json=_body(), headers=issuer.headers(HOST))
    assert r.status_code == 422


def test_the_same_window_cannot_be_held_twice(client, issuer):
    _book(client, issuer)
    r = client.post("/bookings", json=_body(), headers=issuer.headers("someone-else"))
    assert r.status_code == 409


def test_a_retry_with_the_same_key_returns_the_same_booking(client, issuer):
    h = {**issuer.headers(BUYER), "Idempotency-Key": "abc-123"}
    body = _body()
    a = client.post("/bookings", json=body, headers=h).json()
    b = client.post("/bookings", json=body, headers=h).json()
    assert a["booking"]["id"] == b["booking"]["id"]
    assert b["payment"]["clientSecret"] == a["payment"]["clientSecret"]
    assert len(client.get("/bookings", headers=issuer.headers(BUYER)).json()["items"]) == 1


def test_payments_down_keeps_the_booking_for_a_retry(client, issuer, payments):
    """Payments may have made the intent before failing to answer, so nothing
    is failed on a 5xx: the same key retried gets the payment, and an unpaid
    booking lapses by itself."""
    payments.down = True
    h = {**issuer.headers(BUYER), "Idempotency-Key": "k-down"}
    body = _body()
    assert client.post("/bookings", json=body, headers=h).status_code == 503
    [b] = client.get("/bookings", headers=issuer.headers(BUYER)).json()["items"]
    assert b["status"] == "awaiting_payment"
    payments.down = False
    again = client.post("/bookings", json=body, headers=h).json()
    assert again["booking"]["id"] == b["id"] and again["payment"]["clientSecret"]


def test_a_buyer_can_come_back_to_pay(client, issuer):
    bid = _book(client, issuer)["booking"]["id"]
    assert client.get(f"/bookings/{bid}/payment", headers=issuer.headers(BUYER)).json()["clientSecret"]
    assert client.get(f"/bookings/{bid}/payment", headers=issuer.headers(HOST)).status_code == 404


def test_an_owner_who_cannot_be_paid_cannot_be_booked(client, issuer, payments):
    payments.refuse = True
    r = client.post("/bookings", json=_body(), headers=issuer.headers(BUYER))
    assert r.status_code == 409 and "payments" in r.json()["error"]["message"]
    payments.refuse = False
    _book(client, issuer)


def test_the_owner_sees_it_only_once_the_card_is_authorised(client, app, issuer, broker):
    bid = _book(client, issuer)["booking"]["id"]
    assert _authorise(app, bid)
    b = client.get(f"/bookings/{bid}", headers=issuer.headers(HOST)).json()
    assert b["status"] == "requested" and b["requesterId"] == BUYER
    call(app, app.state.relay.flush)
    changes = [(e.data["from"], e.data["to"]) for e in broker.of_type(BOOKING_STATUS_CHANGED)]
    assert changes == [(None, "awaiting_payment"), ("awaiting_payment", "requested")]
    assert broker.of_type(BOOKING_STATUS_CHANGED)[-1].data["amount"] == 4600


def test_a_failed_payment_frees_the_window(client, app, issuer):
    bid = _book(client, issuer)["booking"]["id"]
    assert _authorise(app, bid, PAYMENT_FAILED)
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "payment_failed"
    _book(client, issuer)


def test_a_late_authorisation_does_not_revive_a_cancelled_booking(client, app, issuer):
    bid = _book(client, issuer)["booking"]["id"]
    assert _do(client, issuer, BUYER, bid, "cancel").json()["status"] == "cancelled"
    _authorise(app, bid)
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "cancelled"


def test_full_lifecycle_and_rating(client, app, issuer, broker):
    bid = _requested(client, app, issuer, start_h=0.25)
    assert _do(client, issuer, BUYER, bid, "accept").status_code == 403
    assert _do(client, issuer, HOST, bid, "accept").json()["status"] == "accepted"
    assert _do(client, issuer, HOST, bid, "start").json()["status"] == "active"
    assert _do(client, issuer, HOST, bid, "complete").status_code == 403
    assert _do(client, issuer, BUYER, bid, "complete").json()["status"] == "completed"
    r = _do(client, issuer, BUYER, bid, "rate", onTime=True, quality=5, note="Great", tags=["Ready on time"])
    assert r.status_code == 200 and r.json()["outcome"]["quality"] == 5
    assert _do(client, issuer, BUYER, bid, "rate", onTime=True, quality=5).status_code == 409
    call(app, app.state.relay.flush)
    [rated] = broker.of_type(BOOKING_RATED)
    assert rated.data["ownerId"] == HOST and rated.data["requesterId"] == BUYER


def test_decline_needs_a_reason_and_frees_the_window(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert _do(client, issuer, HOST, bid, "decline", reason="   ").status_code == 422
    r = _do(client, issuer, HOST, bid, "decline", reason="Machine is in for service")
    assert r.json()["status"] == "declined" and r.json()["declineReason"]
    _book(client, issuer)


def test_strangers_cannot_see_or_touch_a_booking(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert client.get(f"/bookings/{bid}", headers=issuer.headers("stranger")).status_code == 404
    assert _do(client, issuer, "stranger", bid, "cancel").status_code == 404


def test_listing_is_paged_and_split_by_role(client, app, issuer):
    for h in (24, 30, 36):
        _book(client, issuer, start_h=h)
    page = client.get("/bookings", params={"limit": 2}, headers=issuer.headers(BUYER)).json()
    assert len(page["items"]) == 2 and page["nextCursor"]
    rest = client.get(
        "/bookings", params={"limit": 2, "cursor": page["nextCursor"]}, headers=issuer.headers(BUYER)
    ).json()
    assert len(rest["items"]) == 1 and "nextCursor" not in rest
    assert client.get("/bookings", params={"role": "owner"}, headers=issuer.headers(BUYER)).json()["items"] == []
    assert len(client.get("/bookings", params={"role": "owner"}, headers=issuer.headers(HOST)).json()["items"]) == 3


def test_busy_is_internal_and_lists_held_windows(client, app, issuer):
    body = {"listingIds": ["l9"], "start": now_iso(), "until": iso_from_ms(now_ms() + 72 * HOUR_MS)}
    assert client.post("/internal/busy", json=body).status_code == 403
    b = _book(client, issuer)["booking"]
    held = client.post("/internal/busy", json=body, headers=INTERNAL).json()
    assert held == {"l9": [[b["match"]["start"], b["match"]["end"]]]}
    _do(client, issuer, BUYER, b["id"], "cancel")
    assert client.post("/internal/busy", json=body, headers=INTERNAL).json() == {}


async def _age(app, bid: str, **fields) -> None:
    async with app.state.db.transaction() as s:
        row = await s.get(BookingRow, bid)
        for k, v in fields.items():
            setattr(row, k, v)


def test_unpaid_and_unanswered_requests_lapse(client, app, issuer):
    unpaid = _book(client, issuer)["booking"]["id"]
    unanswered = _requested(client, app, issuer, start_h=40)
    past = datetime.now(UTC) - timedelta(minutes=1)
    call(app, _age, app, unpaid, expires_at=past)
    # Acting on a lapsed request fails even before the sweep gets to it.
    call(app, _age, app, unanswered, expires_at=past)
    assert _do(client, issuer, HOST, unanswered, "accept").status_code == 409
    assert call(app, sweep_once, app) == 2
    for bid in (unpaid, unanswered):
        assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "expired"
    assert call(app, sweep_once, app) == 0


def test_the_answer_deadline_never_passes_the_window_start(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=2)
    b = client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    assert b["expiresAt"] == b["match"]["start"]


def test_finished_jobs_complete_themselves(client, app, issuer):
    bid = _requested(client, app, issuer)
    _do(client, issuer, HOST, bid, "accept")
    ended = datetime.now(UTC) - timedelta(hours=49)
    call(app, _age, app, bid, window_start=ended - timedelta(hours=2), window_end=ended)
    assert call(app, sweep_once, app) == 1
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "completed"


def test_events_are_idempotent(client, app, issuer):
    bid = _book(client, issuer)["booking"]["id"]
    ev = Event(
        id=new_id("ev"), type=PAYMENT_AUTHORISED, source="payments", occurred_at=now_iso(), data={"bookingId": bid}
    )
    assert call(app, app.state.dispatcher.handle, ev) is True
    assert call(app, app.state.dispatcher.handle, ev) is False


def test_the_hand_over_cannot_be_marked_days_early(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=48)
    _do(client, issuer, HOST, bid, "accept")
    assert _do(client, issuer, HOST, bid, "start").status_code == 409


def test_once_the_time_has_started_the_buyer_disputes_rather_than_cancels(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=40)
    _do(client, issuer, HOST, bid, "accept")
    assert _do(client, issuer, BUYER, bid, "dispute", reason="x").status_code == 409, "nothing to dispute yet"
    started = datetime.now(UTC) - timedelta(minutes=5)
    call(app, _age, app, bid, window_start=started, window_end=started + timedelta(hours=2))
    assert _do(client, issuer, BUYER, bid, "cancel").status_code == 409
    assert _do(client, issuer, HOST, bid, "cancel").status_code == 409
    assert _do(client, issuer, HOST, bid, "dispute", reason="x").status_code == 403
    r = _do(client, issuer, BUYER, bid, "dispute", reason="Nobody was there")
    assert r.json()["status"] == "disputed"
    # A disputed booking never completes, and pays nobody, by itself.
    ended = datetime.now(UTC) - timedelta(hours=72)
    call(app, _age, app, bid, window_start=ended - timedelta(hours=2), window_end=ended)
    assert call(app, sweep_once, app) == 0
    # Support settles it; the owner's payout follows from `completed`.
    body = {"outcome": "pay_owner", "by": "agent-7"}
    assert client.post(f"/internal/bookings/{bid}/resolve", json=body).status_code == 403
    assert client.post(f"/internal/bookings/{bid}/resolve", json=body, headers=INTERNAL).json()["status"] == "completed"
    assert client.post(f"/internal/bookings/{bid}/resolve", json=body, headers=INTERNAL).status_code == 409


def test_a_declined_capture_releases_the_booking(client, app, issuer):
    bid = _requested(client, app, issuer)
    _do(client, issuer, HOST, bid, "accept")
    assert _authorise(app, bid, PAYMENT_FAILED)
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "payment_failed"
    _book(client, issuer)  # the window is free again


def test_what_is_open_and_everything_for_one_person(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert client.get(f"/internal/people/{BUYER}/open").status_code == 403
    assert client.get(f"/internal/people/{BUYER}/open", headers=INTERNAL).json() == {"open": 1}
    assert client.get(f"/internal/people/{HOST}/open", headers=INTERNAL).json() == {"open": 1}
    _do(client, issuer, BUYER, bid, "cancel")
    assert client.get(f"/internal/people/{BUYER}/open", headers=INTERNAL).json() == {"open": 0}
    [b] = client.get(f"/internal/people/{BUYER}/bookings", headers=INTERNAL).json()
    assert b["id"] == bid and b["status"] == "cancelled"


def test_the_handover_address_is_shared_only_once_accepted(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert "handover" not in client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    _do(client, issuer, HOST, bid, "accept")
    for who in (BUYER, HOST):
        h = client.get(f"/bookings/{bid}", headers=issuer.headers(who)).json()["handover"]
        assert h["address"].startswith("Tempelhofer Damm") and h["instructions"]
    assert client.get(f"/bookings/{bid}", headers=issuer.headers("stranger")).status_code == 404


def test_a_key_reused_for_a_different_request_is_refused(client, issuer):
    h = {**issuer.headers(BUYER), "Idempotency-Key": "k-reuse"}
    assert client.post("/bookings", json=_body(start_h=24), headers=h).status_code == 201
    r = client.post("/bookings", json=_body(start_h=30), headers=h)
    assert r.status_code == 422 and "different" in r.json()["error"]["message"]


def test_a_person_cannot_pile_up_unpaid_bookings(client, issuer):
    for h in (24, 30, 36):
        _book(client, issuer, start_h=h)
    r = client.post("/bookings", json=_body(start_h=42), headers=issuer.headers(BUYER))
    assert r.status_code == 429 and r.headers.get("retry-after") is None


def test_the_bookings_kill_switch(issuer, broker, payments):
    settings = Settings(
        app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40, accepting_bookings=False
    )
    app = build_app(
        settings, matching=FakeMatching(), payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier()
    )
    with TestClient(app) as c:
        r = c.post("/bookings", json=_body(), headers=issuer.headers(BUYER))
        assert r.status_code == 503 and r.headers["retry-after"] and "paused" in r.json()["error"]["message"]


def test_a_job_finished_early_keeps_its_window_sold(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=0.25)
    b = client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    for who, action in ((HOST, "accept"), (HOST, "start"), (BUYER, "complete")):
        assert _do(client, issuer, who, bid, action).status_code == 200
    body = {"listingIds": ["l9"], "start": now_iso(), "until": iso_from_ms(now_ms() + 72 * HOUR_MS)}
    held = client.post("/internal/busy", json=body, headers=INTERNAL).json()
    assert held == {"l9": [[b["match"]["start"], b["match"]["end"]]]}
    r = client.post("/bookings", json=_body(start_h=0.25), headers=issuer.headers("someone-else"))
    assert r.status_code == 409


def test_removing_a_listing_declines_its_pending_requests(client, app, issuer):
    from cappy_common.events import LISTING_CHANGED

    pending = _requested(client, app, issuer, start_h=30)
    unpaid = _book(client, issuer, start_h=40)["booking"]["id"]
    accepted = _requested(client, app, issuer, start_h=50)
    _do(client, issuer, HOST, accepted, "accept")
    ev = Event(
        id=new_id("ev"),
        type=LISTING_CHANGED,
        source="catalog",
        occurred_at=now_iso(),
        data={"listingId": "l9", "change": "removed"},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    for bid in (pending, unpaid):
        b = client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
        assert b["status"] == "declined" and "removed" in b["declineReason"]
    assert client.get(f"/bookings/{accepted}", headers=issuer.headers(BUYER)).json()["status"] == "accepted"


def test_an_accepted_booking_says_when_the_hand_over_opens(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=48)
    b = _do(client, issuer, HOST, bid, "accept").json()
    start = datetime.fromisoformat(b["match"]["start"].replace("Z", "+00:00"))
    opens = datetime.fromisoformat(b["canStartFrom"].replace("Z", "+00:00"))
    assert start - opens == timedelta(minutes=30)


def test_contact_details_are_masked_until_the_booking_is_accepted(client, app, issuer, broker):
    from booking.messages import HIDDEN
    from cappy_common.events import BOOKING_MESSAGE

    bid = _requested(client, app, issuer)
    say = lambda who, text: client.post(  # noqa: E731
        f"/bookings/{bid}/messages", json={"body": text}, headers=issuer.headers(who)
    )
    early = say(BUYER, "Call me on +49 151 2345 6789 or mail erin@example.com, see www.mydeals.com").json()
    assert "2345" not in early["body"] and "example.com" not in early["body"] and "mydeals" not in early["body"]
    assert early["body"].count(HIDDEN) == 3 and early["mine"] is True
    assert say(HOST, "Can you come at 3? I have 2 saws.").json()["body"] == "Can you come at 3? I have 2 saws."
    _do(client, issuer, HOST, bid, "accept")
    assert "+49 151" in say(HOST, "Ring +49 151 9999 0000 at the gate").json()["body"], "shared once accepted"
    page = client.get(f"/bookings/{bid}/messages", headers=issuer.headers(HOST)).json()
    assert [m["mine"] for m in page["items"]] == [False, True, True]
    assert client.get(f"/bookings/{bid}/messages", headers=issuer.headers("stranger")).status_code == 404
    call(app, app.state.relay.flush)
    assert [e.data["recipientId"] for e in broker.of_type(BOOKING_MESSAGE)] == [HOST, BUYER, BUYER]


def test_a_block_stops_messages_and_new_bookings(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert client.put(f"/me/blocks/{BUYER}", headers=issuer.headers(HOST)).status_code == 204
    assert client.get("/me/blocks", headers=issuer.headers(HOST)).json() == [BUYER]
    r = client.post(f"/bookings/{bid}/messages", json={"body": "hello?"}, headers=issuer.headers(BUYER))
    assert r.status_code == 403
    assert client.post("/bookings", json=_body(start_h=40), headers=issuer.headers(BUYER)).status_code == 403
    client.delete(f"/me/blocks/{BUYER}", headers=issuer.headers(HOST))
    assert (
        client.post(f"/bookings/{bid}/messages", json={"body": "hello?"}, headers=issuer.headers(BUYER)).status_code
        == 201
    )


def test_a_suspended_person_cannot_book(client, app, issuer):
    from cappy_common.events import OWNER_SUSPENDED

    ev = Event(id=new_id("ev"), type=OWNER_SUSPENDED, source="catalog", occurred_at=now_iso(), data={"ownerId": BUYER})
    assert call(app, app.state.dispatcher.handle, ev)
    assert client.post("/bookings", json=_body(), headers=issuer.headers(BUYER)).status_code == 403


def test_staff_can_resolve_a_dispute_from_the_admin_console(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=40)
    _do(client, issuer, HOST, bid, "accept")
    started = datetime.now(UTC) - timedelta(minutes=5)
    call(app, _age, app, bid, window_start=started, window_end=started + timedelta(hours=2))
    _do(client, issuer, BUYER, bid, "dispute", reason="Nobody came")
    body = {"outcome": "refund_buyer", "by": "ignored"}
    assert client.post(f"/admin/bookings/{bid}/resolve", json=body, headers=issuer.headers(BUYER)).status_code == 403
    staff = {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}
    assert client.post(f"/admin/bookings/{bid}/resolve", json=body, headers=staff).json()["status"] == "cancelled"


def test_check_in_and_check_out_photos_are_kept_as_evidence(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=0.25)
    photo = "/media/" + "a" * 40 + ".webp"
    add = lambda who, stage, photos: client.post(  # noqa: E731
        f"/bookings/{bid}/evidence", json={"stage": stage, "photos": photos}, headers=issuer.headers(who)
    )
    assert add(HOST, "check_in", [photo]).status_code == 422, "nothing to check in before it is accepted"
    _do(client, issuer, HOST, bid, "accept")
    assert add(HOST, "check_in", [photo]).status_code == 201
    assert add(BUYER, "check_out", [photo]).status_code == 422, "check-out after the hand-over"
    _do(client, issuer, HOST, bid, "start")
    assert add(BUYER, "check_out", ["/media/not-mine.webp"]).status_code == 422
    assert add(BUYER, "check_out", [photo]).status_code == 201
    got = client.get(f"/bookings/{bid}/evidence", headers=issuer.headers(HOST)).json()
    assert [(e["by"], e["stage"]) for e in got] == [(HOST, "check_in"), (BUYER, "check_out")]
    assert client.get(f"/bookings/{bid}/evidence", headers=issuer.headers("stranger")).status_code == 404
