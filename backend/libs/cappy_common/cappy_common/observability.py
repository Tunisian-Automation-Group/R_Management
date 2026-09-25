"""Logs, request ids and traces, the same way in every service.

* Every request gets an id: the caller's ``X-Request-Id`` if it looks sane,
  otherwise a fresh one. It is echoed in the response, attached to every log
  line written while handling the request, and forwarded on every
  service-to-service call, so one id follows a request through the system.
* Logs are one JSON object per line in deployed environments (CloudWatch Logs
  Insights queries them directly), plain text on a laptop.
* Traces are OpenTelemetry, exported over OTLP to the ADOT collector sidecar
  (X-Ray in AWS), when ``OTEL_ENABLED`` is set.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
log = logging.getLogger("cappy.access")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
            "requestId": request_id.get(),
        }
        for key in ("method", "path", "status", "durationMs"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def configure_logging(level: str, *, service: str, json_lines: bool) -> None:
    handler = logging.StreamHandler()
    if json_lines:
        handler.setFormatter(JsonFormatter(service))
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's own access log duplicates ours without the request id.
    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so it adds no copy of the body and
    works with streaming responses."""

    def __init__(self, app: ASGIApp, *, quiet_paths: frozenset[str] = frozenset({"/healthz", "/readyz"})) -> None:
        self.app = app
        self.quiet = quiet_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        given = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = given if _SAFE_ID.match(given) else uuid.uuid4().hex
        token = request_id.set(rid)
        started = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode()))
                message["headers"] = headers
            await send(message)

        started_response = {"sent": False}

        async def tracking(message: Message) -> None:
            if message["type"] == "http.response.start":
                started_response["sent"] = True
            await send_wrapper(message)

        try:
            await self.app(scope, receive, tracking)
        except Exception:
            # Handled here rather than by Starlette's outermost error middleware,
            # which runs after this one has exited and the request id is gone.
            logging.getLogger("cappy.error").exception(
                "unhandled error on %s %s", scope.get("method"), scope.get("path")
            )
            status["code"] = 500
            if not started_response["sent"]:
                body = json.dumps(
                    {"error": {"code": "internal", "message": f"something went wrong on our side (request {rid})"}}
                ).encode()
                await send_wrapper(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
        finally:
            path = scope.get("path", "")
            if path not in self.quiet or status["code"] >= 400:
                log.info(
                    "%s %s %s",
                    scope.get("method"),
                    path,
                    status["code"],
                    extra={
                        "method": scope.get("method"),
                        "path": path,
                        "status": status["code"],
                        "durationMs": round((time.perf_counter() - started) * 1000, 1),
                    },
                )
            request_id.reset(token)


def setup_tracing(app: Any, settings: Any, engine: Any | None = None) -> None:
    """OpenTelemetry for FastAPI, httpx and SQLAlchemy. Imported lazily so a
    service that does not trace does not pay for it."""
    if not settings.otel_enabled:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name, "deployment.environment": settings.app_env})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{settings.otel_endpoint}/v1/traces")))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz")
    HTTPXClientInstrumentor().instrument()
    if engine is not None:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
