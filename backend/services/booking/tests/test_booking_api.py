"""The booking API against fake matching and payments services."""

from __future__ import annotations

import time
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
    instant = False

    def __init__(self) -> None:
        w = build_world()
        self.listing = next(l for l in w.listings if l.id == "l9")
        self.owner = next(o for o in w.owners if o.id == self.listing.owner_id)

    async def match_for_offer(self, requirement, listing_id, slot_id, start, end, *, extension=False) -> MatchView:  # noqa: ANN001
        self.extension = extension
        q = Quote(hours=2, base=4000, extra=0, extra_label="", total=4600, platform_fee=600, owner_net=4000)
        m = Match(
            listing_id=listing_id,
            owner_id=self.owner.id,
            slot_id=slot_id or "w8",
            start=start,
            end=end,
            score=1,
            confidence=1,
            reasons=[],
            quote=q,
            distance_km=1.0,
        )
        return MatchView(
            match=m, listing=self.listing.model_copy(update={"instant_book": self.instant}), owner=self.owner
        )


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
        self.currencies = [*getattr(self, "currencies", []), currency]
        return PaymentStart(client_secret=f"pi_{booking_id}_secret", intent_id=f"pi_{booking_id}")

    async def state(self, booking_id):  # noqa: ANN001
        return {"bookingId": booking_id, "status": "captured"} if booking_id in self.started else None


class FakeCatalog:
    kept: list = []

    async def handover(self, listing_id):  # noqa: ANN001
        return {"address": "Tempelhofer Damm 1, 12101 Berlin", "instructions": "Ring the workshop bell"}

    async def keep_evidence(self, owner_id, urls):  # noqa: ANN001
        from cappy_common.errors import Invalid

        if any("not-mine" in u for u in urls):
            raise Invalid("those photos were not uploaded by you")
        self.kept.append((owner_id, urls))

    async def evidence_photo(self, name):  # noqa: ANN001
        return b"RIFF" + name.encode()

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
    assert broker.of_type(BOOKING_RATED) == [], "blind: nothing is published until both have reviewed"
    client.post(f"/bookings/{bid}/rate-renter", json={"quality": 5}, headers=issuer.headers(HOST))
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
    ids = [_book(client, issuer, start_h=h)["booking"]["id"] for h in (24, 30, 36)]
    owner = client.get("/bookings", params={"role": "owner"}, headers=issuer.headers(HOST)).json()["items"]
    assert owner == [], "not before the card is held (FL-15)"
    for bid in ids:
        assert _authorise(app, bid)
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


async def _age_transition(app, bid: str, to_status: str, at: datetime) -> None:
    """Move the moment a booking entered a status into the past."""
    from sqlalchemy import update

    from booking.tables import TransitionRow

    async with app.state.db.transaction() as s:
        await s.execute(
            update(TransitionRow)
            .where(TransitionRow.booking_id == bid, TransitionRow.to_status == to_status)
            .values(at=at)
        )


