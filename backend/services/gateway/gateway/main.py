"""The one public origin: routes ``/api/*`` to the services by an allow-list.

It does not authenticate. Every service verifies the caller's Cognito token
itself (ADR 0002), so the gateway passes ``Authorization`` through untouched
and a bug here cannot make anyone someone else.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from cappy_common.app import create_app
from cappy_common.errors import error_body
from cappy_common.observability import request_id

from .routing import BOOKING, CATALOG, MATCHING, NOTIFICATIONS, PAYMENTS, resolve
from .settings import Settings

log = logging.getLogger(__name__)

_FORWARD_REQUEST = {
    "content-type",
    "accept",
    "authorization",
    "idempotency-key",
    "stripe-signature",
    "if-none-match",
    "x-app-version",
}
_FORWARD_RESPONSE = {"content-type", "cache-control", "location", "etag", "retry-after"}
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def static_root(settings: Settings) -> Path | None:
    if not settings.static_dir:
        return None
    root = Path(settings.static_dir)
    if not (root / "index.html").is_file():
        log.warning("STATIC_DIR=%s has no index.html; serving the API only", root)
        return None
    return root.resolve()


class Shed(Exception):
    """Too much in flight; answered with 503 and Retry-After."""


class Admission:
    """Counts requests in flight on this task. Browsing may use only part of
    the capacity; writes (a booking, a payment, a listing) get the rest, so an
    overload of searches never stops people paying (Netflix's priority
    shedding, in its simplest form)."""

    def __init__(self, limit: int, browse_share: float) -> None:
        self.limit = limit
        self.browse_limit = max(1, int(limit * browse_share))
        self.in_flight = 0

    def enter(self, write: bool) -> None:
        cap = self.limit if write else self.browse_limit
        if self.in_flight >= cap:
            raise Shed
        self.in_flight += 1

    def leave(self) -> None:
        self.in_flight -= 1


def _overloaded(retry_after: int = 2) -> JSONResponse:
    return JSONResponse(
        error_body("overloaded", "we are very busy right now; try again in a moment"),
        status_code=503,
        headers={"Retry-After": str(retry_after)},
    )


def build_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bases = {
            CATALOG: settings.catalog_url,
            MATCHING: settings.matching_url,
            BOOKING: settings.booking_url,
            PAYMENTS: settings.payments_url,
            NOTIFICATIONS: settings.notifications_url,
        }
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        app.state.admission = Admission(settings.max_in_flight, settings.browse_share)
        app.state.bulkheads = {name: asyncio.Semaphore(settings.per_upstream_in_flight) for name in bases}
        app.state.clients = {
            name: httpx.AsyncClient(
                base_url=url, timeout=settings.upstream_timeout_seconds, transport=transport, limits=limits
            )
            for name, url in bases.items()
        }
        try:
            yield
        finally:
            for c in app.state.clients.values():
                await c.aclose()

    app = create_app(
        settings,
        title="Cappy gateway",
        lifespan=lifespan,
        body_limits={"/api/uploads": settings.upload_max_bytes},
    )

    async def forward(request: Request, upstream: str, path: str) -> Response:
        client: httpx.AsyncClient = request.app.state.clients[upstream]
        bulkhead: asyncio.Semaphore = request.app.state.bulkheads[upstream]
        if bulkhead.locked():
            log.warning("bulkhead full for %s; shedding %s %s", upstream, request.method, path)
            return _overloaded()
        async with bulkhead:
            return await _send(request, client, upstream, path)

    async def _send(request: Request, client: httpx.AsyncClient, upstream: str, path: str) -> Response:
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST}
        headers["x-request-id"] = request_id.get()
        try:
            r = await client.request(
                request.method, path, params=request.query_params, content=await request.body(), headers=headers
            )
        except httpx.TimeoutException:
            log.warning("%s timed out on %s %s", upstream, request.method, path)
            return JSONResponse(
                error_body("upstream_timeout", "that took too long; try again"),
                status_code=504,
                headers={"Retry-After": "2"},
            )
        except httpx.HTTPError as e:
            log.warning("%s unreachable: %s", upstream, e)
            return JSONResponse(
                error_body("upstream", "a service is unavailable; try again"),
                status_code=502,
                headers={"Retry-After": "2"},
            )
        return Response(
            status_code=r.status_code,
            content=r.content,
            headers={k: v for k, v in r.headers.items() if k.lower() in _FORWARD_RESPONSE},
        )

    @app.get("/api/app-config", include_in_schema=False)
    async def app_config() -> JSONResponse:
        """What the store apps check at start: below minVersion they ask the
        person to update rather than calling an API they may no longer match."""
        return JSONResponse(
            {"minVersion": settings.app_min_version, "latestVersion": settings.app_latest_version},
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.api_route("/api/{path:path}", methods=_METHODS, include_in_schema=False)
    async def proxy(path: str, request: Request) -> Response:
        rel = "/" + path
        upstream = resolve(rel)
        if upstream is None:
            return JSONResponse(error_body("not_found", f"no such endpoint: {request.method} /api{rel}"), 404)
        admission: Admission = request.app.state.admission
        try:
            admission.enter(write=request.method != "GET")
        except Shed:
            return _overloaded()
        try:
            return await forward(request, upstream, rel)
        finally:
            admission.leave()

    @app.get("/media/{name}", include_in_schema=False)
    async def media_file(name: str, request: Request) -> Response:
        """Locally, photos from the catalog's store. In AWS CloudFront serves them from S3."""
        return await forward(request, CATALOG, f"/media/{name}")

    root = static_root(settings)
    if root is not None:
        # Hashed assets are immutable; index.html and the service worker are
        # not, or an installed app would never pick up a new build.
        no_store = {"index.html", "sw.js", "registerSW.js", "manifest.webmanifest"}

        def serve(rel: str) -> FileResponse:
            candidate = (root / rel).resolve() if rel else root / "index.html"
            if rel and (root not in candidate.parents or not candidate.is_file()):
                candidate = root / "index.html"  # a client-side route
            if candidate.name in no_store:
                cache = "no-store"
            elif candidate.parent.name == "assets":
                cache = "public, max-age=31536000, immutable"
            else:
                cache = "public, max-age=3600"
            return FileResponse(candidate, headers={"Cache-Control": cache})

        @app.get("/", include_in_schema=False)
        async def index_html() -> FileResponse:
            return serve("")

        @app.get("/{rel:path}", include_in_schema=False)
        async def spa(rel: str) -> FileResponse:
            return serve(rel)

    return app


def create() -> FastAPI:
    return build_app(Settings())
