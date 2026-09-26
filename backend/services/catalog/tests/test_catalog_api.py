"""The catalog API: profiles, listings, photos, search, saved, candidates, ratings."""

from __future__ import annotations

import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from cappy_common.events import (
    BOOKING_RATED,
    LISTING_CHANGED,
    PAYOUTS_READY,
    PROFILE_CREATED,
    Event,
    reset_memory_broker,
)
from cappy_common.fixtures import build_world
from cappy_common.ids import new_id
from cappy_common.testing import TestIssuer
from cappy_common.timeutil import HOUR_MS, iso_from_ms, now_iso, now_ms
from catalog.main import build_app
from catalog.media import DirectoryStore
from catalog.repository import CatalogRepository
from catalog.settings import Settings

INTERNAL = {"X-Internal-Token": "i" * 40}
# The test client signs in by default; this is how a test is anonymous.
ANON = {"Authorization": ""}


@pytest.fixture()
def issuer():
    return TestIssuer()


@pytest.fixture()
def broker():
    return reset_memory_broker()


class FakeBookings:
    def __init__(self) -> None:
        self.open: dict[str, int] = {}

    async def open_for(self, person):  # noqa: ANN001
        n = self.open.get(person, 0)
        return {"open": n, "until": "2026-10-01T10:00:00Z" if n else None}

    async def all_for(self, person):  # noqa: ANN001
        return {"bookings": [{"id": "bk_1", "status": "completed"}], "messagesSent": [], "evidence": []}

    async def active_people(self, start, end):  # noqa: ANN001
        return 7

    removed: list[str] = []

    async def message_author(self, message_id):  # noqa: ANN001
        return {"msg_1": "user-b"}.get(message_id)

    async def remove_message(self, message_id):  # noqa: ANN001
        self.removed.append(message_id)

    async def aclose(self) -> None:
        pass


@pytest.fixture()
def bookings():
    return FakeBookings()


@pytest.fixture()
def app(issuer, broker, tmp_path, bookings):
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite://",
        internal_token="i" * 40,
        media_dir=str(tmp_path / "media"),
    )
    from catalog.clients import Notifications, Payments

    return build_app(
        settings,
        media_store=DirectoryStore(str(tmp_path / "media")),
        evidence_store=DirectoryStore(str(tmp_path / "private")),
        bookings=bookings,
        payments=Payments(),
        notifications=Notifications(),
        verifier=issuer.verifier(),
    )


def _run(app, coro_fn):
    """Run a coroutine against the app's database, on the client's loop."""
    return app.state._portal.call(coro_fn)


@pytest.fixture()
def client(app, issuer):
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:
        app.state._portal = c.portal

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())

        c.portal.call(seed)
        yield c


def flush(app):
    return app.state._portal.call(app.state.relay.flush)


def _hours_from_now(h: float) -> str:
    return iso_from_ms(now_ms() + int(h * HOUR_MS))


def _window_listing(**extra):
    return {
        "category": "workshop",
        "mode": "window",
        "title": "Cordless drill",
        "blurb": "Makita, two batteries",
        "district": "Kreuzberg",
        "instructions": "Ring the bell",
        "rules": ["Bring it back charged"],
        "active": True,
        "ratePerHour": 200,
        "minHours": 2,
        "maxHours": 8,
        "extraFee": 0,
        "extraLabel": "",
        **extra,
    }


def _slot(start_h=2, end_h=20, usable=18):
    return {"start": _hours_from_now(start_h), "end": _hours_from_now(end_h), "hoursUsable": usable}


def _profile(client, issuer, sub="user-a", name="Ada Lovelace"):
    r = client.put(
        "/me",
        json={"adult": True, "name": name, "kind": "person", "district": "Kreuzberg"},
        headers=issuer.headers(sub),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _png(shade: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (10, 200, shade)).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (3000, 2000), (200, 80, 40))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (52.0, 30.0, 0.0), 3: "E", 4: (13.0, 25.0, 0.0)}  # GPSInfo
    exif[0x010F] = "PhoneMaker"
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


# --- identity and profiles -----------------------------------------------------------


def test_nobody_is_anybody_without_a_token(client):
    assert client.get("/me", headers=ANON).status_code == 401
    assert client.get("/me", headers={**ANON, "X-Cappy-User": "o1"}).status_code == 401
    assert client.get("/saved", headers=ANON).status_code == 401


def test_profile_is_created_once_and_a_record_cannot_be_declared(client, issuer, app, broker):
    me = client.get("/me", headers=issuer.headers("user-a")).json()
    assert me == {"id": "user-a", "homeDistrict": "Kreuzberg"}  # no owner yet

    owner = _profile(client, issuer)
    assert owner["id"] == "user-a" and owner["initials"] == "AL"
    assert (owner["ratingSum"], owner["jobsDone"], owner["verified"]) == (0, 0, False)

    again = client.put(
        "/me",
        json={
            "name": "Ada L",
            "kind": "business",
            "district": "Neukölln",
            "business": {"legalName": "Ada L GmbH", "address": "Oranienstraße 1, 10999 Berlin"},
            "ratingSum": 500,
            "jobsDone": 100,
        },
        headers=issuer.headers("user-a"),
    ).json()
    assert again["kind"] == "business" and again["district"] == "Neukölln"
    assert (again["ratingSum"], again["jobsDone"]) == (0, 0)

    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(PROFILE_CREATED)] == ["user-a"]


def test_profile_needs_a_known_district(client, issuer):
    r = client.put(
        "/me",
        json={"adult": True, "name": "Ada", "kind": "person", "district": "Atlantis"},
        headers=issuer.headers("u"),
    )
    assert r.status_code == 422


# --- listings ---------------------------------------------------------------------------


def test_listing_needs_a_profile(client, issuer):
    r = client.post("/listings", json={"listing": _window_listing(), "slots": []}, headers=issuer.headers("nobody"))
    assert r.status_code == 403


def test_server_mints_ids_and_ignores_the_client_s(client, issuer, app, broker):
    _profile(client, issuer)
    body = {"listing": _window_listing(id="l1", ownerId="o1"), "slots": [{**_slot(), "id": "s1", "listingId": "l1"}]}
    r = client.post("/listings", json=body, headers=issuer.headers("user-a"))
    assert r.status_code == 201, r.text
    created = r.json()
    lid = created["listing"]["id"]
    assert lid.startswith("ls_") and lid != "l1"
    assert created["listing"]["ownerId"] == "user-a"  # never the body's o1
    assert created["slots"][0]["id"].startswith("sl_") and created["slots"][0]["listingId"] == lid
    flush(app)
    assert broker.of_type(LISTING_CHANGED)[-1].data == {"listingId": lid, "change": "created"}


@pytest.mark.parametrize(
    "override, message",
    [
        ({"title": "x" * 121}, "title"),
        ({"instructions": "x" * 2001}, "instructions"),
        ({"rules": ["r"] * 13}, "rules"),
        ({"category": "fabrication"}, "booked by batch"),
        ({"district": "Atlantis"}, "district"),
        ({"ratePerHour": 0}, "ratePerHour"),
        ({"extraFee": -5000}, "extraFee"),
        ({"currency": "JPY"}, "priced in EUR"),
        ({"currency": "USD"}, "priced in EUR"),
        ({"minHours": 0}, "minHours"),
        ({"minHours": 8, "maxHours": 2}, "minHours"),
        ({"photos": ["https://evil.example/pixel.gif"]}, "uploaded"),
    ],
)
def test_listing_validation(client, issuer, override, message):
    _profile(client, issuer)
    r = client.post("/listings", json={"listing": _window_listing(**override)}, headers=issuer.headers("user-a"))
    assert r.status_code == 422 and message in r.json()["error"]["message"], r.text


def test_slots_are_validated(client, issuer):
    _profile(client, issuer)
    bad = [
        {"start": _hours_from_now(5), "end": _hours_from_now(2), "hoursUsable": 1},  # ends before it starts
        {"start": _hours_from_now(1), "end": _hours_from_now(3), "hoursUsable": 5},  # more usable than wall
        {"start": _hours_from_now(-9), "end": _hours_from_now(-1), "hoursUsable": 1},  # in the past
    ]
    for slot in bad:
        r = client.post(
            "/listings", json={"listing": _window_listing(), "slots": [slot]}, headers=issuer.headers("user-a")
        )
        assert r.status_code == 422, (slot, r.text)


def test_only_the_owner_manages_a_listing(client, issuer):
    _profile(client, issuer)
    lid = client.post(
        "/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=issuer.headers("user-a")
    ).json()["listing"]["id"]
    intruder = issuer.headers("user-b")
    for method, path in [
        ("post", f"/listings/{lid}/pause"),
        ("delete", f"/listings/{lid}"),
        ("put", f"/listings/{lid}"),
        ("post", f"/listings/{lid}/slots"),
    ]:
        kwargs = (
            {"json": {"listing": _window_listing()} if method == "put" else []} if method in ("put", "post") else {}
        )
        r = getattr(client, method)(path, headers=intruder, **kwargs)
        assert r.status_code == 404, (method, path, r.text)

    owner = issuer.headers("user-a")
    assert client.post(f"/listings/{lid}/pause", headers=owner).json()["active"] is False
    # Paused: the owner still sees it; nobody else does.
    assert client.get(f"/listings/{lid}", headers=owner).status_code == 200
    assert client.get(f"/listings/{lid}").status_code == 404
    assert client.post(f"/listings/{lid}/resume", headers=owner).json()["active"] is True
    assert client.delete(f"/listings/{lid}", headers=owner).status_code == 204
    assert client.get(f"/listings/{lid}", headers=owner).status_code == 404


def test_listing_detail_and_reviews_page(client):
    detail = client.get("/listings/l9").json()
    assert detail["listing"]["id"] == "l9" and detail["owner"]["id"] == detail["listing"]["ownerId"]
    assert detail["district"]["name"] == detail["listing"]["district"]
    assert all(s["listingId"] == "l9" for s in detail["slots"])
    summary = detail["reviews"]
    assert summary["count"] >= 1 and 1 <= summary["average"] <= 5

    first = client.get("/listings/l9/reviews", params={"limit": 1}).json()
    assert len(first["items"]) == 1
    if summary["count"] > 1:
        second = client.get("/listings/l9/reviews", params={"limit": 1, "cursor": first["nextCursor"]}).json()
        assert second["items"][0]["id"] != first["items"][0]["id"]