async def _expire(app, bid: str) -> None:
    await _age(app, bid, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    return await sweep_once(app)


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
    settled = client.post(f"/internal/bookings/{bid}/resolve", json=body, headers=INTERNAL).json()
    assert settled["booking"]["status"] == "completed" and settled["resolution"]["status"] == "done"
    assert client.post(f"/internal/bookings/{bid}/resolve", json=body, headers=INTERNAL).status_code == 409


def test_after_an_early_hand_over_the_renter_can_report_at_once(client, app, issuer):
    # V4-3: handed over 20 minutes before the booked time, damage found.
    bid = _requested(client, app, issuer, start_h=40)
    _do(client, issuer, HOST, bid, "accept")
    soon = datetime.now(UTC) + timedelta(minutes=20)
    call(app, _age, app, bid, window_start=soon, window_end=soon + timedelta(hours=2))
    assert _do(client, issuer, HOST, bid, "start").json()["status"] == "active"
    assert _do(client, issuer, BUYER, bid, "cancel").status_code == 409, "no refund while the renter holds it"
    r = _do(client, issuer, BUYER, bid, "dispute", reason="The blade guard is cracked")
    assert r.json()["status"] == "disputed"


def test_a_declined_capture_releases_the_booking(client, app, issuer):
    bid = _requested(client, app, issuer)
    _do(client, issuer, HOST, bid, "accept")
    assert _authorise(app, bid, PAYMENT_FAILED)
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["status"] == "payment_failed"
    _book(client, issuer)  # the window is free again


def test_what_is_open_and_everything_for_one_person(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert client.get(f"/internal/people/{BUYER}/open").status_code == 403
    opened = client.get(f"/internal/people/{BUYER}/open", headers=INTERNAL).json()
    booked = client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    assert opened == {"open": 1, "until": booked["match"]["end"]}, "until the booked window ends"
    assert client.get(f"/internal/people/{HOST}/open", headers=INTERNAL).json()["open"] == 1
    _do(client, issuer, BUYER, bid, "cancel")
    assert client.get(f"/internal/people/{BUYER}/open", headers=INTERNAL).json() == {"open": 0}
    [b] = client.get(f"/internal/people/{BUYER}/export", headers=INTERNAL).json()["bookings"]
    assert b["id"] == bid and b["status"] == "cancelled"


def test_the_handover_address_is_shared_only_once_accepted(client, app, issuer):
    bid = _requested(client, app, issuer)
    assert "handover" not in client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
    _do(client, issuer, HOST, bid, "accept")
    for who in (BUYER, HOST):
        h = client.get(f"/bookings/{bid}", headers=issuer.headers(who)).json()["handover"]
        assert h["address"].startswith("Tempelhofer Damm") and h["instructions"]
    assert client.get(f"/bookings/{bid}", headers=issuer.headers("stranger")).status_code == 404
    # V4-9: the owner corrects the address after accepting; the renter sees it.
    corrected = {"address": "Tempelhofer Damm 7, 12101 Berlin", "instructions": "Side door"}
    app.state.catalog.handover = lambda _lid: _async(corrected)
    assert (
        client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER))
        .json()["handover"]["address"]
        .endswith("7, 12101 Berlin")
    )


async def _async(value):  # noqa: ANN001, ANN202
    return value


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
        assert b["status"] == "declined" and b["declineReason"] == "The listing was removed by its owner"
    assert client.get(f"/bookings/{accepted}", headers=issuer.headers(BUYER)).json()["status"] == "accepted"
    # FL-9: a staff take-down says so.
    later = _requested(client, app, issuer, start_h=60)
    ev = Event(
        id=new_id("ev"),
        type=LISTING_CHANGED,
        source="catalog",
        occurred_at=now_iso(),
        data={"listingId": "l9", "change": "removed", "by": "staff"},
    )
    assert call(app, app.state.dispatcher.handle, ev)
    b = client.get(f"/bookings/{later}", headers=issuer.headers(BUYER)).json()
    assert b["declineReason"] == "The listing was taken down by Cappy"


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
    # Accepted: what was masked before is shown as written, to both sides.
    first = page["items"][0]["body"]
    assert "+49 151 2345 6789" in first and "erin@example.com" in first and HIDDEN not in first
    assert client.get(f"/bookings/{bid}/messages", headers=issuer.headers("stranger")).status_code == 404
    call(app, app.state.relay.flush)
    assert [e.data["recipientId"] for e in broker.of_type(BOOKING_MESSAGE)] == [HOST, BUYER, BUYER]


def test_contact_details_stay_masked_when_the_booking_is_never_accepted(client, app, issuer):
    from booking.messages import HIDDEN

    bid = _requested(client, app, issuer)
    client.post(f"/bookings/{bid}/messages", json={"body": "Mail erin@example.com"}, headers=issuer.headers(BUYER))
    _do(client, issuer, HOST, bid, "decline")
    [m] = client.get(f"/bookings/{bid}/messages", headers=issuer.headers(HOST)).json()["items"]
    assert HIDDEN in m["body"] and "example.com" not in m["body"]


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
    assert (
        client.post(f"/admin/bookings/{bid}/resolve", json=body, headers=staff).json()["booking"]["status"]
        == "cancelled"
    )


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


