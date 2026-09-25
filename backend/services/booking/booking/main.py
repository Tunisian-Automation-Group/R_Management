from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.runtime import Runtime

from . import repository
from .clients import Catalog, HttpCatalog, HttpMatching, HttpPayments, Matching, Payments
from .handlers import handlers
from .jobs import sweep
from .routes import internal, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings,
    *,
    matching: Matching | None = None,
    payments: Payments | None = None,
    catalog: Catalog | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    token = settings.internal_token.get_secret_value()
    repository.START_EARLY = timedelta(minutes=settings.start_early_minutes)

    async def close(app: FastAPI) -> None:
        await app.state.matching.aclose()
        await app.state.payments.aclose()
        await app.state.catalog.aclose()

    runtime = Runtime(settings, metadata=Base.metadata, handlers=handlers(settings), loops=[sweep], on_stop=close)
    app = create_app(settings, title="Cappy booking", lifespan=runtime.lifespan())
    app.state.verifier = verifier
    app.state.matching = matching or HttpMatching(settings.matching_url, token)
    app.state.payments = payments or HttpPayments(settings.payments_url, token)
    app.state.catalog = catalog or HttpCatalog(settings.catalog_url, token)
    app.include_router(router)
    app.include_router(internal)
    return app


def create() -> FastAPI:
    return build_app(Settings())