def test_my_listings_are_paginated(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    ids = {
        client.post("/listings", json={"listing": _window_listing(title=f"Drill {i}")}, headers=h).json()["listing"][
            "id"
        ]
        for i in range(5)
    }
    seen, cursor = set(), None
    while True:
        page = client.get("/me/listings", params={"limit": 2, "cursor": cursor}, headers=h).json()
        seen |= {v["listing"]["id"] for v in page["items"]}
        cursor = page.get("nextCursor")
        if not cursor:
            break
    assert seen == ids


def test_my_listings_carry_their_upcoming_windows(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    client.post("/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=h)
    [view] = client.get("/me/listings", headers=h).json()["items"]
    assert len(view["slots"]) == 1 and view["slots"][0]["hoursUsable"] == 18
    # Nobody else's view of a listing carries them.
    assert "slots" not in client.get("/search", params={"q": "drill"}).json()["items"][0]


# --- photos ---------------------------------------------------------------------------------


def test_uploads_are_reencoded_without_metadata(client, issuer, tmp_path):
    _profile(client, issuer)
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif().get(0x8825)  # the original does carry GPS
    r = client.post("/uploads", files={"file": ("p.jpg", raw, "image/jpeg")}, headers=issuer.headers("user-a"))
    assert r.status_code == 201, r.text
    up = r.json()
    assert up["url"].startswith("/media/") and up["url"].endswith(".webp")
    assert max(up["width"], up["height"]) == 2000  # bounded
    stored = client.get(up["url"]).content
    out = Image.open(io.BytesIO(stored))
    assert out.format == "WEBP" and not out.getexif() and "exif" not in out.info

    # The owner can use it; nobody else can put it on their listing.
    listing = _window_listing(photos=[up["url"]])
    assert client.post("/listings", json={"listing": listing}, headers=issuer.headers("user-a")).status_code == 201
    _profile(client, issuer, sub="user-b", name="Bob Builder")
    r = client.post("/listings", json={"listing": listing}, headers=issuer.headers("user-b"))
    assert r.status_code == 422 and "owner uploaded" in r.text


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"<html><script>alert(1)</script></html>",
        b"\xff\xd8\xff\xe0" + b"not really a jpeg" * 10,
    ],
)
def test_non_images_are_refused(client, issuer, payload):
    _profile(client, issuer)
    r = client.post("/uploads", files={"file": ("x.jpg", payload, "image/jpeg")}, headers=issuer.headers("user-a"))
    assert r.status_code == 422


def test_decompression_bombs_are_refused_before_decoding(client, issuer, app):
    _profile(client, issuer)
    app.state.settings.media_max_pixels = 1_000_000
    buf = io.BytesIO()
    Image.new("L", (4000, 4000)).save(buf, format="PNG")  # compresses to almost nothing
    r = client.post(
        "/uploads", files={"file": ("b.png", buf.getvalue(), "image/png")}, headers=issuer.headers("user-a")
    )
    assert r.status_code == 422


def test_uploads_need_a_session(client):
    assert client.post("/uploads", files={"file": ("p.jpg", b"x", "image/jpeg")}, headers=ANON).status_code == 401


# --- search, cities, saved ----------------------------------------------------------------------


def test_search_is_paginated_and_scoped(client):
    page = client.get("/search", params={"q": "saw", "limit": 2}).json()
    assert page["items"] and all(
        "saw" in (v["listing"]["title"] + v["listing"]["blurb"]).lower() for v in page["items"]
    )
    berlin = client.get("/search", params={"q": "saw", "metro": "Berlin"}).json()["items"]
    assert berlin and all(v["listing"]["district"] for v in berlin)
    assert client.get("/search", params={"q": "zzzz-no-such-thing"}).json() == {"items": []}
    assert client.get("/search", params={"q": "a"}).status_code == 422  # too short to be useful
    # LIKE wildcards in the query are literals, not patterns.
    assert client.get("/search", params={"q": "%%%"}).json() == {"items": []}


def test_cities_are_an_aggregate(client):
    cities = client.get("/cities").json()
    assert cities[0]["city"] == "Berlin" and cities[0]["listings"] > 10
    assert {c["city"] for c in cities} >= {"Berlin", "Paris", "Milan", "Lisbon"}


def test_saved_is_per_person_and_idempotent(client, issuer):
    a, b = issuer.headers("user-a"), issuer.headers("user-b")
    assert client.put("/saved/l9", headers=a).status_code == 204
    assert client.put("/saved/l9", headers=a).status_code == 204
    assert client.put("/saved/l12", headers=a).status_code == 204
    mine = client.get("/saved", headers=a).json()["items"]
    assert [v["listing"]["id"] for v in mine] == ["l12", "l9"] and all(v["saved"] for v in mine)
    assert client.get("/saved", headers=b).json() == {"items": []}
    assert client.put("/saved/nope", headers=a).status_code == 404
    assert client.delete("/saved/l9", headers=a).status_code == 204
    assert [v["listing"]["id"] for v in client.get("/saved", headers=a).json()["items"]] == ["l12"]


# --- internal: candidates -----------------------------------------------------------------------


def test_internal_routes_need_the_service_token(client):
    body = {"origin": "Kreuzberg", "maxKm": 10, "start": now_iso(), "until": _hours_from_now(48)}
    assert client.post("/internal/candidates", json=body).status_code == 403
    assert client.post("/internal/candidates", json=body, headers=INTERNAL).status_code == 200


def test_candidates_are_bounded_and_self_contained(client):
    body = {"origin": "Kreuzberg", "maxKm": 5, "start": now_iso(), "until": _hours_from_now(72), "category": "workshop"}
    w = client.post("/internal/candidates", json=body, headers=INTERNAL).json()
    assert w["listings"], "expected nearby workshop capacity"
    assert all(l["category"] == "workshop" and l["active"] for l in w["listings"])
    owner_ids = {o["id"] for o in w["owners"]}
    assert {l["ownerId"] for l in w["listings"]} <= owner_ids
    assert {s["listingId"] for s in w["slots"]} <= {l["id"] for l in w["listings"]}
    assert "Kreuzberg" in w["districts"] and {l["district"] for l in w["listings"]} <= set(w["districts"])
    # Nothing from another city leaks into a 5 km search from Kreuzberg.
    assert all(w["districts"][l["district"]]["metro"] == "Berlin" for l in w["listings"])

    capped = client.post(
        "/internal/candidates", json={**body, "category": None, "maxKm": 2000, "cap": 3}, headers=INTERNAL
    ).json()
    assert len(capped["listings"]) == 3


def test_candidates_exclude_the_caller_s_own_and_windows_outside_the_range(client):
    far_future = {
        "origin": "Kreuzberg",
        "maxKm": 50,
        "start": _hours_from_now(24 * 400),
        "until": _hours_from_now(24 * 401),
    }
    assert client.post("/internal/candidates", json=far_future, headers=INTERNAL).json()["listings"] == []
    body = {"origin": "Kreuzberg", "maxKm": 50, "start": now_iso(), "until": _hours_from_now(72), "excludeOwner": "o1"}
    w = client.post("/internal/candidates", json=body, headers=INTERNAL).json()
    assert w["listings"] and all(l["ownerId"] != "o1" for l in w["listings"])


# --- the rating loop ------------------------------------------------------------------------------


def test_a_rating_applies_exactly_once_and_becomes_a_review(client, app):
    before = client.get("/owners/o1").json()
    booking_id = new_id("bk")
    event = Event(
        id=new_id("ev"),
        type=BOOKING_RATED,
        source="booking",
        occurred_at=now_iso(),
        data={
            "bookingId": booking_id,
            "ownerId": "o1",
            "listingId": "l9",
            "requesterId": "o17",
            "outcome": {"onTime": True, "quality": 5, "note": "Spot on", "tags": ["Clear handover"]},
            "at": now_iso(),
        },
    )
    handled = [app.state._portal.call(app.state.dispatcher.handle, event) for _ in range(3)]
    assert handled == [True, False, False]  # redeliveries do nothing

    after = client.get("/owners/o1").json()
    assert after["ratingSum"] == before["ratingSum"] + 5 and after["jobsDone"] == before["jobsDone"] + 1
    reviews = client.get("/listings/l9/reviews", params={"limit": 100}).json()["items"]
    mine = [r for r in reviews if r["id"] == f"rv_{booking_id}"]
    assert len(mine) == 1 and mine[0]["text"] == "Spot on" and mine[0]["authorId"] == "o17"


def test_only_owners_who_can_be_paid_are_offered(issuer, broker, tmp_path):
    """Deployed, a listing appears in search and candidates only once payments
    has said its owner can be paid, and disappears if that stops."""
    settings = Settings(
        app_env="test",
        database_url="sqlite+aiosqlite://",
        internal_token="i" * 40,
        require_payable_owners=True,
    )
    app = build_app(settings, media_store=DirectoryStore(str(tmp_path)), verifier=issuer.verifier())
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())

        c.portal.call(seed)
        body = {"origin": "Kreuzberg", "maxKm": 2000, "start": now_iso(), "until": _hours_from_now(24 * 30)}

        def offered():
            return {
                l["ownerId"] for l in c.post("/internal/candidates", json=body, headers=INTERNAL).json()["listings"]
            }

        def ready(owner, ok, as_of=None):
            data = {"ownerId": owner, "ready": ok, **({"asOf": as_of} if as_of else {})}
            e = Event(
                id=new_id("ev"),
                type=PAYOUTS_READY,
                source="payments",
                occurred_at=now_iso(),
                data=data,
            )
            c.portal.call(app.state.dispatcher.handle, e)

        assert offered() == set()
        assert c.get("/search", params={"q": "saw"}).json()["items"] == []
        ready("o1", True)
        assert offered() == {"o1"}
        assert c.get("/search", params={"q": "saw"}).json()["items"]
        ready("o1", False)
        assert offered() == set()
        # A stale "ready" that arrives late changes nothing.
        ready("o1", True, as_of="2020-01-01T00:00:00+00:00")
        assert offered() == set()


