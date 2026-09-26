from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.runtime import Runtime

from .clients import Bookings, Catalog, CatalogRevocations, HttpBookings, HttpCatalog
from .routes import admin, internal, router, vocab
from .settings import Settings


def build_app(
    settings: Settings,
    *,
    catalog: Catalog | None = None,
    bookings: Bookings | None = None,
    verifier: TokenVerifier | None = None,
    revocations=None,  # noqa: ANN001 - anything with async not_before(sub)
) -> FastAPI:
    token = settings.internal_token.get_secret_value()

    async def close(app: FastAPI) -> None:
        await app.state.catalog.aclose()
        await app.state.bookings.aclose()
        if hasattr(app.state.revocations, "aclose"):
            await app.state.revocations.aclose()

    # Stateless: no database, no events. Two upstreams, both per request.
    runtime = Runtime(settings, on_stop=close)
    app = create_app(settings, title="Cappy matching", lifespan=runtime.lifespan())
    app.state.verifier = verifier
    app.state.catalog = catalog or HttpCatalog(settings.catalog_url, token)
    app.state.bookings = bookings or HttpBookings(settings.booking_url, token)
    # Sessions ended elsewhere end here too (P-24): the auth dependency asks.
    app.state.revocations = revocations or CatalogRevocations(settings.catalog_url, token)
    app.include_router(vocab)
    app.include_router(router)
    app.include_router(internal)
    app.include_router(admin)
    return app


def create() -> FastAPI:
    return build_app(Settings())
