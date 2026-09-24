from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from cappy_common.app import create_app
from cappy_common.errors import NotFound, Unauthorized, error_body

from .routing import ACCOUNTS, BOOKING, CATALOG, MATCHING, resolve
from .settings import Settings

log = logging.getLogger(__name__)

# Request headers worth passing upstream. Hop-by-hop headers and Host are not,
# and neither is X-Cappy-User: the gateway sets that one itself, from the
# session, and a client cannot choose to be someone else by sending it.
_FORWARD_REQUEST = {"content-type", "accept", "x-request-id"}
_FORWARD_RESPONSE = {"content-type", "cache-control", "location"}
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]


def static_root(settings: Settings) -> Path | None:
    """The built web app, if the gateway has been pointed at one."""
    if not settings.static_dir:
        return None
    root = Path(settings.static_dir)
    if not (root / "index.html").is_file():
        log.warning("STATIC_DIR=%s has no index.html; serving the API only", root)
        return None
    return root.resolve()


class SessionCache:
    """Token -> owner id, remembered briefly so the accounts service is asked
    once per minute per device rather than once per request. A sign-out drops
    the entry at once; an expired session is refused within the TTL."""

    def __init__(self, ttl_seconds: float, capacity: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._capacity = capacity
        self._entries: dict[str, tuple[str, float]] = {}

    def get(self, token: str) -> str | None:
        hit = self._entries.get(token)
        if not hit:
            return None
        user, until = hit
        if until < time.monotonic():
            del self._entries[token]
            return None
        return user

    def put(self, token: str, user: str) -> None:
        if len(self._entries) >= self._capacity:
            self._entries.clear()
        self._entries[token] = (user, time.monotonic() + self._ttl)

    def drop(self, token: str) -> None:
        self._entries.pop(token, None)


def build_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bases = {
            CATALOG: settings.catalog_url,
            MATCHING: settings.matching_url,
            BOOKING: settings.booking_url,
            ACCOUNTS: settings.accounts_url,
        }
        app.state.clients = {
            name: httpx.AsyncClient(base_url=url, timeout=settings.upstream_timeout_seconds, transport=transport)
            for name, url in bases.items()
        }
        app.state.sessions = SessionCache(settings.session_cache_seconds)
        try:
            yield
        finally:
            for c in app.state.clients.values():
                await c.aclose()

    app = create_app(settings, title="Cappy gateway", lifespan=lifespan)
    root = static_root(settings)

    def bearer(request: Request) -> str | None:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        return auth[7:].strip() or None

    async def identify(request: Request) -> str | None:
        """The owner id behind the request's session token, None when there is
        no token, and a 401 when there is one and it is no good."""
        token = bearer(request)
        if not token:
            return None
        cache: SessionCache = request.app.state.sessions
        user = cache.get(token)
        if user:
            return user
        client: httpx.AsyncClient = request.app.state.clients[ACCOUNTS]
        try:
            r = await client.get("/auth/session", headers={"Authorization": f"Bearer {token}"})
        except httpx.HTTPError as e:
            raise Unauthorized(f"accounts is unreachable: {e}") from e
        if r.status_code == 200:
            user = r.json()["id"]
            cache.put(token, user)
            return user
        if r.status_code == 401:
            raise Unauthorized(r.json().get("error", {}).get("message", "sign in again"))
        raise Unauthorized(f"accounts answered {r.status_code}")

    async def forward(request: Request, upstream: str, path: str, *, user: str | None = None) -> Response:
        client: httpx.AsyncClient = request.app.state.clients[upstream]
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST}
        if user:
            headers["X-Cappy-User"] = user
        if upstream == ACCOUNTS and "authorization" in request.headers:
            headers["Authorization"] = request.headers["authorization"]
        try:
            r = await client.request(
                request.method,
                path,
                params=request.query_params,
                content=await request.body(),
                headers=headers,
            )
        except httpx.HTTPError as e:
            return Response(
                status_code=502,
                media_type="application/json",
                content=_json(error_body("upstream", f"{upstream} is unreachable: {e}")),
            )
        return Response(
            status_code=r.status_code,
            content=r.content,
            headers={k: v for k, v in r.headers.items() if k.lower() in _FORWARD_RESPONSE},
        )

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        async def probe(name: str, client: httpx.AsyncClient) -> tuple[str, bool]:
            try:
                r = await client.get("/healthz", timeout=3)
                return name, r.status_code == 200
            except httpx.HTTPError:
                return name, False

        results = dict(await asyncio.gather(*(probe(n, c) for n, c in request.app.state.clients.items())))
        return {"ok": all(results.values()), "services": results}

    @app.post("/api/admin/reset", status_code=204)
    async def reset(request: Request) -> Response:
        """Demo reset, in dependency order: bookings first, then the world they
        pointed at, then accounts, so the reseeded inbox request finds a fresh
        catalog and every session is ended."""
        for upstream in (BOOKING, CATALOG, ACCOUNTS):
            r = await forward(request, upstream, "/admin/reset")
            if r.status_code >= 400:
                return r
        request.app.state.sessions = SessionCache(settings.session_cache_seconds)
        return Response(status_code=204)

    @app.api_route("/api/{path:path}", methods=_METHODS, include_in_schema=False)
    async def proxy(path: str, request: Request) -> Response:
        rel = "/" + path
        upstream = resolve(rel)
        if upstream is None:
            raise NotFound(f"no service answers {rel}")
        if upstream == ACCOUNTS:
            # Sign-in and sign-up carry no session yet; the accounts service
            # reads the token itself for session and logout.
            response = await forward(request, upstream, rel)
            if rel == "/auth/logout" and (token := bearer(request)):
                request.app.state.sessions.drop(token)
            return response
        return await forward(request, upstream, rel, user=await identify(request))

    @app.get("/media/{name}", include_in_schema=False)
    async def media_file(name: str, request: Request) -> Response:
        """Listing photographs, from the catalog's store, on the app's origin
        so a photo URL is the same string on the website and the phone."""
        return await forward(request, CATALOG, f"/media/{name}")

    if root is None:

        @app.get("/", include_in_schema=False)
        async def index() -> dict:
            """A browser landing on the bare origin should see where to go, not a 404."""
            return {
                "service": "cappy gateway",
                "health": "/api/health",
                "world": "/api/world",
                "bookings": "/api/bookings",
                "docs": "/docs",
                "service_docs": {
                    "catalog": "http://localhost:8001/docs",
                    "matching": "http://localhost:8002/docs",
                    "booking": "http://localhost:8003/docs",
                    "accounts": "http://localhost:8004/docs",
                },
                "frontend_integration": "backend/docs/frontend-integration.md",
            }

    else:
        # The web app and the installed PWA, from the same origin as the API.
        # Hashed assets are immutable; index.html and the service worker are
        # not, or an installed app would never pick up a new build.
        _NO_STORE = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}

        def _serve(rel: str) -> FileResponse:
            candidate = (root / rel).resolve() if rel else root / "index.html"
            if rel and (root not in candidate.parents or not candidate.is_file()):
                # Client-side route (``/listing/l9``): the app's router takes it from here.
                candidate = root / "index.html"
            headers = (
                {"Cache-Control": "no-store"}
                if candidate.name in _NO_STORE
                else {"Cache-Control": "public, max-age=31536000, immutable"}
                if candidate.parent.name == "assets"
                else {"Cache-Control": "public, max-age=3600"}
            )
            return FileResponse(candidate, headers=headers)

        @app.get("/", include_in_schema=False)
        async def index_html() -> FileResponse:
            return _serve("")

        @app.get("/{rel:path}", include_in_schema=False)
        async def spa(rel: str) -> FileResponse:
            return _serve(rel)

    return app


def _json(body: dict) -> bytes:
    import json

    return json.dumps(body).encode()


app = build_app(Settings())