def test_deleting_an_account_forgets_what_is_theirs(client, app, issuer, bookings, broker):
    from cappy_common.events import PROFILE_DELETED

    _profile(client, issuer)
    h = issuer.headers("user-a")
    lid = client.post(
        "/listings", json={"listing": _window_listing(title="Unique lathe"), "slots": [_slot()]}, headers=h
    ).json()["listing"]["id"]
    client.put("/saved/l9", headers=h)
    export = client.get("/me/export", headers=h)
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    data = export.json()
    assert data["profile"]["name"] == "Ada Lovelace" and [l["id"] for l in data["listings"]] == [lid]
    assert data["saved"][0]["listingId"] == "l9" and data["bookings"]

    assert data["notifications"] == {}
    bookings.open["user-a"] = 1
    refused = client.delete("/me", headers=h)
    assert refused.status_code == 409, "not while a booking is open"
    assert refused.json()["error"]["code"] == "open_obligations"
    assert refused.json()["error"]["details"] == {
        "openBookings": 1,
        "pendingPayouts": 0,
        "until": "2026-10-01T10:00:00Z",
    }
    bookings.open["user-a"] = 0

    async def owed(person):  # noqa: ANN001
        return 1

    app.state.payments.pending_payouts = owed
    refused = client.delete("/me", headers=h)
    assert refused.status_code == 409 and refused.json()["error"]["details"]["pendingPayouts"] == 1, "nor money owed"
    del app.state.payments.pending_payouts
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get(f"/listings/{lid}").status_code == 404
    assert client.get("/search", params={"q": "unique lathe"}).json()["items"] == []
    assert client.get("/owners/user-a").status_code == 404, "gone from public pages"
    assert client.get("/saved", headers=h).status_code == 401, "the old session ended with the account"
    later = issuer.headers("user-a", iat=int(time.time()) + 1)
    assert client.get("/saved", headers=later).json()["items"] == []
    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(PROFILE_DELETED)] == ["user-a"]
    assert client.delete("/me", headers=ANON).status_code == 401


def test_the_handover_address_stays_private(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    body = {
        "listing": _window_listing(title="Private address drill"),
        "slots": [_slot()],
        "address": "Oranienstr. 5, Berlin",
    }
    lid = client.post("/listings", json=body, headers=h).json()["listing"]["id"]
    assert "Oranienstr" not in client.get(f"/listings/{lid}").text
    assert "Oranienstr" not in client.get("/search", params={"q": "private address"}).text
    assert client.get("/me/listings", headers=h).json()["items"][0]["address"] == "Oranienstr. 5, Berlin"
    assert client.get(f"/internal/listings/{lid}/handover").status_code == 403
    assert (
        client.get(f"/internal/listings/{lid}/handover", headers=INTERNAL).json()["address"] == "Oranienstr. 5, Berlin"
    )
    # Editing without mentioning the address leaves it; sending null clears it.
    client.put(f"/listings/{lid}", json={"listing": _window_listing(title="Private address drill 2")}, headers=h)
    assert (
        client.get(f"/internal/listings/{lid}/handover", headers=INTERNAL).json()["address"] == "Oranienstr. 5, Berlin"
    )
    client.put(f"/listings/{lid}", json={"listing": _window_listing(), "address": None}, headers=h)
    assert "address" not in client.get(f"/internal/listings/{lid}/handover", headers=INTERNAL).json()


def test_search_needs_three_characters(client):
    assert client.get("/search", params={"q": "ab"}).status_code == 422
    assert client.get("/search", params={"q": "saw"}).status_code == 200


def test_nothing_of_the_product_is_served_before_sign_in(client, issuer):
    """GOAL 13: signed-in only, enforced here, not just hidden in the app."""
    for path in ("/listings/l9", "/listings/l9/reviews", "/search?q=saw", "/owners/o1", "/districts", "/cities"):
        assert client.get(path, headers=ANON).status_code == 401, path
    signed_in = client.get("/listings/l9", headers=issuer.headers("user-a"))
    assert signed_in.status_code == 200 and signed_in.headers["cache-control"] == "private, no-store"
    # What law or the stores need stays public: reporting (DSA Art. 16).
    body = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "spam",
        "details": "Looks like spam to me",
        "email": "a@example.com",
    }
    assert client.post("/reports", json=body, headers=ANON).status_code == 201


def test_two_people_can_upload_the_same_picture(client, issuer):
    same = _jpeg_with_gps()
    for who, name in (("user-a", "Ada Lovelace"), ("user-b", "Bo Builder")):
        _profile(client, issuer, sub=who, name=name)
        h = issuer.headers(who)
        url = client.post("/uploads", files={"file": ("p.jpg", same, "image/jpeg")}, headers=h).json()["url"]
        body = {"listing": _window_listing(photos=[url]), "slots": [_slot()]}
        assert client.post("/listings", json=body, headers=h).status_code == 201, who


def test_editing_a_listing_keeps_the_photos_it_already_shows(client, issuer):
    """Seeded listings show photos from elsewhere; resending them on an edit is
    fine, adding someone else's is not."""
    from cappy_common.fixtures import build_world

    l9 = next(l for l in build_world().listings if l.id == "l9")
    h = issuer.headers("o1")
    body = l9.model_dump(mode="json", by_alias=True, exclude={"id", "owner_id"})
    assert (
        client.put("/listings/l9", json={"listing": {**body, "title": "Festool, edited"}}, headers=h).status_code == 200
    )
    stranger = {**body, "photos": [*body["photos"], "https://images.unsplash.com/other.jpg"]}
    assert client.put("/listings/l9", json={"listing": stranger}, headers=h).status_code == 422


def test_the_listings_kill_switch(issuer, broker, tmp_path, bookings):
    settings = Settings(
        app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40, accepting_listings=False
    )
    app = build_app(settings, media_store=DirectoryStore(str(tmp_path)), bookings=bookings, verifier=issuer.verifier())
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())

        c.portal.call(seed)
        _profile(c, issuer)
        r = c.post("/listings", json={"listing": _window_listing()}, headers=issuer.headers("user-a"))
        assert r.status_code == 503


def test_upload_quota(issuer, broker, tmp_path, bookings):
    settings = Settings(
        app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40, media_daily_quota=2
    )
    app = build_app(settings, media_store=DirectoryStore(str(tmp_path)), bookings=bookings, verifier=issuer.verifier())
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:
        h = issuer.headers("user-a")
        codes = [
            c.post("/uploads", files={"file": ("p.png", _png(shade), "image/png")}, headers=h).status_code
            for shade in (0, 120, 250)
        ]
        assert codes == [201, 201, 429]
        # Once over the quota even a repeat is refused: the check comes first.
        assert c.post("/uploads", files={"file": ("p.png", _png(0), "image/png")}, headers=h).status_code == 429


def test_unused_uploads_are_swept_and_shared_ones_kept(client, app, issuer, tmp_path):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from catalog.jobs import sweep_orphans_once
    from catalog.tables import MediaRow

    same = _jpeg_with_gps()
    urls = {}
    for who, name in (("user-a", "Ada Lovelace"), ("user-b", "Bo Builder")):
        _profile(client, issuer, sub=who, name=name)
        urls[who] = client.post(
            "/uploads", files={"file": ("p.jpg", same, "image/jpeg")}, headers=issuer.headers(who)
        ).json()["url"]
    # user-b uses it on a listing; user-a never does.
    body = {"listing": _window_listing(photos=[urls["user-b"]]), "slots": [_slot()]}
    assert client.post("/listings", json=body, headers=issuer.headers("user-b")).status_code == 201
    lonely = client.post(
        "/uploads", files={"file": ("q.png", _png(), "image/png")}, headers=issuer.headers("user-a")
    ).json()["url"]

    async def age():
        async with app.state.db.transaction() as s:
            await s.execute(update(MediaRow).values(created_at=datetime.now(UTC) - timedelta(days=2)))

    _run(app, age)
    assert _run(app, lambda: sweep_orphans_once(app)) == 1, "only the photo nobody holds is deleted"
    assert client.get(lonely).status_code == 404
    assert client.get(urls["user-b"]).status_code == 200


def test_reviewers_are_shown_by_first_name_and_initial():
    from catalog.handlers import short_name

    assert short_name("Ada Lovelace") == "Ada L."
    assert short_name("Jean Claude van Damme") == "Jean D."
    assert short_name("Cher") == "Cher"


def _staff(issuer):
    return {"Authorization": f"Bearer {issuer.token('staff-1', **{'cognito:groups': ['admin']})}"}


def test_anyone_can_report_and_staff_decide_with_reasons(client, app, issuer, broker):
    from cappy_common.events import MODERATION_DECISION, REPORT_RECEIVED

    body = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "fraud",
        "details": "The photos are stolen from a shop",
    }
    assert client.post("/reports", json=body, headers=ANON).status_code == 422, "anonymous needs an email"
    anon = client.post("/reports", json={**body, "email": "neighbour@example.com"}, headers=ANON).json()
    mine = client.post("/reports", json={**body, "reason": "spam"}, headers=issuer.headers("user-a")).json()
    assert anon["status"] == "open" and mine["id"] != anon["id"]

    assert client.get("/admin/reports", headers=issuer.headers("user-a")).status_code == 403, "staff only"
    queue = client.get("/admin/reports", headers=_staff(issuer)).json()["items"]
    assert [r["id"] for r in queue] == [anon["id"], mine["id"]], "oldest first"
    title = client.get("/listings/l9").json()["listing"]["title"]
    assert queue[0]["targetLabel"] == title, "named, not a raw id (V7-19)"

    short = {"action": "take_down", "statement": "no"}
    assert client.post(f"/admin/reports/{anon['id']}/decide", json=short, headers=_staff(issuer)).status_code == 422
    why = {"action": "take_down", "statement": "The listing uses photos taken from another business (terms §4)."}
    assert (
        client.post(f"/admin/reports/{anon['id']}/decide", json=why, headers=_staff(issuer)).json()["status"]
        == "actioned"
    )
    assert client.post(f"/admin/reports/{anon['id']}/decide", json=why, headers=_staff(issuer)).status_code == 409
    assert client.get("/listings/l9").status_code == 404
    assert all(v["listing"]["id"] != "l9" for v in client.get("/search", params={"q": "festool"}).json()["items"])
    # The owner cannot simply bring it back.
    assert client.post("/listings/l9/resume", headers=issuer.headers("o1")).status_code == 404

    dismiss = {"action": "dismiss", "statement": "Already handled under the earlier report about this listing."}
    client.post(f"/admin/reports/{mine['id']}/decide", json=dismiss, headers=_staff(issuer))
    flush(app)
    assert len(broker.of_type(REPORT_RECEIVED)) == 2
    decisions = broker.of_type(MODERATION_DECISION)
    assert decisions[0].data["affectedId"] == "o1" and decisions[0].data["reporterEmail"] == "neighbour@example.com"
    assert decisions[1].data["affectedId"] is None, "nobody is told they were cleared of what they never heard of"
    audit = client.get("/admin/audit", headers=_staff(issuer)).json()["items"]
    assert [a["action"] for a in audit] == ["dismiss", "take_down"] and audit[1]["actorId"] == "staff-1"


