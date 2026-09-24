"""One error shape for every service: ``{"error": {"code": ..., "message": ...}}``."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class Invalid(ApiError):
    status = 422
    code = "invalid"


class Upstream(ApiError):
    status = 502
    code = "upstream"


def error_body(code: str, message: str, details: object | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("invalid", "request did not validate", _serialisable(exc.errors())),
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
