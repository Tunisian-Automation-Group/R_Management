from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.events import CATALOG_CHANGED, make_event_bus
from cappy_common.http import ServiceClient

from .routes import router
from .settings import Settings
from .world import CatalogWorldProvider, WorldProvider


def build_app(settings: Settings, world_provider: WorldProvider | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        provider = world_provider or CatalogWorldProvider(
            ServiceClient(settings.catalog_url), settings.world_cache_ttl_seconds
        )
        bus = make_event_bus(settings.event_bus_url, group="matching")

        async def on_catalog_changed(_: dict) -> None:
            provider.invalidate()

        bus.subscribe(CATALOG_CHANGED, on_catalog_changed)
        await bus.start()

        app.state.settings = settings
        app.state.world_provider = provider
        app.state.bus = bus
        try:
            yield
        finally:
            await bus.stop()
            await provider.aclose()

    app = create_app(settings, title="Cappy matching", lifespan=lifespan)
    app.include_router(router)
    return app


app = build_app(Settings())