def test_a_suspended_owner_disappears_and_cannot_list(client, app, issuer, broker):
    from cappy_common.events import OWNER_SUSPENDED

    why = {"statement": "Repeated fraudulent listings after two warnings (terms §9)."}
    assert client.post("/admin/owners/o1/suspend", json=why, headers=_staff(issuer)).status_code == 204
    assert all(v["listing"]["ownerId"] != "o1" for v in client.get("/search", params={"q": "saw"}).json()["items"])
    r = client.post("/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=issuer.headers("o1"))
    assert r.status_code == 403
    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(OWNER_SUSPENDED)] == ["o1"]
    client.post("/admin/owners/o1/reinstate", json=why, headers=_staff(issuer))
    assert (
        client.post(
            "/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=issuer.headers("o1")
        ).status_code
        == 201
    )


def test_a_new_owner_s_expensive_listing_waits_for_a_staff_check(client, app, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    pricey = client.post(
        "/listings",
        json={"listing": _window_listing(title="Laser cutter bargain", ratePerHour=25_000), "slots": [_slot()]},
        headers=h,
    ).json()
    assert pricey["held"] is True
    lid = pricey["listing"]["id"]
    assert client.get(f"/listings/{lid}").status_code == 404, "nobody sees it yet"
    mine = client.get("/me/listings", headers=h).json()["items"]
    assert [(v["listing"]["id"], v.get("held")) for v in mine] == [(lid, True)], "the owner does"
    assert client.get(f"/listings/{lid}", headers=h).status_code == 200, "and can open it (FL-6)"
    cheap = client.post("/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=h).json()
    assert cheap["held"] is False
    assert [x["id"] for x in client.get("/admin/listings/held", headers=_staff(issuer)).json()] == [lid]
    assert client.post(f"/admin/listings/{lid}/approve", headers=_staff(issuer)).status_code == 204
    assert client.get(f"/listings/{lid}").status_code == 200


def test_new_listings_per_day_are_limited(issuer, broker, tmp_path, bookings):
    settings = Settings(
        app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40, max_listings_per_day=2
    )
    app = build_app(settings, media_store=DirectoryStore(str(tmp_path)), bookings=bookings, verifier=issuer.verifier())
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())

        c.portal.call(seed)
        _profile(c, issuer)
        codes = [
            c.post("/listings", json={"listing": _window_listing()}, headers=issuer.headers("user-a")).status_code
            for _ in range(3)
        ]
        assert codes == [201, 201, 429]


def test_renter_ratings_build_a_renter_record(client, app, issuer):
    from cappy_common.events import RENTER_RATED

    _profile(client, issuer)
    for q in (4, 5):
        e = Event(
            id=new_id("ev"),
            type=RENTER_RATED,
            source="booking",
            occurred_at=now_iso(),
            data={"bookingId": new_id("bk"), "renterId": "user-a", "ownerId": "o1", "quality": q},
        )
        _run(app, lambda e=e: app.state.dispatcher.handle(e))
    owner = client.get("/owners/user-a").json()
    assert (owner["renterRatingSum"], owner["renterJobs"]) == (9, 2)


def test_hand_over_instructions_are_never_public(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    body = {"listing": _window_listing(title="Secret door drill", instructions="Key under the blue pot, code 4471")}
    lid = client.post("/listings", json=body, headers=h).json()["listing"]["id"]
    assert "4471" not in client.get(f"/listings/{lid}").text
    assert "4471" not in client.get("/search", params={"q": "secret door"}).text
    assert "4471" in client.get("/me/listings", headers=h).text, "the owner sees their own"
    assert client.get(f"/internal/listings/{lid}/handover", headers=INTERNAL).json()["instructions"].endswith("4471")


def test_raising_the_price_later_still_waits_for_review(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    lid = client.post("/listings", json={"listing": _window_listing(), "slots": [_slot()]}, headers=h).json()[
        "listing"
    ]["id"]
    assert client.get(f"/listings/{lid}").status_code == 200
    client.put(f"/listings/{lid}", json={"listing": _window_listing(ratePerHour=50_000)}, headers=h)
    assert client.get(f"/listings/{lid}").status_code == 404, "held for a staff check"
    assert [x["id"] for x in client.get("/admin/listings/held", headers=_staff(issuer)).json()] == [lid]


def test_reports_cannot_be_used_to_flood_an_inbox(client, issuer):
    body = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "spam",
        "details": "Looks like spam to me",
        "email": "victim@example.com",
    }
    answers = [client.post("/reports", json=body, headers=ANON) for _ in range(4)]
    assert [a.status_code for a in answers] == [201, 201, 201, 429]
    assert answers[-1].json()["error"]["code"] == "reports_today", "a code the app can translate (V7-18)"
    mine = client.post("/reports", json={**body, "email": "elsewhere@example.com"}, headers=issuer.headers("user-a"))
    assert mine.status_code == 201


def test_anonymous_reports_cannot_crowd_out_members(client, issuer):
    from catalog.moderation import ANONYMOUS_PER_TARGET

    body = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "spam",
        "details": "Looks like spam to me",
    }
    codes = [
        client.post("/reports", json={**body, "email": f"a{i}@example.com"}, headers=ANON).status_code
        for i in range(ANONYMOUS_PER_TARGET + 1)
    ]
    assert codes[-1] == 429 and set(codes[:-1]) == {201}
    # A member's report of the same thing still gets through (P-7).
    assert client.post("/reports", json=body, headers=issuer.headers("user-a")).status_code == 201


def test_taking_down_declines_requests_and_owners_manage_held_listings(client, app, issuer, broker):
    why = {"statement": "Counterfeit machinery offered under a known brand (terms 4)."}
    assert client.post("/admin/listings/l9/take-down", json=why, headers=_staff(issuer)).status_code == 204
    flush(app)
    assert any(
        e.data == {"listingId": "l9", "change": "removed", "by": "staff"} for e in broker.of_type(LISTING_CHANGED)
    )
    _profile(client, issuer)
    h = issuer.headers("user-a")
    lid = client.post("/listings", json={"listing": _window_listing(ratePerHour=90_000)}, headers=h).json()["listing"][
        "id"
    ]
    assert (
        client.put(
            f"/listings/{lid}", json={"listing": _window_listing(ratePerHour=80_000, title="Fixed typo")}, headers=h
        ).status_code
        == 200
    )
    assert client.delete(f"/listings/{lid}", headers=h).status_code == 204


def test_staff_preview_any_listing_with_why_it_is_hidden(client, app, issuer):
    """V5-4: approvals are not blind; guests still get 404."""
    _profile(client, issuer)
    h = issuer.headers("user-a")
    lid = client.post("/listings", json={"listing": _window_listing(ratePerHour=90_000)}, headers=h).json()["listing"][
        "id"
    ]
    assert client.get(f"/listings/{lid}", headers=issuer.headers("someone")).status_code == 404
    assert client.get(f"/admin/listings/{lid}", headers=issuer.headers("someone")).status_code == 403
    seen = client.get(f"/admin/listings/{lid}", headers=_staff(issuer)).json()
    assert seen["state"] == "held" and seen["heldAt"] and seen["detail"]["listing"]["id"] == lid
    assert seen["detail"]["owner"]["id"] == "user-a"
    # V6-2: staff also see where it is and what renters said.
    assert seen["handover"]["instructions"] == "Ring the bell", "the hand-over, for staff only"
    assert seen["reviews"] == []
    assert client.get("/admin/listings/l9", headers=_staff(issuer)).json()["reviews"], "l9 has reviews"
    why = {"statement": "Counterfeit machinery (terms 4)."}
    client.post("/admin/listings/l9/take-down", json=why, headers=_staff(issuer))
    assert client.get("/admin/listings/l9", headers=_staff(issuer)).json()["state"] == "taken_down"
    assert client.get("/admin/listings/held", headers=_staff(issuer)).status_code == 200, "the list is not shadowed"


def test_a_take_down_purges_the_listing_s_photos_from_the_cdn(issuer, broker, tmp_path, bookings):
    """F-4: through the Cdn seam; the photos are what the edge caches."""
    from catalog.cdn import Cdn
    from catalog.tables import ListingRow

    class Recorded(Cdn):
        purged: list[list[str]] = []

        async def purge(self, paths):  # noqa: ANN001
            self.purged.append(paths)

    cdn = Recorded()
    settings = Settings(app_env="test", database_url="sqlite+aiosqlite://", internal_token="i" * 40)
    app = build_app(
        settings, media_store=DirectoryStore(str(tmp_path)), bookings=bookings, cdn=cdn, verifier=issuer.verifier()
    )
    with TestClient(app, headers=issuer.headers("viewer-1")) as c:

        async def seed():
            async with app.state.db.transaction() as s:
                await CatalogRepository(s).load_seed(build_world())
                row = await s.get(ListingRow, "l9")
                row.photos = [f"{settings.media_public_base}/media/{'a' * 40}.webp", "https://images.example/x.jpg"]

        c.portal.call(seed)
        why = {"statement": "Counterfeit machinery offered under a known brand (terms 4)."}
        assert c.post("/admin/listings/l9/take-down", json=why, headers=_staff(issuer)).status_code == 204
    assert cdn.purged == [[f"/media/{'a' * 40}.webp"]], "our photos only; a foreign URL is not ours to purge"


def test_a_retried_listing_create_makes_one_listing(client, issuer):
    _profile(client, issuer)
    h = {**issuer.headers("user-a"), "Idempotency-Key": "k-listing-1"}
    body = {"listing": _window_listing(title="Retried lathe"), "slots": [_slot()]}
    first, again = client.post("/listings", json=body, headers=h), client.post("/listings", json=body, headers=h)
    assert first.status_code == again.status_code == 201
    assert first.json()["listing"]["id"] == again.json()["listing"]["id"], "the lost answer, not a second listing"
    other = {"listing": _window_listing(title="Another lathe"), "slots": [_slot()]}
    assert client.post("/listings", json=other, headers=h).status_code == 422, "same key, different request"
    # Keys are per person: someone else's identical key is their own.
    _profile(client, issuer, sub="user-b", name="Bea")
    theirs = client.post("/listings", json=body, headers={**issuer.headers("user-b"), "Idempotency-Key": "k-listing-1"})
    assert theirs.status_code == 201 and theirs.json()["listing"]["id"] != first.json()["listing"]["id"]


def test_a_retried_report_files_one_report(client, issuer):
    h = {**issuer.headers("user-a"), "Idempotency-Key": "k-report-1"}
    body = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "spam",
        "details": "Looks like spam to me",
    }
    first, again = client.post("/reports", json=body, headers=h), client.post("/reports", json=body, headers=h)
    assert first.status_code == again.status_code == 201 and first.json()["id"] == again.json()["id"]


