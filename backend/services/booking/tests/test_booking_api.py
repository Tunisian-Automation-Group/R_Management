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
from cappy_common.errors import Unavailable
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

    async def start(self, *, booking_id, requester_id, owner_id, amount, currency) -> PaymentStart:  # noqa: ANN001
        if self.down:
            raise Unavailable("stripe is down")
        self.started.append(booking_id)
        return PaymentStart(client_secret=f"pi_{booking_id}_secret", intent_id=f"pi_{booking_id}")


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
    return build_app(settings, matching=FakeMatching(), payments=payments, verifier=issuer.verifier())


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
    a = client.post("/bookings", json=_body(), headers=h).json()
    b = client.post("/bookings", json=_body(), headers=h).json()
    assert a["booking"]["id"] == b["booking"]["id"]
    assert b["payment"]["clientSecret"] == a["payment"]["clientSecret"]
    assert len(client.get("/bookings", headers=issuer.headers(BUYER)).json()["items"]) == 1


def test_payments_down_releases_the_window(client, issuer, payments):
    payments.down = True
    r = client.post("/bookings", json=_body(), headers=issuer.headers(BUYER))
    assert r.status_code == 503
    [b] = client.get("/bookings", headers=issuer.headers(BUYER)).json()["items"]
    assert b["status"] == "payment_failed"
    payments.down = False
    _book(client, issuer)  # the window is free again


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
    bid = _requested(client, app, issuer)
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
