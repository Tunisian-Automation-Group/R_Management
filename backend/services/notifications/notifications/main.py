from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.auth import TokenVerifier
from cappy_common.runtime import Runtime

from .handlers import handlers
from .mail import CognitoDirectory, Directory, LogMailer, Mailer, SesMailer
from .push import LogPusher, Pusher, SnsPusher
from .routes import internal, router
from .settings import Settings
from .tables import Base


def build_app(
    settings: Settings,
    *,
    directory: Directory | None = None,
    mailer: Mailer | None = None,
    pusher: Pusher | None = None,
    verifier: TokenVerifier | None = None,
) -> FastAPI:
    directory = directory or CognitoDirectory(settings)
    mailer = mailer or (SesMailer(settings) if settings.mailer == "ses" else LogMailer())
    configured = settings.push_ios_app_arn or settings.push_android_app_arn
    pusher = pusher or (SnsPusher(settings) if configured else LogPusher())
    runtime = Runtime(
        settings, metadata=Base.metadata, handlers=handlers(directory, mailer, settings.web_base_url, pusher)
    )
    app = create_app(settings, title="Cappy notifications", lifespan=runtime.lifespan())
    app.state.verifier = verifier
    app.state.mailer = mailer
    app.state.pusher = pusher
    app.state.directory = directory
    app.include_router(router)
    app.include_router(internal)
    return app


def create() -> FastAPI:
    return build_app(Settings())