# --- traders, the minimum age, reliability, statements of reasons, DSA numbers ---------
# (S-4, S-5, S-13, S-17, S-18, S-30)

PERSON = {"name": "Ada Lovelace", "kind": "person", "district": "Kreuzberg"}
TRADER = {"legalName": "Werkstatt Lovelace GmbH", "address": "Oranienstraße 1, 10999 Berlin"}


def _event(app, type_: str, data: dict) -> None:
    from cappy_common.events import Event

    e = Event(id=new_id("ev"), type=type_, source="booking", occurred_at=now_iso(), data=data)
    app.state._portal.call(app.state.dispatcher.handle, e)


def test_a_new_profile_needs_the_age_confirmation(client, issuer):
    h = issuer.headers("teen-1")
    r = client.put("/me", json=PERSON, headers=h)
    assert r.status_code == 422 and "18" in r.json()["error"]["message"]
    assert client.put("/me", json={**PERSON, "adult": False}, headers=h).status_code == 422
    assert client.put("/me", json={**PERSON, "adult": True}, headers=h).status_code == 200
    # Once confirmed, later edits need not say it again.
    assert client.put("/me", json={**PERSON, "name": "Ada L."}, headers=h).status_code == 200


def test_seeded_and_existing_profiles_are_grandfathered(client, issuer):
    assert client.put("/me", json={**PERSON, "name": "Nadia B."}, headers=issuer.headers("o1")).status_code == 200


def test_a_business_says_who_it_is_and_renters_see_it(client, issuer):
    h = issuer.headers("trader-1")
    base = {**PERSON, "adult": True, "kind": "business"}
    assert client.put("/me", json=base, headers=h).status_code == 422, "legal name and address required"
    bad = {**base, "business": {**TRADER, "vatId": "DE12345"}}
    assert client.put("/me", json=bad, headers=h).status_code == 422
    good = {**base, "business": {**TRADER, "registerNumber": "HRB 12345 B", "vatId": "de 123 456 789"}}
    owner = client.put("/me", json=good, headers=h).json()
    assert owner["business"] == {**TRADER, "registerNumber": "HRB 12345 B", "vatId": "DE123456789"}
    assert client.get("/owners/trader-1", headers=issuer.headers("viewer-2")).json()["business"]["legalName"]
    # Other EU VAT IDs are only checked loosely.
    fr = {**base, "business": {**TRADER, "vatId": "FR12345678901"}}
    assert client.put("/me", json=fr, headers=h).status_code == 200
    # Becoming a person again drops the trader details from every answer.
    person = client.put("/me", json={**PERSON}, headers=h).json()
    assert person.get("business") is None


def test_a_form_hears_every_problem_at_once(client, issuer):
    # V4-20: a short legal name, a short address and a bad VAT ID, one answer.
    body = {**PERSON, "adult": True, "kind": "business", "business": {"legalName": "A", "address": "x", "vatId": "DE1"}}
    err = client.put("/me", json=body, headers=issuer.headers("t-2")).json()["error"]
    assert err["code"] == "invalid" and err["message"]  # older clients still get words
    assert {f["field"] for f in err["fields"]} == {"business.legalName", "business.address", "business.vatId"}
    assert "VAT ID" in next(f["message"] for f in err["fields"] if f["field"] == "business.vatId")
    missing = client.put("/me", json={**PERSON, "adult": True, "kind": "business"}, headers=issuer.headers("t-2"))
    assert [f["field"] for f in missing.json()["error"]["fields"]] == ["business"]


def test_a_person_never_shows_an_address(client, issuer):
    # Even if one is sent, a person has no trader block.
    body = {**PERSON, "adult": True, "business": TRADER}
    assert client.put("/me", json=body, headers=issuer.headers("p-1")).json().get("business") is None


def test_owner_reliability_comes_from_booking_and_shows_on_the_owner(client, app):
    from cappy_common.events import OWNER_RELIABILITY

    assert client.get("/owners/o1").json().get("cancellationRate") is None
    _event(app, OWNER_RELIABILITY, {"ownerId": "o1", "rate": 0.2, "bookings": 10, "failures": 2})
    assert client.get("/owners/o1").json()["cancellationRate"] == 0.2
    _event(app, OWNER_RELIABILITY, {"ownerId": "o1", "rate": None, "bookings": 3, "failures": 1})
    assert client.get("/owners/o1").json().get("cancellationRate") is None


def test_response_time_is_what_booking_measured_and_nothing_else(client, app):
    """H-1: the seed's figure stays until booking has measured one; a
    response event never touches the cancellation rate, nor the reverse."""
    from cappy_common.events import OWNER_RELIABILITY

    _event(app, OWNER_RELIABILITY, {"ownerId": "o1", "rate": 0.2, "bookings": 10, "failures": 2})
    _event(app, OWNER_RELIABILITY, {"ownerId": "o1", "responseMins": 42, "responseRate": 0.9})
    o = client.get("/owners/o1").json()
    assert (o["responseMins"], o["responseRate"], o["cancellationRate"]) == (42, 0.9, 0.2)
    _event(app, OWNER_RELIABILITY, {"ownerId": "o1", "responseMins": None, "responseRate": None})
    o = client.get("/owners/o1").json()
    assert o.get("responseMins") is None and o.get("responseRate") is None and o["cancellationRate"] == 0.2


def test_flags_join_the_queue_once_while_open(client, app, issuer):
    from cappy_common.events import PERSON_FLAGGED

    flagged = {"personId": "o1", "reason": "reliability", "details": "Cancelled 3 accepted bookings in 30 days."}
    _event(app, PERSON_FLAGGED, flagged)
    _event(app, PERSON_FLAGGED, flagged)
    _event(app, PERSON_FLAGGED, {**flagged, "reason": "linked_to_suspended", "details": "Shares a card."})
    queue = client.get("/admin/reports", headers=_staff(issuer)).json()["items"]
    mine = [(r["reason"], r["targetId"]) for r in queue if r["targetId"] == "o1"]
    assert sorted(mine) == [("linked_to_suspended", "o1"), ("reliability", "o1")]


def test_reports_need_good_faith(client):
    body = {"targetType": "listing", "targetId": "l9", "reason": "spam", "details": "Looks like spam to me"}
    r = client.post("/reports", json={**body, "email": "a@example.com"}, headers=ANON)
    assert r.status_code == 422 and "accurate" in r.json()["error"]["message"]
    ok = {**body, "email": "a@example.com", "goodFaith": True}
    assert client.post("/reports", json=ok, headers=ANON).status_code == 201


def test_a_restriction_comes_with_a_structured_statement_of_reasons(client, app, issuer, broker):
    from cappy_common.events import MODERATION_DECISION

    body = {"goodFaith": True, "targetType": "listing", "targetId": "l9", "reason": "illegal"}
    report = client.post("/reports", json={**body, "details": "This is a stolen machine"}).json()
    decision = {
        "action": "take_down",
        "statement": "The serial number matches a machine reported stolen to the police.",
        "ground": "law",
        "clause": "§ 259 StGB (handling stolen goods)",
    }
    done = client.post(f"/admin/reports/{report['id']}/decide", json=decision, headers=_staff(issuer)).json()
    sor = done["statementOfReasons"]
    assert sor["restriction"].startswith("The listing was removed")
    assert sor["facts"] == decision["statement"] and sor["ground"] == "law" and sor["automated"] is False
    assert sor["clause"] == "§ 259 StGB (handling stolen goods)" and "6 months" in sor["redress"]
    flush(app)
    event = broker.of_type(MODERATION_DECISION)[-1]
    assert event.data["statementOfReasons"] == sor

    other = client.post("/reports", json={**body, "details": "Spam spam spam", "reason": "spam"}).json()
    dismissed = client.post(
        f"/admin/reports/{other['id']}/decide",
        json={"action": "dismiss", "statement": "Nothing wrong with this listing on a second look."},
        headers=_staff(issuer),
    ).json()
    assert dismissed.get("statementOfReasons") is None, "a dismissal restricts nobody"


def test_staff_take_downs_default_to_the_terms(client, issuer):
    r = client.post(
        "/admin/listings/l9/take-down",
        json={"statement": "Listing offers a service our terms do not allow."},
        headers=_staff(issuer),
    )
    assert r.status_code == 204
    audit = client.get("/admin/audit", headers=_staff(issuer)).json()["items"]
    assert audit[0]["action"] == "take_down"