def test_hand_over_photos_are_seen_only_through_signed_links(client, app, issuer):
    from urllib.parse import parse_qs, urlparse

    bid = _requested(client, app, issuer, start_h=0.25)
    _do(client, issuer, HOST, bid, "accept")
    ref = "evidence:" + "b" * 40 + ".webp"
    r = client.post(
        f"/bookings/{bid}/evidence", json={"stage": "check_in", "photos": [ref]}, headers=issuer.headers(HOST)
    )
    assert r.status_code == 201
    link = client.get(f"/bookings/{bid}/evidence", headers=issuer.headers(BUYER)).json()[0]["photos"][0]
    assert link.startswith(f"/api/bookings/{bid}/evidence/") and "sig=" in link
    path = urlparse(link).path.removeprefix("/api")
    q = {k: v[0] for k, v in parse_qs(urlparse(link).query).items()}
    got = client.get(path, params=q, headers={"Authorization": ""})  # an <img>: no session, the link is the key
    assert got.status_code == 200 and got.content == b"RIFF" + b"b" * 40 + b".webp"
    assert got.headers["cache-control"].startswith("private")
    assert client.get(path, params={**q, "sig": "0" * 64}, headers={"Authorization": ""}).status_code == 403
    assert client.get(path, params={**q, "exp": "1"}, headers={"Authorization": ""}).status_code == 403
    other = path.rsplit("/", 1)[0] + "/1"
    assert client.get(other, params=q, headers={"Authorization": ""}).status_code == 403, "signed per photo"
    # Staff see them only with the staff group; strangers never.
    assert client.get(f"/bookings/{bid}/evidence", headers=issuer.headers("stranger")).status_code == 404
    staff = issuer.headers("mod-1", **{"cognito:groups": ["admin"]})
    assert len(client.get(f"/bookings/{bid}/evidence", headers=staff).json()) == 1
    # The host's data export carries the photos as links too, good for a day.
    exported = client.get(f"/internal/people/{HOST}/export", headers=INTERNAL).json()["evidence"][0]["photos"][0]
    assert exported.startswith(f"/api/bookings/{bid}/evidence/") and "evidence:" not in exported
    q = {k: v[0] for k, v in parse_qs(urlparse(exported).query).items()}
    assert int(q["exp"]) > time.time() + 3600
    assert (
        client.get(urlparse(exported).path.removeprefix("/api"), params=q, headers={"Authorization": ""}).status_code
        == 200
    )


def test_booking_requests_per_day_are_limited(client, app, issuer):
    # Unpaid bookings are also capped (3); pay each so only the daily cap bites.
    for i in range(10):
        bid = _book(client, issuer, start_h=24 + i * 3)["booking"]["id"]
        _authorise(app, bid)
    r = client.post("/bookings", json=_body(start_h=60), headers=issuer.headers(BUYER))
    assert r.status_code == 429 and "a lot of booking requests" in r.json()["error"]["message"]


def test_expensive_bookings_need_a_verified_renter(issuer, broker, payments, monkeypatch):
    import booking.routes
    from cappy_common.events import IDENTITY_VERIFIED
    from cappy_common.markets import market

    # The owner's market sets the threshold, in its currency (M-2): make it low.
    cheap = market("DE").model_copy(update={"id_check_above": 1000})
    monkeypatch.setattr(booking.routes, "market", lambda country: cheap)
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(
        settings, matching=FakeMatching(), payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier()
    )
    with TestClient(app) as c:
        r = c.post("/bookings", json=_body(), headers=issuer.headers(BUYER))
        assert r.status_code == 403 and r.json()["error"]["code"] == "verification_required"
        ev = Event(
            id=new_id("ev"), type=IDENTITY_VERIFIED, source="payments", occurred_at=now_iso(), data={"personId": BUYER}
        )
        c.portal.call(app.state.dispatcher.handle, ev)
        assert c.post("/bookings", json=_body(), headers=issuer.headers(BUYER)).status_code == 201


