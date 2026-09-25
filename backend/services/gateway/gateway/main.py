"""The one public origin: routes ``/api/*`` to the services by an allow-list.

It does not authenticate. Every service verifies the caller's Cognito token
itself (ADR 0002), so the gateway passes ``Authorization`` through untouched
and a bug here cannot make anyone someone else.
"""

from __future__ import annotations

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

from .routing import BOOKING, CATALOG, MATCHING, PAYMENTS, resolve
from .settings import Settings

log = logging.getLogger(__name__)

_FORWARD_REQUEST = {"content-type", "accept", "authorization", "idempotency-key", "stripe-signature", "if-none-match"}
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


def build_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bases = {
            CATALOG: settings.catalog_url,
            MATCHING: settings.matching_url,
            BOOKING: settings.booking_url,
            PAYMENTS: settings.payments_url,
        }
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
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
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST}
        headers["x-request-id"] = request_id.get()
        try:
            r = await client.request(
                request.method, path, params=request.query_params, content=await request.body(), headers=headers
            )
        except httpx.TimeoutException:
            log.warning("%s timed out on %s %s", upstream, request.method, path)
            return JSONResponse(error_body("upstream_timeout", "that took too long; try again"), status_code=504)
        except httpx.HTTPError as e:
            log.warning("%s unreachable: %s", upstream, e)
            return JSONResponse(error_body("upstream", "a service is unavailable; try again"), status_code=502)
        return Response(
            status_code=r.status_code,
            content=r.content,
            headers={k: v for k, v in r.headers.items() if k.lower() in _FORWARD_RESPONSE},
        )

    @app.api_route("/api/{path:path}", methods=_METHODS, include_in_schema=False)
    async def proxy(path: str, request: Request) -> Response:
        rel = "/" + path
        upstream = resolve(rel)
        if upstream is None:
            return JSONResponse(error_body("not_found", f"no such endpoint: {request.method} /api{rel}"), 404)
        return await forward(request, upstream, rel)

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
