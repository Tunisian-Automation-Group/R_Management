"""The FastAPI shell every service uses: health, CORS, error shape, user header."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from fastapi import APIRouter, FastAPI, Header

from .errors import Unauthorized, install_error_handlers
from .settings import CommonSettings


class ApiRouter(APIRouter):
    """An ``APIRouter`` that never sends ``null`` for an optional field.

    The web app and the mobile app both run the domain rules locally on the
    JSON they load, and those rules are written against TypeScript optionals
    (``listing.toleranceMm === undefined``). A ``null`` there is not
    ``undefined``, so every response leaves absent fields out instead.
    """

    def add_api_route(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        kwargs["response_model_exclude_none"] = True
        super().add_api_route(path, endpoint, **kwargs)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def create_app(
    settings: CommonSettings,
    *,
    title: str,
    lifespan: Callable[[FastAPI], AbstractAsyncContextManager[None]] | None = None,
) -> FastAPI:
    configure_logging(settings.log_level)
    app = FastAPI(title=title, version="0.2.0", lifespan=lifespan)
    install_error_handlers(app)

    if settings.cors_origin_list or settings.cors_origin_regex:
        from fastapi.middleware.cors import CORSMiddleware

        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,
            allow_origin_regex=settings.cors_origin_regex or None,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/healthz", tags=["ops"], include_in_schema=False)
    async def healthz() -> dict:
        return {"ok": True, "service": settings.service_name}

    return app


def identity(settings: CommonSettings) -> Callable[[str | None], str]:
    """Who is calling, from the ``X-Cappy-User`` header the gateway sets after
    checking the session. With no header and no demo user there is nobody, and
    anything that needs a person is refused with a 401."""

    def current_user(header: str | None) -> str:
        if header:
            return header
        if settings.demo_user_id:
            return settings.demo_user_id
        raise Unauthorized("sign in to do that")

    return current_user


def user_dependency(settings: CommonSettings) -> Callable[..., str]:
    """``identity`` as a FastAPI dependency."""
    current = identity(settings)

    def current_user(x_cappy_user: str | None = Header(default=None)) -> str:
        return current(x_cappy_user)

    return current_user