def test_export_includes_messages_and_evidence_and_deletion_clears_blocks(client, app, issuer):
    from cappy_common.events import PROFILE_DELETED

    bid = _requested(client, app, issuer)
    client.post(f"/bookings/{bid}/messages", json={"body": "Is the rail included?"}, headers=issuer.headers(BUYER))
    client.put(f"/me/blocks/{HOST}", headers=issuer.headers(BUYER))
    out = client.get(f"/internal/people/{BUYER}/export", headers=INTERNAL).json()
    assert [b["id"] for b in out["bookings"]] == [bid]
    assert out["messagesSent"][0]["body"] == "Is the rail included?"
    ev = Event(id=new_id("ev"), type=PROFILE_DELETED, source="catalog", occurred_at=now_iso(), data={"ownerId": BUYER})
    assert call(app, app.state.dispatcher.handle, ev)
    later = issuer.headers(BUYER, iat=int(time.time()) + 1)  # a sign-in after the deletion
    assert client.get("/me/blocks", headers=later).json() == []


def test_instant_book_confirms_once_the_card_is_held(issuer, broker, payments):
    matching = FakeMatching()
    matching.instant = True
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, matching=matching, payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        bid = c.post("/bookings", json=_body(), headers=issuer.headers(BUYER)).json()["booking"]["id"]
        assert _authorise(app, bid)
        b = c.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()
        assert b["status"] == "accepted" and b["listing"]["instantBook"] is True


def test_the_owner_rates_the_renter_once_after_completion(client, app, issuer, broker):
    from cappy_common.events import RENTER_RATED

    bid = _requested(client, app, issuer, start_h=0.25)
    rate = lambda who, q: client.post(f"/bookings/{bid}/rate-renter", json={"quality": q}, headers=issuer.headers(who))  # noqa: E731
    _do(client, issuer, HOST, bid, "accept")
    assert rate(HOST, 5).status_code == 409, "not before completion"
    _do(client, issuer, HOST, bid, "start")
    _do(client, issuer, BUYER, bid, "complete")
    assert rate(BUYER, 5).status_code == 403
    assert rate(HOST, 4).json()["renterRating"] == 4
    assert rate(HOST, 5).status_code == 409
    call(app, app.state.relay.flush)
    assert broker.of_type(RENTER_RATED) == [], "blind until the renter reviews too, or the window closes"
    # The window closes: what is in is published by the sweep.
    ended = datetime.now(UTC) - timedelta(days=15)
    call(app, _age, app, bid, window_start=ended - timedelta(hours=2), window_end=ended)
    call(app, sweep_once, app)
    call(app, app.state.relay.flush)
    assert [(e.data["renterId"], e.data["quality"]) for e in broker.of_type(RENTER_RATED)] == [(BUYER, 4)]
    assert _do(client, issuer, BUYER, bid, "rate", onTime=True, quality=5).status_code == 409, "reviews closed"


