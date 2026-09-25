"""One error shape for every service: ``{"error": {"code": ..., "message": ...}}``."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    status = 500
    code = "internal"

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        if status is not None:
            self.status = status
        if code is not None:
            self.code = code


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class Unauthorized(ApiError):
    """No account behind the request. Sign in, then try again."""

    status = 401
    code = "unauthorized"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class Invalid(ApiError):
    status = 422
    code = "invalid"


class TooLarge(ApiError):
    status = 413
    code = "too_large"


class RateLimited(ApiError):
    status = 429
    code = "rate_limited"


class Upstream(ApiError):
    status = 502
    code = "upstream"


class Unavailable(ApiError):
    status = 503
    code = "unavailable"


def error_body(code: str, message: str, details: object | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        # A 503 says when to come back, so clients spread their retries out.
        headers = {"Retry-After": "2"} if exc.status == 503 else None
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message), headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("invalid", "request did not validate", _serialisable(exc.errors())),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Router-level 404/405 in the same shape as everything else.
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "error")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Logged in full with the request id; the client learns nothing about
        # the internals, only the id to quote to support.
        from .observability import request_id

        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_body("internal", f"something went wrong on our side (request {request_id.get()})"),
        )


def _serialisable(errors: list) -> list:
    """Pydantic puts the raw exception from a ``field_validator`` in ``ctx``;
    JSON wants its message."""
    out = []
    for e in errors:
        e = dict(e)
        if isinstance(e.get("ctx"), dict):
            e["ctx"] = {k: str(v) if isinstance(v, Exception) else v for k, v in e["ctx"].items()}
        out.append(e)
    return out
