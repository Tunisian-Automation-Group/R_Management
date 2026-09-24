from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from cappy_common.app import create_app
from cappy_common.errors import NotFound, error_body

from .routing import BOOKING, CATALOG, MATCHING, resolve
from .settings import Settings

log = logging.getLogger(__name__)

# Request headers worth passing upstream. Hop-by-hop headers and Host are not.
_FORWARD_REQUEST = {"content-type", "accept", "x-cappy-user", "x-request-id"}
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


def build_app(settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bases = {
            CATALOG: settings.catalog_url,
            MATCHING: settings.matching_url,
            BOOKING: settings.booking_url,
        }
        app.state.clients = {
            name: httpx.AsyncClient(base_url=url, timeout=settings.upstream_timeout_seconds, transport=transport)
            for name, url in bases.items()
        }
        try:
            yield
        finally:
            for c in app.state.clients.values():
                await c.aclose()

    app = create_app(settings, title="Cappy gateway", lifespan=lifespan)
    root = static_root(settings)

    async def forward(request: Request, upstream: str, path: str) -> Response:
        client: httpx.AsyncClient = request.app.state.clients[upstream]
        headers = {k: v for k, v in request.headers.items() if k.lower() in _FORWARD_REQUEST}
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
        pointed at, so the reseeded inbox request finds a fresh catalog."""
        for upstream in (BOOKING, CATALOG):
            r = await forward(request, upstream, "/admin/reset")
            if r.status_code >= 400:
                return r
        return Response(status_code=204)

    @app.api_route("/api/{path:path}", methods=_METHODS, include_in_schema=False)
    async def proxy(path: str, request: Request) -> Response:
        rel = "/" + path
        upstream = resolve(rel)
        if upstream is None:
            raise NotFound(f"no service answers {rel}")
        return await forward(request, upstream, rel)

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