def test_other_services_staff_actions_join_the_one_audit_log(client, app, issuer):
    # H-7: booking announces a resolution and a case read; catalog keeps both.
    from cappy_common.events import STAFF_ACTION, Event
    from cappy_common.ids import new_id
    from cappy_common.timeutil import now_iso

    def action(what: str, actor: str, at: str) -> Event:
        data = {
            "actorId": actor,
            "action": what,
            "targetType": "booking",
            "targetId": "bk_1",
            "personId": None,
            "reason": f"{what} of bk_1",
            "requestId": "req-42",
            "service": "booking",
            "at": at,
        }
        return Event(id=new_id("ev"), type=STAFF_ACTION, source="booking", occurred_at=now_iso(), data=data)

    resolved = action("resolve_dispute", "staff-1", "2026-09-27T10:00:00Z")
    read = action("read_case", "staff-2", "2026-09-27T10:05:00Z")
    for e in (resolved, read, resolved):  # redelivered: logged once
        app.state._portal.call(app.state.dispatcher.handle, e)
    staff = _staff(issuer)
    page = client.get("/admin/audit", params={"target": "bk_1"}, headers=staff).json()
    assert [a["action"] for a in page["items"]] == ["read_case", "resolve_dispute"]
    assert page["items"][1]["requestId"] == "req-42" and page["items"][1]["actorId"] == "staff-1"
    mine = client.get("/admin/audit", params={"actor": "staff-2"}, headers=staff).json()["items"]
    assert [a["action"] for a in mine] == ["read_case"]
    first = client.get("/admin/audit", params={"target": "bk_1", "limit": 1}, headers=staff).json()
    rest = client.get("/admin/audit", params={"target": "bk_1", "cursor": first["nextCursor"]}, headers=staff).json()
    assert [a["action"] for a in first["items"] + rest["items"]] == ["read_case", "resolve_dispute"]
    assert client.get("/admin/audit", headers=issuer.headers("o1")).status_code == 403


def test_audit_lines_carry_their_facts_and_a_repeated_read_is_one(client, app, issuer):
    # V6-9: the console renders amount, reason and listing in words; a case
    # opened twice within the minute is one line.
    from cappy_common.events import STAFF_ACTION, Event
    from cappy_common.ids import new_id
    from cappy_common.timeutil import now_iso

    def line(action: str, **extra) -> Event:
        data = {
            "actorId": "staff-1",
            "action": action,
            "targetType": "booking",
            "targetId": "bk_9",
            "reason": "",
            "at": "2026-09-27T10:00:00Z",
            **extra,
        }
        return Event(id=new_id("ev"), type=STAFF_ACTION, source="booking", occurred_at=now_iso(), data=data)

    facts = {
        "amount": 1500,
        "currency": "EUR",
        "reasonCode": "not_as_described",
        "outcome": "refund_buyer",
        "bookingId": "bk_9",
        "listingTitle": "Table saw",
    }
    events = [
        line("resolve_dispute", reason="The motor fault is on video.", details=facts),
        line("read_case", dedupe="staff-1:read_case:bk_9:202609271000"),
        line("read_case", dedupe="staff-1:read_case:bk_9:202609271000"),
        # V7-13: the refetch after a decision, 23 s later across a calendar minute.
        line("read_case", at="2026-09-27T10:00:23Z", dedupe="staff-1:read_case:bk_9:202609271000"),
        line("read_case", at="2026-09-27T09:59:50Z", dedupe="staff-1:read_case:bk_9:202609270959"),
    ]
    for e in events:
        app.state._portal.call(app.state.dispatcher.handle, e)
    items = client.get("/admin/audit", params={"target": "bk_9"}, headers=_staff(issuer)).json()["items"]
    assert sorted(a["action"] for a in items) == ["read_case", "resolve_dispute"]
    later = line("read_case", at="2026-09-27T10:05:00Z", dedupe="staff-1:read_case:bk_9:202609271005")
    app.state._portal.call(app.state.dispatcher.handle, later)
    again = client.get("/admin/audit", params={"target": "bk_9"}, headers=_staff(issuer)).json()["items"]
    assert [a["action"] for a in again].count("read_case") == 2, "a real second opening, minutes later, counts"
    [resolved] = [a for a in items if a["action"] == "resolve_dispute"]
    assert resolved["statement"] == "The motor fault is on video." and resolved["details"] == facts


def test_districts_come_by_city(client):
    # V6-16: "Flon (Lausanne)" next to Lausanne, not scattered by name.
    ds = list(client.get("/districts").json().values())
    assert [(d["city"], d["name"]) for d in ds] == sorted((d["city"], d["name"]) for d in ds)


def test_dsa_numbers_for_a_month(client, issuer):
    from datetime import UTC, datetime

    month = datetime.now(UTC).strftime("%Y-%m")
    body = {"goodFaith": True, "targetType": "listing", "targetId": "l9", "details": "Stolen photos here"}
    a = client.post("/reports", json={**body, "reason": "fraud"}).json()
    client.post("/reports", json={**body, "reason": "spam"})
    client.post(
        f"/admin/reports/{a['id']}/decide",
        json={"action": "dismiss", "statement": "The photos are the owner's own, checked."},
        headers=_staff(issuer),
    )
    assert client.get(f"/admin/dsa-stats?month={month}").status_code == 403
    stats = client.get(f"/admin/dsa-stats?month={month}", headers=_staff(issuer)).json()
    assert stats["activeRecipients"] == 7
    assert stats["notices"]["byReason"] == {"fraud": 1, "spam": 1}
    assert stats["notices"]["byDecision"] == {"dismiss": 1, "open": 1}
    assert stats["medianHoursToDecision"] is not None
    assert client.get("/admin/dsa-stats?month=2026-13", headers=_staff(issuer)).status_code == 422


def test_signing_out_everywhere_ends_every_session_now(client, app, issuer, broker):
    import time

    from cappy_common.events import PERSON_SIGNED_OUT

    _profile(client, issuer)
    old = issuer.headers("user-a", iat=int(time.time()) - 60)
    assert client.get("/me", headers=old).status_code == 200
    assert client.post("/me/sign-out-everywhere", headers=old).status_code == 204
    # The token that asked, and every other issued before, stops counting here at once (P-24).
    r = client.get("/me", headers=old)
    assert r.status_code == 401 and r.json()["error"]["code"] == "token_expired"
    fresh = issuer.headers("user-a", iat=int(time.time()) + 1)
    assert client.get("/me", headers=fresh).status_code == 200
    # Matching, which has no database, asks catalog the same question.
    assert client.get("/internal/revocations/user-a").status_code == 403
    ended = client.get("/internal/revocations/user-a", headers=INTERNAL).json()["notBefore"]
    assert ended and time.time() - 60 < ended <= time.time()
    assert client.get("/internal/revocations/nobody", headers=INTERNAL).json() == {"notBefore": None}
    flush(app)
    # V4-24: a token issued in the same second as the sign-out is ended too
    # (whole-second iat against the exact revocation time).
    now = issuer.headers("user-b", iat=int(time.time()))
    _profile(client, issuer, sub="user-b")
    assert client.post("/me/sign-out-everywhere", headers=now).status_code == 204
    assert client.get("/me", headers=now).status_code == 401
    assert [e.data for e in broker.of_type(PERSON_SIGNED_OUT)] == [{"personId": "user-a"}]
    # A handful an hour, then a 429 (P-12).
    for _ in range(4):
        assert (
            client.post(
                "/me/sign-out-everywhere", headers=issuer.headers("user-a", iat=int(time.time()) + 2)
            ).status_code
            == 204
        )
    assert (
        client.post("/me/sign-out-everywhere", headers=issuer.headers("user-a", iat=int(time.time()) + 3)).status_code
        == 429
    )


def test_exports_are_limited_per_person(client, issuer):
    _profile(client, issuer, sub="user-x")
    h = issuer.headers("user-x")
    for _ in range(5):
        assert client.get("/me/export", headers=h).status_code == 200
    assert client.get("/me/export", headers=h).status_code == 429
    assert client.get("/me/export", headers=issuer.headers("user-y")).status_code == 200, "per person"


def test_hand_over_photos_are_never_public(client, issuer):
    h = issuer.headers("user-a")
    up = client.post("/uploads?purpose=evidence", files={"file": ("p.png", _png(40), "image/png")}, headers=h)
    assert up.status_code == 201
    ref = up.json()["url"]
    assert ref.startswith("evidence:"), "a reference, not a link"
    name = ref.removeprefix("evidence:")
    assert client.get(f"/media/{name}").status_code == 404, "not in the public store (P-27)"
    # Booking may read it, and keep it as this person's evidence; nobody else's.
    assert client.get(f"/internal/evidence/{name}", headers=INTERNAL).content[:4] == b"RIFF"
    ok = {"ownerId": "user-a", "urls": [ref]}
    assert client.post("/internal/media/evidence", json=ok, headers=INTERNAL).status_code == 204
    other = {"ownerId": "user-b", "urls": [ref]}
    assert client.post("/internal/media/evidence", json=other, headers=INTERNAL).status_code == 422
    public = client.post("/uploads", files={"file": ("p.png", _png(41), "image/png")}, headers=h).json()["url"]
    body = {"ownerId": "user-a", "urls": [public]}
    assert client.post("/internal/media/evidence", json=body, headers=INTERNAL).status_code == 422


