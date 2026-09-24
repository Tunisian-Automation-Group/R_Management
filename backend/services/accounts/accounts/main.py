from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.db import Base, Database

from . import tables  # noqa: F401 - registers the tables on Base.metadata
from .clients import CatalogClient, HttpCatalogClient
from .routes import router
from .seed import seed_demo_account
from .settings import Settings


def build_app(settings: Settings, catalog: CatalogClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(settings.database_url)
        await db.create_all(Base)
        app.state.settings = settings
        app.state.db = db
        app.state.catalog = catalog or HttpCatalogClient(settings.catalog_url)
        if settings.seed_on_start:
            await seed_demo_account(app)
        try:
            yield
        finally:
            await app.state.catalog.aclose()
            await db.dispose()

    app = create_app(settings, title="Cappy accounts", lifespan=lifespan)
    app.include_router(router)
    return app


app = build_app(Settings())
