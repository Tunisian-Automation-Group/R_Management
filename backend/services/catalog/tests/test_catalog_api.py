"""The catalog API: profiles, listings, photos, search, saved, candidates, ratings."""

from __future__ import annotations

import io

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
        return self.open.get(person, 0)

    async def all_for(self, person):  # noqa: ANN001
        return {"bookings": [{"id": "bk_1", "status": "completed"}], "messagesSent": [], "evidence": []}

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
    return build_app(
        settings, media_store=DirectoryStore(str(tmp_path / "media")), bookings=bookings, verifier=issuer.verifier()
    )


def _run(app, coro_fn):
    """Run a coroutine against the app's database, on the client's loop."""
    return app.state._portal.call(coro_fn)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
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
    r = client.put("/me", json={"name": name, "kind": "person", "district": "Kreuzberg"}, headers=issuer.headers(sub))
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
    assert client.get("/me").status_code == 401
    assert client.get("/me", headers={"X-Cappy-User": "o1"}).status_code == 401
    assert client.get("/saved").status_code == 401


def test_profile_is_created_once_and_a_record_cannot_be_declared(client, issuer, app, broker):
    me = client.get("/me", headers=issuer.headers("user-a")).json()
    assert me == {"id": "user-a", "homeDistrict": "Kreuzberg"}  # no owner yet

    owner = _profile(client, issuer)
    assert owner["id"] == "user-a" and owner["initials"] == "AL"
    assert (owner["ratingSum"], owner["jobsDone"], owner["verified"]) == (0, 0, False)

    again = client.put(
        "/me",
        json={"name": "Ada L", "kind": "business", "district": "Neukölln", "ratingSum": 500, "jobsDone": 100},
        headers=issuer.headers("user-a"),
    ).json()
    assert again["kind"] == "business" and again["district"] == "Neukölln"
    assert (again["ratingSum"], again["jobsDone"]) == (0, 0)

    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(PROFILE_CREATED)] == ["user-a"]


def test_profile_needs_a_known_district(client, issuer):
    r = client.put("/me", json={"name": "Ada", "kind": "person", "district": "Atlantis"}, headers=issuer.headers("u"))
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
    assert client.post("/uploads", files={"file": ("p.jpg", b"x", "image/jpeg")}).status_code == 401


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
    with TestClient(app) as c:

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

    bookings.open["user-a"] = 1
    assert client.delete("/me", headers=h).status_code == 409, "not while a booking is open"
    bookings.open["user-a"] = 0
    assert client.delete("/me", headers=h).status_code == 204
    assert client.get(f"/listings/{lid}").status_code == 404
    assert client.get("/search", params={"q": "unique lathe"}).json()["items"] == []
    assert client.get("/owners/user-a").status_code == 404, "gone from public pages"
    assert client.get("/saved", headers=h).json()["items"] == []
    flush(app)
    assert [e.data["ownerId"] for e in broker.of_type(PROFILE_DELETED)] == ["user-a"]
    assert client.delete("/me").status_code == 401


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


def test_public_reads_are_cacheable_at_the_edge_and_personal_ones_never(client, issuer):
    anon = client.get("/listings/l9")
    assert "s-maxage=30" in anon.headers["cache-control"] and "stale-if-error" in anon.headers["cache-control"]
    assert "s-maxage" in client.get("/search", params={"q": "saw"}).headers["cache-control"]
    mine = client.get("/listings/l9", headers=issuer.headers("user-a"))
    assert mine.headers["cache-control"] == "private, no-store"
    assert "cache-control" not in client.get("/listings/nope").headers, "errors are not cached"
    assert client.get("/saved", headers=issuer.headers("user-a")).headers["cache-control"] == "private, no-store"


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
    with TestClient(app) as c:

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
    with TestClient(app) as c:
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
        "targetType": "listing",
        "targetId": "l9",
        "reason": "fraud",
        "details": "The photos are stolen from a shop",
    }
    assert client.post("/reports", json=body).status_code == 422, "anonymous needs an email"
    anon = client.post("/reports", json={**body, "email": "neighbour@example.com"}).json()
    mine = client.post("/reports", json={**body, "reason": "spam"}, headers=issuer.headers("user-a")).json()
    assert anon["status"] == "open" and mine["id"] != anon["id"]

    assert client.get("/admin/reports", headers=issuer.headers("user-a")).status_code == 403, "staff only"
    queue = client.get("/admin/reports", headers=_staff(issuer)).json()["items"]
    assert [r["id"] for r in queue] == [anon["id"], mine["id"]], "oldest first"

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
    audit = client.get("/admin/audit", headers=_staff(issuer)).json()
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
    with TestClient(app) as c:

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