def test_deletion_leaves_no_words_photos_or_reports_behind(client, app, issuer):
    """D-1..D-4: the listing's words and photos, every upload, the reports they
    filed and their stored answers go; rows others point at stay as shells."""
    from sqlalchemy import select

    from catalog.jobs import sweep_orphans_once
    from catalog.tables import IDEMPOTENCY, ListingRow, MediaRow, OwnerRow, ReportRow

    _profile(client, issuer)
    h = issuer.headers("user-a")
    photo = client.post("/uploads", files={"file": ("p.png", _png(), "image/png")}, headers=h).json()["url"]
    body = {
        "listing": _window_listing(
            title="Ada's lathe",
            instructions="Door code 4711",
            photos=[photo],
            extraLabel="Ada's own chisels",
            location={"lat": 52.49871, "lng": 13.41912},
            country="DE",
            postalCode="10999",
        ),
        "slots": [_slot()],
    }
    lid = client.post("/listings", json=body, headers={**h, "Idempotency-Key": "k-1"}).json()["listing"]["id"]
    report = {
        "goodFaith": True,
        "targetType": "listing",
        "targetId": "l9",
        "reason": "spam",
        "details": "Spam, clearly",
    }
    assert client.post("/reports", json=report, headers=h).status_code == 201
    assert [r["details"] for r in client.get("/me/export", headers=h).json()["reportsFiled"]] == ["Spam, clearly"]

    assert client.delete("/me", headers=h).status_code == 204

    async def left():
        async with app.state.db.transaction() as s:
            listing = await s.get(ListingRow, lid)
            owner = await s.get(OwnerRow, "user-a")
            reports = (await s.execute(select(ReportRow).where(ReportRow.details == "Spam, clearly"))).scalars().all()
            keys = (await s.execute(select(IDEMPOTENCY).where(IDEMPOTENCY.c.principal == "user-a"))).all()
            return listing, owner, reports, keys

    listing, owner, reports, keys = _run(app, left)
    assert (listing.title, listing.instructions, listing.photos) == ("Removed listing", "", [])
    assert (owner.name, owner.verified, owner.business) == ("Former member", False, None)
    assert reports == [] and keys == []
    assert listing.spec["extraLabel"] == "" and listing.spec["ratePerHour"] > 0, "the spec's words, not its numbers"
    assert "location" not in listing.spec and "postalCode" not in listing.spec, "the exact point is often a home"
    purged: list[str] = []

    class Edge:
        async def purge(self, paths):
            purged.extend(paths)

    app.state.cdn = Edge()
    assert _run(app, lambda: sweep_orphans_once(app)) == 1, "their photo goes on the next sweep"
    assert purged == [f"/media/{photo.rsplit('/', 1)[-1]}"], "and its copies leave the CDN"
    assert client.get(photo).status_code == 404

    async def media():
        async with app.state.db.transaction() as s:
            return (await s.execute(select(MediaRow).where(MediaRow.owner_id == "user-a"))).all()

    assert _run(app, media) == []


def test_a_reporter_is_forgotten_six_months_after_the_decision(client, app, issuer):
    from datetime import UTC, datetime, timedelta

    from catalog.jobs import forget_reporters_once
    from catalog.tables import ReportRow

    body = {"goodFaith": True, "targetType": "listing", "targetId": "l9", "reason": "spam", "details": "Spam again"}
    rid = client.post("/reports", json={**body, "email": "r@example.com"}, headers=ANON).json()["id"]

    async def decided(days):
        async with app.state.db.transaction() as s:
            row = await s.get(ReportRow, rid)
            row.decided_at = datetime.now(UTC) - timedelta(days=days)

    async def reporter():
        async with app.state.db.transaction() as s:
            row = await s.get(ReportRow, rid)
            return row.reporter_email, row.details

    _run(app, lambda: decided(100))
    assert _run(app, lambda: forget_reporters_once(app)) == 0
    _run(app, lambda: decided(200))
    assert _run(app, lambda: forget_reporters_once(app)) == 1
    assert _run(app, reporter) == (None, "[removed after the case closed]")


def test_reported_messages_and_reviews_are_removed_and_their_authors_suspendable(client, app, issuer, bookings, broker):
    """FL-7: remove_content takes the words out; suspend targets the author."""
    from cappy_common.events import MODERATION_DECISION, OWNER_SUSPENDED

    _profile(client, issuer, sub="user-b", name="Bo Builder")
    staff = _staff(issuer)

    def report(target_type, target_id):
        body = {"goodFaith": True, "targetType": target_type, "targetId": target_id, "reason": "offensive"}
        return client.post(
            "/reports", json={**body, "details": "Rude and abusive words"}, headers=issuer.headers("user-a")
        ).json()["id"]

    decision = {"statement": "Insults another member, against the rules for conduct."}
    rid = report("message", "msg_1")
    r = client.post(f"/admin/reports/{rid}/decide", json={**decision, "action": "remove_content"}, headers=staff)
    assert r.status_code == 200 and bookings.removed == ["msg_1"]
    assert r.json()["statementOfReasons"]["restriction"].startswith("The message or review was removed")
    rid = report("message", "msg_1")
    assert (
        client.post(f"/admin/reports/{rid}/decide", json={**decision, "action": "suspend"}, headers=staff).status_code
        == 200
    )
    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(OWNER_SUSPENDED)] == ["user-b"], "the author, not a listing owner"
    assert [e.data["affectedId"] for e in broker.of_type(MODERATION_DECISION)] == ["user-b", "user-b"]

    async def decisions_about_the_author():
        from catalog.repository import CatalogRepository

        async with app.state.db.session() as s:
            return (await CatalogRepository(s).export("user-b"))["moderationDecisionsAboutMe"]

    about = client.portal.call(decisions_about_the_author)
    assert [(d["action"], d["targetId"]) for d in about] == [("remove_content", "msg_1"), ("suspend", "msg_1")], (
        "decisions on their message are in their export"
    )
    rid = report("listing", "l9")
    bad = client.post(f"/admin/reports/{rid}/decide", json={**decision, "action": "remove_content"}, headers=staff)
    assert bad.status_code == 422, "a listing is taken down, not removed this way"


def test_signing_up_again_after_deletion_is_a_fresh_start(client, app, issuer):
    """FL-11: the old record never comes back, and onboarding does not loop."""
    from catalog.tables import OwnerRow

    _profile(client, issuer)
    h = issuer.headers("user-a")

    async def had_a_record():
        async with app.state.db.transaction() as s:
            row = await s.get(OwnerRow, "user-a")
            row.rating_sum, row.jobs_done, row.verified = 45, 9, True

    _run(app, had_a_record)
    assert client.delete("/me", headers=h).status_code == 204
    h = issuer.headers("user-a", iat=int(time.time()) + 1)  # signed up again, later
    assert client.get("/me", headers=h).json().get("owner") is None, "onboarding again"
    again = {"name": "Ada L", "kind": "person", "district": "Kreuzberg"}
    assert client.put("/me", json=again, headers=h).status_code == 422, "18+ asked again"
    fresh = client.put("/me", json={**again, "adult": True}, headers=h).json()
    assert (fresh["name"], fresh["jobsDone"], fresh["verified"]) == ("Ada L", 0, False)
    assert client.get("/me", headers=h).json()["owner"]["id"] == "user-a"


def test_markets_decide_where_people_join_list_and_in_which_currency(client, issuer):
    """M-2: only open markets, and a listing is priced in its market's money."""
    h = issuer.headers("zurich-1")
    person = {"adult": True, "name": "Heidi Muster", "kind": "person", "district": "Kreuzberg"}
    r = client.put("/me", json={**person, "country": "FR"}, headers=h)
    assert r.status_code == 422 and r.json()["error"]["code"] == "market_not_live", "France is planned"
    assert client.put("/me", json={**person, "country": "ZZ"}, headers=h).json()["error"]["code"] == "market_unknown"
    wrong = client.put("/me", json={**person, "country": "CH"}, headers=h).json()["error"]
    assert wrong["code"] == "district_not_in_country" and wrong["fields"][0]["field"] == "district"
    swiss = {**person, "country": "CH", "district": "Zürich-Kreis 5"}
    assert client.put("/me", json=swiss, headers=h).status_code == 200
    listing = {k: v for k, v in _window_listing().items() if k != "currency"}
    berlin = client.post("/listings", json={"listing": listing}, headers=h)
    assert berlin.json()["error"]["code"] == "district_not_in_country", "a Swiss owner lists in Switzerland"
    listing = {**listing, "district": "Zürich-Kreis 5"}
    created = client.post("/listings", json={"listing": listing}, headers=h)
    assert created.status_code == 201 and created.json()["listing"]["currency"] == "CHF", "the market's currency"
    r = client.post("/listings", json={"listing": {**listing, "currency": "EUR"}}, headers=h)
    assert r.json()["error"]["code"] == "currency_not_in_market"
    pricey = client.post("/listings", json={"listing": {**listing, "ratePerHour": 25_000}}, headers=h).json()
    assert pricey["held"] is True
    held = client.get("/admin/listings/held", headers=_staff(issuer)).json()
    assert [(x["id"], x["currency"]) for x in held] == [(pricey["listing"]["id"], "CHF")], "staff see francs"


# --- weekly schedules and listings that went dark (H-4) ---------------------------


WEEKDAYS = {"weekly": [{"day": d, "start": "09:00", "end": "17:00"} for d in range(1, 6)], "timeZone": "Europe/Berlin"}