def test_cancellation_policy_decides_the_refund(issuer, broker, payments):
    matching = FakeMatching()
    matching.listing = matching.listing.model_copy(update={"cancellation_policy": "strict"})
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite://",
        internal_token="i" * 40,
        feature_flags="paidCancellationPolicies:100",
    )
    app = build_app(settings, matching=matching, payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        # Accepted, starting in 3 days: strict keeps half.
        bid = c.post("/bookings", json=_body(start_h=72), headers=issuer.headers(BUYER)).json()["booking"]["id"]
        _authorise(app, bid)
        c.post(f"/bookings/{bid}/accept", headers=issuer.headers(HOST))
        quote = c.get(f"/bookings/{bid}/cancellation", headers=issuer.headers(BUYER)).json()
        assert quote == {"refundAmount": 2300, "currency": "EUR", "policy": "strict", "charged": True}
        assert c.get(f"/bookings/{bid}/cancellation", headers=issuer.headers(HOST)).json()["refundAmount"] == 4600, (
            "owner cancels: in full"
        )
        done = c.post(f"/bookings/{bid}/cancel", headers=issuer.headers(BUYER)).json()
        assert done["status"] == "cancelled" and done["refundAmount"] == 2300


def test_flexible_only_until_counsel_confirms(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=30)
    _do(client, issuer, HOST, bid, "accept")
    q = client.get(f"/bookings/{bid}/cancellation", headers=issuer.headers(BUYER)).json()
    assert q["policy"] == "flexible" and q["refundAmount"] == 4600


def test_withdrawing_a_request_releases_the_hold_and_refunds_nothing(client, app, issuer):
    """FL-8: nothing was charged before accept, so no refund is claimed."""
    bid = _requested(client, app, issuer, start_h=30)
    q = client.get(f"/bookings/{bid}/cancellation", headers=issuer.headers(BUYER)).json()
    assert (q["charged"], q["refundAmount"]) == (False, 0)
    done = _do(client, issuer, BUYER, bid, "cancel").json()
    assert done["status"] == "cancelled" and done.get("refundAmount") is None


def test_neither_side_sees_the_other_s_review_before_publication(client, app, issuer):
    bid = _requested(client, app, issuer, start_h=0.25)
    for who, action in ((HOST, "accept"), (HOST, "start"), (BUYER, "complete")):
        _do(client, issuer, who, bid, action)
    _do(client, issuer, BUYER, bid, "rate", onTime=True, quality=1)
    assert "outcome" not in client.get(f"/bookings/{bid}", headers=issuer.headers(HOST)).json(), "blind to the owner"
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(BUYER)).json()["outcome"]["quality"] == 1
    export = lambda: client.get(f"/internal/people/{BUYER}/export", headers=INTERNAL).json()  # noqa: E731
    assert export()["renterRatingsAboutMe"] == [], "not before the owner has rated"
    r = client.post(f"/bookings/{bid}/rate-renter", json={"quality": 5}, headers=issuer.headers(HOST)).json()
    assert r["outcome"]["quality"] == 1 and r["renterRating"] == 5, "both published: both visible"
    # V7-16: the renter's export has how they were rated, once published.
    assert [x["rating"] for x in export()["renterRatingsAboutMe"]] == [5]


def test_a_reinstated_person_can_book_again(client, app, issuer):
    from cappy_common.events import OWNER_REINSTATED, OWNER_SUSPENDED

    for t in (OWNER_SUSPENDED, OWNER_REINSTATED):
        call(
            app,
            app.state.dispatcher.handle,
            Event(id=new_id("ev"), type=t, source="catalog", occurred_at=now_iso(), data={"ownerId": BUYER}),
        )
    assert client.post("/bookings", json=_body(), headers=issuer.headers(BUYER)).status_code == 201


def test_suspending_someone_declines_their_pending_requests(client, app, issuer):
    from cappy_common.events import OWNER_SUSPENDED

    bid = _requested(client, app, issuer)
    call(
        app,
        app.state.dispatcher.handle,
        Event(id=new_id("ev"), type=OWNER_SUSPENDED, source="catalog", occurred_at=now_iso(), data={"ownerId": BUYER}),
    )
    assert client.get(f"/bookings/{bid}", headers=issuer.headers(HOST)).json()["status"] == "declined"


def test_a_retried_message_is_sent_once_and_pay_outside_is_flagged(client, app, issuer):
    bid = _requested(client, app, issuer)
    h = {**issuer.headers(BUYER), "Idempotency-Key": "k-msg-1"}
    body = {"body": "Can I pay you by PayPal instead?"}
    first = client.post(f"/bookings/{bid}/messages", json=body, headers=h)
    again = client.post(f"/bookings/{bid}/messages", json=body, headers=h)
    assert first.status_code == again.status_code == 201 and first.json()["id"] == again.json()["id"]
    assert first.json()["flagged"] is True, "asking to pay around Cappy is flagged, not blocked"
    page = client.get(f"/bookings/{bid}/messages", headers=issuer.headers(HOST)).json()["items"]
    assert len(page) == 1 and page[0]["flagged"] is True
    changed = client.post(f"/bookings/{bid}/messages", json={"body": "something else"}, headers=h)
    assert changed.status_code == 422


