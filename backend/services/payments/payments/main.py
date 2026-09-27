from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.runtime import Runtime

from . import invoices
from .handlers import handlers
from .identity import IdentityProvider, make_identity
from .jobs import purge_invoices, reconcile
from .provider import Provider, make_provider
from .routes import admin, internal, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings,
    *,
    provider: Provider | None = None,
    identity: IdentityProvider | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    provider = provider or make_provider(settings)
    identity = identity or make_identity(settings)

    async def close(app: FastAPI) -> None:
        await provider.aclose()

    runtime = Runtime(
        settings,
        metadata=Base.metadata,
        handlers=handlers(
            provider, settings.service_name, settings.payouts_on, invoices.issuer_of(settings), identity=identity
        ),
        loops=[reconcile, purge_invoices],
        on_stop=close,
    )
    app = create_app(settings, title="Cappy payments", lifespan=runtime.lifespan())
    app.state.verifier = verifier
    app.state.provider = provider
    app.state.identity = identity
    app.include_router(router)
    app.include_router(internal)
    app.include_router(admin)
    app.include_router(invoices.router)
    app.include_router(invoices.admin)
    return app


def create() -> FastAPI:
    return build_app(Settings())