def test_a_weekly_schedule_keeps_eight_weeks_of_windows_open(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    r = client.post("/listings", json={"listing": _window_listing(availability=WEEKDAYS)}, headers=h)
    assert r.status_code == 201, r.text
    created = r.json()
    lid, slots = created["listing"]["id"], created["slots"]
    assert created["listing"]["availability"]["timeZone"] == "Europe/Berlin"
    assert 38 <= len(slots) <= 41, "five weekdays for eight weeks"
    # Today's, if already under way, is cut short (V5-23); every other is whole.
    assert all(0 < s["hoursUsable"] <= 8 for s in slots) and sum(s["hoursUsable"] < 8 for s in slots) <= 1

    # A hand-made window stays; a new schedule replaces only what the old one made.
    extra = {"start": "2027-06-06T08:00:00Z", "end": "2027-06-06T10:00:00Z", "hoursUsable": 2}
    assert client.post(f"/listings/{lid}/slots", json=[extra], headers=h).status_code == 201
    weekends = {"weekly": [{"day": 6, "start": "10:00", "end": "14:00"}], "timeZone": "Europe/Berlin"}
    body = {"listing": {**_window_listing(availability=weekends)}}
    assert client.put(f"/listings/{lid}", json=body, headers=h).status_code == 200
    after = client.get(f"/listings/{lid}").json()["slots"]
    assert all(0 < s["hoursUsable"] <= 4 for s in after) and any(s["hoursUsable"] == 2 for s in after)

    # An edit that does not mention the schedule keeps it.
    assert client.put(f"/listings/{lid}", json={"listing": _window_listing()}, headers=h).status_code == 200
    assert client.get(f"/listings/{lid}").json()["listing"]["availability"] == weekends


def test_removing_a_hand_made_window_brings_the_weekly_hours_back(client, issuer):
    """V7-11: the seed's dated windows won over the demo schedule, and once
    taken away the day stayed empty until the next roll, up to a day later."""
    from datetime import UTC, datetime, timedelta
    from zoneinfo import ZoneInfo

    _profile(client, issuer)
    h = issuer.headers("user-a")
    berlin = ZoneInfo("Europe/Berlin")
    day = datetime.now(berlin).date() + timedelta(days=3)
    while day.isoweekday() > 5:
        day += timedelta(days=1)
    at = lambda hh: datetime(day.year, day.month, day.day, hh, tzinfo=berlin).astimezone(UTC).isoformat()  # noqa: E731
    extra = {"start": at(8), "end": at(12), "hoursUsable": 4}
    lid = client.post("/listings", json={"listing": _window_listing(), "slots": [extra]}, headers=h).json()["listing"][
        "id"
    ]
    body = {"listing": _window_listing(availability=WEEKDAYS)}
    assert client.put(f"/listings/{lid}", json=body, headers=h).status_code == 200
    on = lambda: [s for s in client.get(f"/listings/{lid}").json()["slots"] if s["start"][:10] == at(12)[:10]]  # noqa: E731
    [hand] = on()
    assert hand["hoursUsable"] == 4, "the dated window stood over the day's hours"
    assert client.delete(f"/listings/{lid}/slots/{hand['id']}", headers=h).status_code == 204
    [back] = on()
    assert back["hoursUsable"] == 8, "the weekday's 09:00-17:00 again, at once"


@pytest.mark.parametrize(
    "bad, message",
    [
        ({"weekly": [{"day": 1, "start": "17:00", "end": "09:00"}]}, "end after"),
        ({"weekly": [{"day": 8, "start": "09:00", "end": "17:00"}]}, "validate"),
        ({"weekly": [{"day": 1, "start": "09:00", "end": "17:00"}], "timeZone": "Mars/Olympus"}, "time zone"),
    ],
)
def test_a_schedule_is_checked(client, issuer, bad, message):
    _profile(client, issuer)
    r = client.post("/listings", json={"listing": _window_listing(availability=bad)}, headers=issuer.headers("user-a"))
    assert r.status_code == 422 and message in r.json()["error"]["message"], r.text


def test_the_schedule_rolls_on_and_an_idle_listing_tells_its_owner_once_a_week(client, app, issuer, broker):
    from datetime import UTC, datetime, timedelta

    from cappy_common.events import LISTING_IDLE
    from catalog.jobs import keep_schedules_once

    _profile(client, issuer)
    h = issuer.headers("user-a")
    dark = client.post("/listings", json={"listing": _window_listing()}, headers=h).json()["listing"]["id"]
    kept = client.post("/listings", json={"listing": _window_listing(availability=WEEKDAYS)}, headers=h).json()
    before = len(kept["slots"])

    later = datetime.now(UTC) + timedelta(days=9)
    assert app.state._portal.call(keep_schedules_once, app, later) > 0, "rolled on past the old horizon"
    assert len(client.get(f"/listings/{kept['listing']['id']}").json()["slots"]) > before - 10
    flush(app)
    told = [e.data for e in broker.of_type(LISTING_IDLE) if e.data["ownerId"] == "user-a"]
    assert [t["listingId"] for t in told] == [dark], "only the one with nothing free"
    app.state._portal.call(keep_schedules_once, app, later + timedelta(days=1))
    flush(app)
    assert len([e for e in broker.of_type(LISTING_IDLE) if e.data["ownerId"] == "user-a"]) == 1, "once a week"


def test_a_schedule_follows_the_clocks_going_back():
    """25 Oct 2026, Berlin: Sunday 09:00-17:00 is 07-15 UTC before, 08-16 UTC
    after, eight real hours both times."""
    from datetime import UTC, datetime

    from cappy_common.models import Availability
    from catalog.schedule import windows

    a = Availability.model_validate({"weekly": [{"day": 7, "start": "09:00", "end": "17:00"}]})
    got = windows(a, datetime(2026, 10, 17, tzinfo=UTC), datetime(2026, 10, 27, tzinfo=UTC))
    assert got == [
        (datetime(2026, 10, 18, 7, tzinfo=UTC), datetime(2026, 10, 18, 15, tzinfo=UTC)),
        (datetime(2026, 10, 25, 8, tzinfo=UTC), datetime(2026, 10, 25, 16, tzinfo=UTC)),
    ]
    late = Availability.model_validate({"weekly": [{"day": 6, "start": "20:00", "end": "24:00"}]})
    [(start, end)] = windows(late, datetime(2026, 10, 24, tzinfo=UTC), datetime(2026, 10, 25, 12, tzinfo=UTC))
    assert (end - start).total_seconds() == 4 * 3600, "midnight is the next day's, whatever the offset"


# --- where a listing is (M-5, M-6) ------------------------------------------------


def test_the_exact_point_waits_for_an_accepted_booking(client, issuer):
    _profile(client, issuer)
    h = issuer.headers("user-a")
    exact = {"lat": 52.49871, "lng": 13.41912}
    body = {"listing": _window_listing(location=exact, country="DE", postalCode="10999")}
    lid = client.post("/listings", json=body, headers=h).json()["listing"]["id"]

    public = client.get(f"/listings/{lid}").json()["listing"]
    assert public["location"] != exact and "postalCode" not in public
    assert (
        abs(public["location"]["lat"] - exact["lat"]) < 0.0045
        and abs(public["location"]["lng"] - exact["lng"]) < 0.0045
    )
    nearby = {"lat": 52.49872, "lng": 13.41913}
    other = client.post("/listings", json={"listing": _window_listing(location=nearby)}, headers=h).json()["listing"][
        "id"
    ]
    assert client.get(f"/listings/{other}").json()["listing"]["location"] == public["location"], (
        "same square, same answer"
    )

    [mine] = [v["listing"] for v in client.get("/me/listings", headers=h).json()["items"] if v["listing"]["id"] == lid]
    assert mine["location"] == exact and mine["postalCode"] == "10999", "the owner sees their own point"
    handover = client.get(f"/internal/listings/{lid}/handover", headers=INTERNAL).json()
    assert handover["location"] == exact and handover["postalCode"] == "10999"


def test_a_point_must_be_in_its_district(client, issuer):
    _profile(client, issuer)
    far = _window_listing(location={"lat": 48.137, "lng": 11.575})  # Munich, filed under Kreuzberg
    r = client.post("/listings", json={"listing": far}, headers=issuer.headers("user-a"))
    assert r.status_code == 422 and r.json()["error"]["code"] == "location_outside_district"
    bad = _window_listing(location={"lat": 95, "lng": 13})
    assert client.post("/listings", json={"listing": bad}, headers=issuer.headers("user-a")).status_code == 422


def test_the_demo_world_has_hand_over_addresses_and_trader_details(client, issuer):
    # V4-10: a seeded listing can be edited and booked without inventing an
    # address; V4-16: a seeded business names who the contract is with.
    [view] = [
        v
        for v in client.get("/me/listings", headers=issuer.headers("o1")).json()["items"]
        if v["listing"]["id"] == "l9"
    ]
    assert view["address"].endswith("12099 Berlin")
    business = client.get("/owners/b10").json()["business"]
    assert business["legalName"] == "Havelspedition GmbH" and business["vatId"].startswith("DE")
    public = client.get("/listings/l9").json()
    assert "Tempelhofer" not in str(public), "private until accepted"


def test_older_decisions_on_messages_find_their_author(client, app):
    # Recorded before decisions carried their person (747ed6b).
    from datetime import UTC, datetime

    from catalog.jobs import attribute_decisions_once
    from catalog.tables import ModerationActionRow

    async def old():
        async with app.state.db.transaction() as s:
            s.add(
                ModerationActionRow(
                    id="ma_old",
                    actor_id="staff",
                    action="remove_content",
                    target_type="message",
                    target_id="msg_1",
                    statement="s",
                    at=datetime.now(UTC),
                )
            )

    async def who():
        async with app.state.db.transaction() as s:
            return (await s.get(ModerationActionRow, "ma_old")).person_id

    _run(app, old)
    assert _run(app, lambda: attribute_decisions_once(app)) == 1
    assert _run(app, who) == "user-b"
    assert _run(app, lambda: attribute_decisions_once(app)) == 0, "done once"


def test_a_listing_outside_an_open_market_is_held_until_its_owner_moves_it(client, app, issuer):
    """V5-1: a listing published before places were checked (l62, a German
    owner's in Amsterdam) leaves search and detail; the owner sees why, staff
    cannot wave it through, and moving it into an open market brings it back."""
    from catalog.jobs import hold_out_of_market_once

    assert client.get("/listings/l62").status_code == 200
    assert _run(app, lambda: hold_out_of_market_once(app)) >= 1
    assert _run(app, lambda: hold_out_of_market_once(app)) == 0, "once is enough"
    assert client.get("/listings/l62").status_code == 404, "gone for everyone else"
    mine = client.get("/me/listings", params={"limit": 100}, headers=issuer.headers("n7")).json()["items"]
    view = next(v for v in mine if v["listing"]["id"] == "l62")
    assert view["held"] is True and view["holdReason"] == "market_not_live"
    held = client.get("/admin/listings/held", headers=_staff(issuer)).json()
    assert next(h for h in held if h["id"] == "l62")["holdReason"] == "market_not_live"
    refused = client.post("/admin/listings/l62/approve", headers=_staff(issuer))
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "market_not_live"
    moved = {**view["listing"], "district": "Kreuzberg", "country": None, "location": None}
    r = client.put("/listings/l62", json={"listing": moved}, headers=issuer.headers("n7"))
    assert r.status_code == 200, r.text
    assert client.get("/listings/l62").status_code == 200, "back once it is in an open market"


def test_a_weekly_window_already_under_way_is_cut_not_dropped():
    """V5-23: a Saturday 10:00-16:00 schedule seen at 10:34 still offers today
    from 10:45; the last quarter hour is not worth a window."""
    from datetime import UTC, datetime

    from cappy_common.models import Availability
    from catalog.schedule import windows

    sat = Availability.model_validate(
        {"weekly": [{"day": 6, "start": "10:00", "end": "16:00"}], "timeZone": "Europe/Berlin"}
    )
    night = datetime(2026, 9, 27, tzinfo=UTC)
    [(start, end)] = windows(sat, datetime(2026, 9, 26, 8, 34, 12, tzinfo=UTC), night)
    assert (start, end) == (datetime(2026, 9, 26, 8, 45, tzinfo=UTC), datetime(2026, 9, 26, 14, tzinfo=UTC))
    assert windows(sat, datetime(2026, 9, 26, 13, 50, tzinfo=UTC), night) == []