def test_messages_are_capped_per_sender_so_pushes_cannot_flood(client, app, issuer):
    from booking.messages import MESSAGES_PER_WINDOW

    bid = _requested(client, app, issuer)
    for i in range(MESSAGES_PER_WINDOW):
        assert (
            client.post(
                f"/bookings/{bid}/messages", json={"body": f"hi {i}"}, headers=issuer.headers(BUYER)
            ).status_code
            == 201
        )
    r = client.post(f"/bookings/{bid}/messages", json={"body": "one more"}, headers=issuer.headers(BUYER))
    assert r.status_code == 429
    assert (
        client.post(f"/bookings/{bid}/messages", json={"body": "hello"}, headers=issuer.headers(HOST)).status_code
        == 201
    )


# --- no-shows, owner reliability, cards shared with suspended accounts (S-11, S-17, S-18) ---


def _accepted(client, app, issuer, start_h: float = 40) -> str:
    bid = _requested(client, app, issuer, start_h=start_h)
    assert _do(client, issuer, HOST, bid, "accept").json()["status"] == "accepted"
    return bid


def _started(app, bid: str, minutes_ago: float) -> None:
    started = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    call(app, _age, app, bid, window_start=started, window_end=started + timedelta(hours=3))


def _events(app, broker, type_: str) -> list[dict]:
    call(app, app.state.relay.flush)
    return [e.data for e in broker.of_type(type_)]


def test_an_owner_no_show_refunds_the_renter_in_full(client, app, issuer, broker):
    from cappy_common.events import OWNER_RELIABILITY

    bid = _accepted(client, app, issuer)
    assert _do(client, issuer, BUYER, bid, "no-show").status_code == 409, "not before the booked time"
    _started(app, bid, 5)
    assert _do(client, issuer, "stranger", bid, "no-show").status_code == 404
    b = _do(client, issuer, BUYER, bid, "no-show").json()
    assert (b["status"], b["noShow"], b["refundAmount"]) == ("cancelled", "owner", 4600)
    changed = _events(app, broker, BOOKING_STATUS_CHANGED)[-1]
    assert changed["noShow"] == "owner" and changed["refundAmount"] == 4600
    assert _events(app, broker, OWNER_RELIABILITY)[-1] == {"ownerId": HOST, "rate": None, "bookings": 1, "failures": 1}


def test_a_renter_no_show_is_reported_after_a_grace_and_refunds_nothing(client, app, issuer, broker):
    from cappy_common.events import OWNER_RELIABILITY

    bid = _accepted(client, app, issuer)
    _started(app, bid, 10)
    assert _do(client, issuer, HOST, bid, "no-show").status_code == 409, "the renter may be running late"
    _started(app, bid, 40)
    b = _do(client, issuer, HOST, bid, "no-show").json()
    assert (b["status"], b["noShow"], b["refundAmount"]) == ("cancelled", "renter", 0)
    # A renter's no-show says nothing about the owner.
    assert _events(app, broker, OWNER_RELIABILITY)[-1]["failures"] == 0


def test_no_shows_are_reported_in_the_first_two_hours_only(client, app, issuer):
    bid = _accepted(client, app, issuer)
    _started(app, bid, 130)
    assert _do(client, issuer, BUYER, bid, "no-show").status_code == 409
    other = _requested(client, app, issuer, start_h=60)
    assert _do(client, issuer, BUYER, other, "no-show").status_code == 409, "only an accepted booking"


def test_owner_cancellations_set_a_rate_and_three_in_a_month_reach_staff(client, app, issuer, broker):
    from cappy_common.events import OWNER_RELIABILITY, PERSON_FLAGGED

    bids = [_accepted(client, app, issuer, start_h=40 + 3 * i) for i in range(5)]
    for bid in bids[:2]:
        assert _do(client, issuer, HOST, bid, "cancel").json()["status"] == "cancelled"
    assert _events(app, broker, PERSON_FLAGGED) == []
    # The renter cancelling is not the owner's fault.
    _do(client, issuer, BUYER, bids[4], "cancel")
    assert _events(app, broker, OWNER_RELIABILITY)[-1]["failures"] == 2
    _do(client, issuer, HOST, bids[2], "cancel")
    assert _events(app, broker, OWNER_RELIABILITY)[-1] == {"ownerId": HOST, "rate": 0.6, "bookings": 5, "failures": 3}
    [flag] = _events(app, broker, PERSON_FLAGGED)
    assert flag["personId"] == HOST and flag["reason"] == "reliability"


