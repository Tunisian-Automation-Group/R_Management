"""The FastAPI shell every service uses.

Middleware, outermost first:

1. security headers on every response, errors included
2. request context: request id, access log, and the 500 for anything unhandled
3. body-size limit: a request larger than allowed is refused before it is read
4. CORS, only when a separately hosted client is configured

Plus the one error shape, ``/healthz`` (liveness: the process answers) and
``/readyz`` (readiness: its dependencies answer, so the load balancer stops
sending traffic to a task whose database is unreachable).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import error_body, install_error_handlers
from .observability import RequestContextMiddleware, configure_logging
from .settings import CommonSettings

ReadinessCheck = Callable[[], Awaitable[None]]


class ApiRouter(APIRouter):
    """An ``APIRouter`` that never sends ``null`` for an optional field.

    The web app runs domain rules written against TypeScript optionals
    (``listing.toleranceMm === undefined``). A ``null`` is not ``undefined``,
    so every response leaves absent fields out instead.
    """

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        kwargs["response_model_exclude_none"] = True
        super().add_api_route(path, endpoint, **kwargs)


class BodyLimitMiddleware:
    """Refuses bodies over the limit, by declared length and by bytes actually
    received (a client can lie about, or omit, ``Content-Length``)."""

    def __init__(self, app: ASGIApp, *, default: int, overrides: dict[str, int] | None = None) -> None:
        self.app = app
        self.default = default
        self.overrides = sorted((overrides or {}).items(), key=lambda kv: -len(kv[0]))

    def _limit(self, path: str) -> int:
        for prefix, limit in self.overrides:
            if path.startswith(prefix):
                return limit
        return self.default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope.get("path", ""))
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _too_large(send, limit)
            return

        seen = 0
        responded = False

        async def limited_receive() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal responded
            if message["type"] == "http.response.start":
                responded = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            if not responded:
                await _too_large(send, limit)


class _BodyTooLarge(Exception):
    pass


async def _too_large(send: Send, limit: int) -> None:
    import json

    body = json.dumps(error_body("too_large", f"request body is larger than {limit} bytes")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"strict-transport-security", b"max-age=63072000; includeSubDomains; preload"),
    (b"cross-origin-resource-policy", b"same-site"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                present = {k.lower() for k, _ in message.get("headers") or []}
                headers = list(message.get("headers") or [])
                headers += [(k, v) for k, v in _SECURITY_HEADERS if k not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, with_headers)


# Anonymous public reads: fresh for 30 s at the edge, then served stale while
# refreshing (request coalescing), and stale for 10 min if the origin is failing.
EDGE_CACHE = b"public, max-age=0, s-maxage=30, stale-while-revalidate=60, stale-if-error=600"


class PublicCacheMiddleware:
    """Marks successful anonymous GETs under ``prefixes`` as cacheable at the
    edge, and everything answered to a signed-in caller as private, so a
    personal answer (saved hearts, owner-only fields) is never shared."""

    def __init__(self, app: ASGIApp, prefixes: tuple[str, ...]) -> None:
        self.app = app
        self.prefixes = prefixes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        signed_in = any(k == b"authorization" for k, _ in scope.get("headers") or [])
        public = not signed_in and scope["path"].startswith(self.prefixes)

        async def mark(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                if not any(k.lower() == b"cache-control" for k, _ in headers):
                    if public and message["status"] == 200:
                        headers.append((b"cache-control", EDGE_CACHE))
                    elif signed_in:
                        headers.append((b"cache-control", b"private, no-store"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, mark)


def create_app(
    settings: CommonSettings,
    *,
    title: str,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
    body_limits: dict[str, int] | None = None,
    public_cache: tuple[str, ...] = (),
) -> FastAPI:
    configure_logging(settings.log_level, service=settings.service_name, json_lines=settings.log_json)
    # Interactive docs are for developers; a deployed API does not advertise
    # its whole surface to the internet.
    docs = not settings.deployed
    app = FastAPI(
        title=title,
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.settings = settings
    app.state.readiness = []  # list[ReadinessCheck]
    install_error_handlers(app)

    if settings.cors_origin_list:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["authorization", "content-type", "idempotency-key", "x-request-id"],
            max_age=600,
        )
    # Added innermost first: security headers wrap everything, so even a 413 or
    # a 500 written by an outer layer carries them.
    if public_cache:
        app.add_middleware(PublicCacheMiddleware, prefixes=public_cache)
    app.add_middleware(BodyLimitMiddleware, default=settings.max_body_bytes, overrides=body_limits)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True, "service": settings.service_name}

    @app.get("/readyz", include_in_schema=False)
    async def readyz(request: Request) -> JSONResponse:
        failures = []
        for check in request.app.state.readiness:
            try:
                await check()
            except Exception as e:  # noqa: BLE001 - readiness reports, it does not raise
                failures.append(f"{getattr(check, '__name__', 'check')}: {type(e).__name__}")
        if failures:
            return JSONResponse(status_code=503, content={"ok": False, "failing": failures})
        return JSONResponse({"ok": True, "service": settings.service_name})

    return app
