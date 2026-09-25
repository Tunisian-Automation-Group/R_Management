from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.events import BOOKING_RATED, OWNER_RELIABILITY, PAYOUTS_READY, PERSON_FLAGGED, RENTER_RATED
from cappy_common.runtime import Runtime

from . import moderation
from .clients import Bookings, HttpBookings, HttpNotifications, HttpPayments, Notifications, Payments
from .handlers import on_booking_rated, on_owner_reliability, on_payouts_ready, on_person_flagged, on_renter_rated
from .jobs import sweep_orphans
from .media import MediaStore, make_store
from .routes import internal, media_router, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings,
    *,
    media_store: MediaStore | None = None,
    evidence_store: MediaStore | None = None,
    bookings: Bookings | None = None,
    payments: Payments | None = None,
    notifications: Notifications | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    async def close(app: FastAPI) -> None:
        await app.state.bookings.aclose()
        await app.state.payments.aclose()
        await app.state.notifications.aclose()

    runtime = Runtime(
        settings,
        metadata=Base.metadata,
        handlers={
            BOOKING_RATED: on_booking_rated,
            PAYOUTS_READY: on_payouts_ready,
            RENTER_RATED: on_renter_rated,
            OWNER_RELIABILITY: on_owner_reliability,
            PERSON_FLAGGED: on_person_flagged,
        },
        loops=[sweep_orphans],
        on_stop=close,
    )
    app = create_app(
        settings,
        title="Cappy catalog",
        lifespan=runtime.lifespan(),
        # Photos are the one large body; everything else keeps the default.
        body_limits={"/uploads": settings.media_max_bytes + 64_000},
    )
    app.state.verifier = verifier
    app.state.media = media_store or make_store(settings)
    app.state.evidence = evidence_store or make_store(settings, private=True)
    app.state.bookings = bookings or HttpBookings(settings.booking_url, settings.internal_token.get_secret_value())
    app.state.payments = payments or HttpPayments(settings.payments_url, settings.internal_token.get_secret_value())
    app.state.notifications = notifications or HttpNotifications(
        settings.notifications_url, settings.internal_token.get_secret_value()
    )
    app.include_router(router)
    app.include_router(media_router)
    app.include_router(moderation.public)
    app.include_router(moderation.admin)
    app.include_router(internal)
    return app


def create() -> FastAPI:
    """Uvicorn factory (``uvicorn --factory catalog.main:create``): settings are
    read when the server starts, not when the module is imported."""
    return build_app(Settings())