def test_owners_response_time_and_rate_are_measured_not_made_up(client, app, issuer, broker):
    """H-1: nothing is claimed under three requests; then the median minutes
    to answer and the share answered before the request lapsed. A lapse
    counts against the owner, a renter withdrawing does not count at all."""
    from cappy_common.events import OWNER_RELIABILITY

    def measured() -> dict:
        return [e for e in _events(app, broker, OWNER_RELIABILITY) if "responseMins" in e][-1]

    asked_ago = lambda bid, minutes: call(  # noqa: E731
        app, _age_transition, app, bid, "requested", datetime.now(UTC) - timedelta(minutes=minutes)
    )
    first = _requested(client, app, issuer, start_h=40)
    asked_ago(first, 30)
    _do(client, issuer, HOST, first, "accept")
    assert measured() == {"ownerId": HOST, "responseMins": None, "responseRate": None}, "one request says nothing"

    second = _requested(client, app, issuer, start_h=50)
    asked_ago(second, 90)
    assert _do(client, issuer, HOST, second, "decline", reason="Booked elsewhere that day").status_code == 200
    withdrawn = _requested(client, app, issuer, start_h=60)
    _do(client, issuer, BUYER, withdrawn, "cancel")
    lapsed = _requested(client, app, issuer, start_h=70)
    assert call(app, _expire, app, lapsed) == 1
    assert measured() == {"ownerId": HOST, "responseMins": 60, "responseRate": 0.6667}


def test_a_card_a_suspended_account_used_puts_the_new_account_in_front_of_staff(client, app, issuer, broker):
    from cappy_common.events import OWNER_SUSPENDED, PERSON_FLAGGED

    def authorise(bid: str, fp: str) -> None:
        data = {"bookingId": bid, "cardFingerprint": fp}
        ev = Event(id=new_id("ev"), type=PAYMENT_AUTHORISED, source="payments", occurred_at=now_iso(), data=data)
        assert call(app, app.state.dispatcher.handle, ev)

    first = client.post("/bookings", json=_body(start_h=40), headers=issuer.headers("banned-1")).json()
    authorise(first["booking"]["id"], "fp_card_1")
    ev = Event(
        id=new_id("ev"), type=OWNER_SUSPENDED, source="catalog", occurred_at=now_iso(), data={"ownerId": "banned-1"}
    )
    assert call(app, app.state.dispatcher.handle, ev)
    assert _events(app, broker, PERSON_FLAGGED) == []

    mine = _book(client, issuer, start_h=60)["booking"]["id"]
    authorise(mine, "fp_card_1")
    assert client.get(f"/bookings/{mine}", headers=issuer.headers(BUYER)).json()["status"] == "requested"
    [flag] = _events(app, broker, PERSON_FLAGGED)
    assert flag["personId"] == BUYER and flag["reason"] == "linked_to_suspended" and "banned-1" in flag["details"]

    theirs_too = _book(client, issuer, start_h=80)["booking"]["id"]
    authorise(theirs_too, "fp_other_card")
    assert len(_events(app, broker, PERSON_FLAGGED)) == 1, "a different card links nobody"


def test_active_people_for_the_transparency_numbers(client, app, issuer):
    _book(client, issuer)
    since = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    params = {"from": since, "until": until}
    assert client.get("/internal/stats/active-people", params=params).status_code == 403
    r = client.get("/internal/stats/active-people", params=params, headers=INTERNAL)
    assert r.json() == {"people": 2}


