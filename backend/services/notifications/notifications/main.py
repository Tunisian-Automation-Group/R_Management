from __future__ import annotations

from fastapi import FastAPI

from cappy_common.app import create_app
from cappy_common.runtime import Runtime

from .handlers import handlers
from .mail import CognitoDirectory, Directory, LogMailer, Mailer, SesMailer
from .settings import Settings
from .tables import Base


def build_app(settings: Settings, *, directory: Directory | None = None, mailer: Mailer | None = None) -> FastAPI:
    directory = directory or CognitoDirectory(settings)
    mailer = mailer or (SesMailer(settings) if settings.mailer == "ses" else LogMailer())
    runtime = Runtime(settings, metadata=Base.metadata, handlers=handlers(directory, mailer, settings.web_base_url))
    app = create_app(settings, title="Cappy notifications", lifespan=runtime.lifespan())
    app.state.mailer = mailer
    return app


def create() -> FastAPI:
    return build_app(Settings())
