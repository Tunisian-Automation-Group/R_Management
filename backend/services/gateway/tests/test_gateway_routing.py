from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from gateway.main import build_app
from gateway.routing import BOOKING, CATALOG, MATCHING, PAYMENTS, resolve
from gateway.settings import Settings


@pytest.mark.parametrize(
    ("path", "upstream"),
    [
        ("/me", CATALOG),
        ("/me/listings", CATALOG),
        ("/districts", CATALOG),
        ("/cities", CATALOG),
        ("/owners/o1", CATALOG),
        ("/listings", CATALOG),
        ("/listings/l9", CATALOG),
        ("/listings/l9/slots", CATALOG),
        ("/listings/l9/reviews", CATALOG),
        ("/search", CATALOG),
        ("/saved/l9", CATALOG),
        ("/uploads", CATALOG),
        ("/listings/l9/offers", MATCHING),
        ("/matches", MATCHING),
        ("/quote", MATCHING),
        ("/categories", MATCHING),
        ("/browse/spotlight", MATCHING),
        ("/bookings", BOOKING),
        ("/bookings/bk_1/accept", BOOKING),
        ("/payments/config", PAYMENTS),
        ("/payments/webhooks/stripe", PAYMENTS),
        # Never reachable from outside, however the path is dressed up.
        ("/internal/candidates", None),
        ("/listings/internal/candidates", None),
        ("/bookings/../internal/busy", None),
        ("/match-for-offer", None),
        ("/admin/reset", None),
        ("/world", None),
        ("/nothing-here", None),
    ],
)
def test_resolve(path, upstream):
    assert resolve(path) == upstream


def _upstreams(calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.host, request.method, request.url.path, dict(request.headers)))
        if request.url.host == "matching":
            raise httpx.ConnectError("down")
        if request.url.path.startswith("/media/"):
            return httpx.Response(200, content=b"WEBP", headers={"content-type": "image/webp", "x-secret": "no"})
        return httpx.Response(201, json={"ok": True}, headers={"set-cookie": "leak=1"})

    return httpx.MockTransport(handler)


def _settings(**over) -> Settings:
    return Settings(
        app_env="test",
        catalog_url="http://catalog",
        matching_url="http://matching",
        booking_url="http://booking",
        payments_url="http://payments",
        **over,
    )


@pytest.fixture()
def gateway():
    calls: list = []
    with TestClient(build_app(_settings(), transport=_upstreams(calls))) as c:
        yield c, calls


def test_forwards_the_token_and_request_id_and_nothing_else(gateway):
    c, calls = gateway
    r = c.post(
        "/api/bookings",
        json={"listingId": "l9"},
        headers={"Authorization": "Bearer t", "Idempotency-Key": "k1", "X-Cappy-User": "o1", "Cookie": "a=b"},
    )
    assert r.status_code == 201 and "set-cookie" not in r.headers
    host, method, path, headers = calls[-1]
    assert (host, method, path) == ("booking", "POST", "/bookings")
    assert headers["authorization"] == "Bearer t" and headers["idempotency-key"] == "k1"
    assert headers["x-request-id"] == r.headers["x-request-id"]
    assert "x-cappy-user" not in headers and "cookie" not in headers


def test_unknown_paths_never_reach_a_service(gateway):
    c, calls = gateway
    for path in ("/api/internal/busy", "/api/whatever", "/api/admin/reset"):
        r = c.post(path, json={})
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert calls == []


def test_an_unreachable_service_is_a_clean_502(gateway):
    c, _ = gateway
    r = c.post("/api/matches", json={})
    assert r.status_code == 502 and "down" not in r.text


def test_photos_pass_through_without_internal_headers(gateway):
    c, _ = gateway
    r = c.get("/media/abc.webp")
    assert r.headers["content-type"] == "image/webp" and "x-secret" not in r.headers


def test_body_limit(gateway):
    c, calls = gateway
    assert (
        c.post("/api/bookings", content=b"x" * 300_000, headers={"content-type": "application/json"}).status_code == 413
    )
    assert calls == []


def test_serves_the_web_app_from_the_same_origin(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Cappy</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "sw.js").write_text("// service worker", encoding="utf-8")
    with TestClient(build_app(_settings(static_dir=str(tmp_path)), transport=_upstreams([]))) as c:
        home = c.get("/")
        assert "Cappy" in home.text and home.headers["cache-control"] == "no-store"
        assert "immutable" in c.get("/assets/index-abc123.js").headers["cache-control"]
        assert c.get("/sw.js").headers["cache-control"] == "no-store"
        assert "Cappy" in c.get("/listing/l9").text, "client-side routes fall back to the app"
        assert "Cappy" in c.get("/../../etc/passwd").text
        assert c.get("/api/whatever").status_code == 404


def test_the_native_apps_may_call_the_api_cross_origin():
    settings = _settings(cors_origins="capacitor://localhost,https://localhost")
    with TestClient(build_app(settings, transport=_upstreams([]))) as c:
        pre = {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,idempotency-key",
        }
        ok = c.options("/api/bookings", headers={"Origin": "capacitor://localhost", **pre})
        assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "capacitor://localhost"
        evil = c.options("/api/bookings", headers={"Origin": "https://evil.example", **pre})
        assert "access-control-allow-origin" not in evil.headers