def test_paid_policies_follow_the_flag_the_app_reads():
    from booking.settings import Settings as BookingSettings

    base = dict(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    assert not BookingSettings(**base).paid_cancellation_policies
    assert BookingSettings(**base, feature_flags="paidCancellationPolicies:100").paid_cancellation_policies
    # Money rules are everyone or no one.
    assert not BookingSettings(**base, feature_flags="paidCancellationPolicies:50").paid_cancellation_policies


def test_deletion_redacts_what_names_or_locates_the_person(client, app, issuer):
    """D-5: the booking stays for accounting; the owner's name and business,
    the hand-over address, notes and evidence of the deleted person go."""
    from booking.tables import BookingRow, EvidenceRow
    from cappy_common.events import PROFILE_DELETED

    bid = _requested(client, app, issuer)
    _do(client, issuer, HOST, bid, "accept")

    async def dress():
        async with app.state.db.transaction() as s:
            row = await s.get(BookingRow, bid)
            row.listing_snapshot = {
                **row.listing_snapshot,
                "ownerName": "Nadia Brandt",
                "ownerBusiness": {"legalName": "NB"},
            }
            row.handover = {"address": "Oranienstr. 5", "instructions": "Code 4711"}
            row.card_fingerprint = "fp_buyer"
            row.outcome = {"quality": 5, "onTime": True, "note": "Nadia was lovely"}
            s.add(
                EvidenceRow(
                    id="ev_1",
                    booking_id=bid,
                    by=BUYER,
                    stage="check_in",
                    photos=["a.jpg"],
                    note="Scratch",
                    at=datetime.now(UTC),
                )
            )

    call(app, dress)
    for person in (HOST, BUYER):
        ev = Event(
            id=new_id("ev"), type=PROFILE_DELETED, source="catalog", occurred_at=now_iso(), data={"ownerId": person}
        )
        assert call(app, app.state.dispatcher.handle, ev)

    async def left():
        async with app.state.db.transaction() as s:
            return await s.get(BookingRow, bid), await s.get(EvidenceRow, "ev_1")

    row, evidence = call(app, left)
    assert row.listing_snapshot["ownerName"] == "Former member" and "ownerBusiness" not in row.listing_snapshot
    assert row.handover is None and row.card_fingerprint is None and row.outcome["note"] is None
    assert (evidence.photos, evidence.note) == ([], None)
    assert row.amount and row.status == "accepted", "the booking itself stays"


def test_a_closed_booking_s_conversation_is_read_only(client, app, issuer):
    """FL-18: no new messages once a booking will never happen."""
    bid = _requested(client, app, issuer, start_h=30)
    say = lambda: client.post(f"/bookings/{bid}/messages", json={"body": "Still on?"}, headers=issuer.headers(BUYER))  # noqa: E731
    assert say().status_code == 201
    _do(client, issuer, BUYER, bid, "cancel")
    r = say()
    assert r.status_code == 409 and r.json()["error"]["code"] == "conversation_closed"


def test_moderation_can_read_a_message_s_author_and_remove_its_words(client, app, issuer):
    """FL-7, the booking half: catalog asks who wrote it, then removes it."""
    bid = _requested(client, app, issuer, start_h=30)
    mid = client.post(
        f"/bookings/{bid}/messages", json={"body": "Rude words here"}, headers=issuer.headers(BUYER)
    ).json()["id"]
    assert client.get(f"/internal/messages/{mid}").status_code == 403
    assert client.get(f"/internal/messages/{mid}", headers=INTERNAL).json() == {"senderId": BUYER}
    assert client.post(f"/internal/messages/{mid}/remove", headers=INTERNAL).status_code == 204
    [m] = client.get(f"/bookings/{bid}/messages", headers=issuer.headers(HOST)).json()["items"]
    assert m["body"].startswith("[removed by Cappy")
    assert client.get("/internal/messages/nope", headers=INTERNAL).status_code == 404


def test_a_booking_is_in_its_listing_s_currency(issuer, broker, payments):
    """M-3: a Toronto listing priced in CAD is booked and paid in CAD."""
    matching = FakeMatching()
    matching.listing = matching.listing.model_copy(update={"currency": "CAD"})
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(settings, matching=matching, payments=payments, catalog=FakeCatalog(), verifier=issuer.verifier())
    with TestClient(app) as c:
        app.state._portal = c.portal
        b = c.post("/bookings", json=_body(), headers=issuer.headers(BUYER)).json()["booking"]
        assert b["currency"] == "CAD", "ISO 4217 uppercase, like the listing and quote"
        assert payments.currencies[-1] == "CAD", "and paid in it (the Stripe adapter lowercases)"
