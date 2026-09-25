from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.events import BOOKING_RATED, PAYOUTS_READY
from cappy_common.runtime import Runtime

from .clients import Bookings, HttpBookings
from .handlers import on_booking_rated, on_payouts_ready
from .jobs import sweep_orphans
from .media import MediaStore, make_store
from .routes import internal, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings,
    *,
    media_store: MediaStore | None = None,
    bookings: Bookings | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    async def close(app: FastAPI) -> None:
        await app.state.bookings.aclose()

    runtime = Runtime(
        settings,
        metadata=Base.metadata,
        handlers={BOOKING_RATED: on_booking_rated, PAYOUTS_READY: on_payouts_ready},
        loops=[sweep_orphans],
        on_stop=close,
    )
    app = create_app(
        settings,
        title="Cappy catalog",
        lifespan=runtime.lifespan(),
        # Photos are the one large body; everything else keeps the default.
        body_limits={"/uploads": settings.media_max_bytes + 64_000},
        # Listing pages, their reviews, search and owner cards (resilience F7).
        public_cache=("/listings/", "/search", "/owners/"),
    )
    app.state.verifier = verifier
    app.state.media = media_store or make_store(settings)
    app.state.bookings = bookings or HttpBookings(settings.booking_url, settings.internal_token.get_secret_value())
    app.include_router(router)
    app.include_router(internal)
    return app


def create() -> FastAPI:
    """Uvicorn factory (``uvicorn --factory catalog.main:create``): settings are
    read when the server starts, not when the module is imported."""
    return build_app(Settings())
