from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.runtime import Runtime

from . import invoices
from .handlers import handlers
from .jobs import reconcile
from .provider import Provider, make_provider
from .routes import internal, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings, *, provider: Provider | None = None, verifier: TokenVerifier | None = None
) -> FastAPI:
    provider = provider or make_provider(settings)

    async def close(app: FastAPI) -> None:
        await provider.aclose()

    runtime = Runtime(
        settings,
        metadata=Base.metadata,
        handlers=handlers(provider, settings.service_name, settings.payouts_on),
        loops=[reconcile],
        on_stop=close,
    )
    app = create_app(settings, title="Cappy payments", lifespan=runtime.lifespan())
    app.state.verifier = verifier
    app.state.provider = provider
    app.include_router(router)
    app.include_router(internal)
    app.include_router(invoices.router)
    return app


def create() -> FastAPI:
    return build_app(Settings())
