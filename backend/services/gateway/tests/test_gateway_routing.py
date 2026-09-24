from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.main import build_app
from gateway.routing import BOOKING, CATALOG, MATCHING, resolve
from gateway.settings import Settings


@pytest.mark.parametrize(
    ("path", "upstream"),
    [
        ("/world", CATALOG),
        ("/me", CATALOG),
        ("/districts", CATALOG),
        ("/owners/o1", CATALOG),
        ("/owners/o1/outcomes", CATALOG),
        ("/listings", CATALOG),
        ("/listings/l9", CATALOG),
        ("/listings/l9/slots", CATALOG),
        ("/listings/l9/pause", CATALOG),
        ("/listings/l9/reviews", CATALOG),
        ("/reviews", CATALOG),
        ("/saved", CATALOG),
        ("/saved/l9", CATALOG),
        ("/uploads", CATALOG),
        ("/listings/l9/offers", MATCHING),
        ("/listings/l9/reviews/summary", MATCHING),
        ("/matches", MATCHING),
        ("/match-for-offer", MATCHING),
        ("/quote", MATCHING),
        ("/feasibility", MATCHING),
        ("/categories", MATCHING),
        ("/groups", MATCHING),
        ("/review-tags", MATCHING),
        ("/browse/spotlight", MATCHING),
        ("/districts/nearest", MATCHING),
        ("/bookings", BOOKING),
        ("/bookings/bk_1/accept", BOOKING),
        ("/nothing-here", None),
        ("/admin/reset", None),
    ],
)
def test_resolve(path, upstream):
    assert resolve(path) == upstream


def _fake_upstreams(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.method, request.url.path, dict(request.headers)))
        if request.url.path == "/healthz":
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/admin/reset":
            return httpx.Response(204)
        if request.url.host == "catalog" and request.url.path == "/world":
            return httpx.Response(200, json={"owners": [], "listings": [], "slots": [], "districts": {}, "reviews": []})
        if request.url.host == "catalog" and request.url.path == "/saved/l9":
            return httpx.Response(200, json=["l9"])
        if request.url.host == "catalog" and request.url.path.startswith("/media/"):
            return httpx.Response(
                200,
                content=b"PNG",
                headers={"content-type": "image/png", "cache-control": "public, max-age=31536000, immutable"},
            )
        if request.url.host == "booking" and request.url.path == "/bookings":
            body = json.loads(request.content or b"{}")
            return httpx.Response(201, json={"echo": body, "user": request.headers.get("x-cappy-user")})
        return httpx.Response(404, json={"error": {"code": "not_found", "message": "nope"}})

    return httpx.MockTransport(handler)


def _settings(**over) -> Settings:
    return Settings(
        catalog_url="http://catalog",
        matching_url="http://matching",
        booking_url="http://booking",
        cors_origins="",
        **over,
    )


@pytest.fixture()
def gateway():
    calls: list = []
    with TestClient(build_app(_settings(), transport=_fake_upstreams(calls))) as c:
        yield c, calls


def test_proxies_by_path_and_forwards_identity(gateway):
    c, calls = gateway
    assert c.get("/api/world").json() == {"owners": [], "listings": [], "slots": [], "districts": {}, "reviews": []}
    r = c.post("/api/bookings", json={"listingId": "l9"}, headers={"X-Cappy-User": "o5"})
    assert r.status_code == 201 and r.json() == {"echo": {"listingId": "l9"}, "user": "o5"}
    assert c.put("/api/saved/l9").json() == ["l9"]
    photo = c.get("/media/abc.png")
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/png"
    assert "immutable" in photo.headers["cache-control"]
    assert [(h, m, p) for h, m, p, _ in calls] == [
        ("catalog", "GET", "/world"),
        ("booking", "POST", "/bookings"),
        ("catalog", "PUT", "/saved/l9"),
        ("catalog", "GET", "/media/abc.png"),
    ]


def test_index_points_somewhere_useful(gateway):
    c, _ = gateway
    body = c.get("/").json()
    assert body["health"] == "/api/health" and body["docs"] == "/docs"


def test_unknown_and_upstream_errors_keep_shape(gateway):
    c, _ = gateway
    assert c.get("/api/whatever").status_code == 404
    r = c.get("/api/listings/l99")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_health_and_reset_fan_out(gateway):
    c, calls = gateway
    h = c.get("/api/health").json()
    assert h == {"ok": True, "services": {"catalog": True, "matching": True, "booking": True}}
    calls.clear()
    assert c.post("/api/admin/reset").status_code == 204
    assert [(h, p) for h, _, p, _ in calls] == [("booking", "/admin/reset"), ("catalog", "/admin/reset")]


def test_serves_the_web_app_from_the_same_origin(tmp_path):
    """The website and the installed PWA come from the gateway's origin, with a
    single-page fallback for the app's own routes, and the API stays at /api."""
    (tmp_path / "index.html").write_text("<!doctype html><title>Cappy</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("// service worker", encoding="utf-8")
    calls: list = []
    with TestClient(build_app(_settings(static_dir=str(tmp_path)), transport=_fake_upstreams(calls))) as c:
        home = c.get("/")
        assert home.status_code == 200 and "Cappy" in home.text
        assert home.headers["cache-control"] == "no-store"

        asset = c.get("/assets/index-abc123.js")
        assert asset.status_code == 200 and "immutable" in asset.headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-store"

        deep_link = c.get("/listing/l9")
        assert deep_link.status_code == 200 and "Cappy" in deep_link.text, "client-side routes fall back to the app"
        assert c.get("/../../etc/passwd").status_code == 200 and "Cappy" in c.get("/../../etc/passwd").text

        assert c.get("/api/world").status_code == 200, "the API is untouched"
        assert c.get("/media/abc.png").headers["content-type"] == "image/png", "photos are not the app"
        assert c.get("/api/health").json()["ok"] is True
        assert c.get("/api/whatever").status_code == 404


def test_missing_static_dir_falls_back_to_api_only(tmp_path):
    with TestClient(build_app(_settings(static_dir=str(tmp_path / "nope")), transport=_fake_upstreams([]))) as c:
        assert c.get("/").json()["health"] == "/api/health"
