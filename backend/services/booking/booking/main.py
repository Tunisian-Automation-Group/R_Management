from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.db import Base, Database
from cappy_common.events import CATALOG_CHANGED, make_event_bus

from . import tables  # noqa: F401 - registers the tables on Base.metadata
from .clients import CatalogClient, HttpCatalogClient, HttpMatchingClient, MatchingClient
from .routes import router
from .settings import Settings
from .workers import auto_accept_loop, on_catalog_changed, seed_inbox_with_retry


def build_app(
    settings: Settings, matching: MatchingClient | None = None, catalog: CatalogClient | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.database_url)
        await db.create_all(Base)
        bus = make_event_bus(settings.event_bus_url, group="booking")

        app.state.settings = settings
        app.state.db = db
        app.state.bus = bus
        app.state.matching = matching or HttpMatchingClient(settings.matching_url)
        app.state.catalog = catalog or HttpCatalogClient(settings.catalog_url)
        app.state.current_user = lambda header: header or settings.demo_user_id

        async def _on_catalog_changed(payload: dict) -> None:
            await on_catalog_changed(app, payload)

        bus.subscribe(CATALOG_CHANGED, _on_catalog_changed)
        await bus.start()

        tasks: list[asyncio.Task] = []
        if settings.run_background_workers:
            if settings.demo_auto_accept_seconds > 0:
                tasks.append(asyncio.create_task(auto_accept_loop(app), name="auto-accept"))
            tasks.append(asyncio.create_task(seed_inbox_with_retry(app), name="reconcile-and-seed"))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await bus.stop()
            await app.state.matching.aclose()
            await app.state.catalog.aclose()
            await db.dispose()

    app = create_app(settings, title="Cappy booking", lifespan=lifespan)
    app.include_router(router)
    return app


app = build_app(Settings())
