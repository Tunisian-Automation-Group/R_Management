"""Everything a service does at startup and shutdown, once.

A service describes what it has (a database, event handlers, extra readiness
checks, background loops) and the runtime wires it: the database and its
readiness check, the token verifier, the outbox and its relay, the event
consumer, and an orderly shutdown that stops taking work, finishes what it
has, flushes the outbox and closes connections.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import make_verifier
from .db import Database
from .events import Dispatcher, Handler, Outbox, OutboxRelay, event_tables, make_consumer, make_publisher
from .observability import setup_tracing

log = logging.getLogger(__name__)

Loop = Callable[[FastAPI], Awaitable[None]]


class Runtime:
    def __init__(
        self,
        settings: Any,
        *,
        metadata: MetaData | None = None,
        handlers: dict[str, Handler] | None = None,
        loops: list[Loop] | None = None,
        on_start: Callable[[FastAPI], Awaitable[None]] | None = None,
        on_stop: Callable[[FastAPI], Awaitable[None]] | None = None,
    ) -> None:
        self.settings = settings
        self.metadata = metadata
        self.handlers = handlers or {}
        self.loops = loops or []
        self.on_start = on_start
        self.on_stop = on_stop
        self.db: Database | None = None
        self.outbox: Outbox | None = None
        self.relay: OutboxRelay | None = None
        if metadata is not None:
            existing = metadata.tables.get("outbox")
            if existing is None:
                self.outbox_table, self.processed_table = event_tables(metadata)
            else:
                self.outbox_table, self.processed_table = existing, metadata.tables["processed_events"]

    @property
    def creates_schema(self) -> bool:
        """Only a throwaway SQLite database is created from the models. Postgres,
        locally as in AWS, is always migrated, so local runs exercise the same
        migrations production will."""
        url = getattr(self.settings, "database_url", "")
        return self.settings.app_env in ("local", "test") and url.startswith("sqlite")

    def lifespan(self) -> Callable[[FastAPI], Any]:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> AsyncIterator[None]:
            s = self.settings
            app.state.runtime = self
            # Tests install a verifier for their own throwaway issuer first.
            if getattr(app.state, "verifier", None) is None:
                app.state.verifier = make_verifier(s)

            tasks: list[asyncio.Task] = []
            publisher = None
            consumer = None
            if self.metadata is not None:
                self.db = Database(s.database_url, application_name=s.service_name)
                if self.creates_schema:
                    await self.db.create_all(self.metadata)
                app.state.db = self.db
                app.state.readiness.append(_named("database", self.db.ping))

                publisher = make_publisher(s)
                self.outbox = Outbox(self.outbox_table, s.service_name)
                self.relay = OutboxRelay(self.db, self.outbox_table, publisher)
                app.state.outbox = self.outbox
                app.state.relay = self.relay

                dispatcher = Dispatcher(self.db, self.processed_table, self.handlers)
                consumer = make_consumer(s, dispatcher)
                app.state.dispatcher = dispatcher

            setup_tracing(app, s, self.db.engine if self.db else None)

            if self.on_start:
                await self.on_start(app)

            # Background work never runs under test: tests drive the relay and
            # consumers explicitly, so they are deterministic.
            if s.app_env != "test":
                if self.relay:
                    tasks.append(asyncio.create_task(self.relay.run(), name=f"{s.service_name}:relay"))
                if consumer:
                    tasks.append(asyncio.create_task(consumer.run(), name=f"{s.service_name}:consumer"))
                for loop in self.loops:
                    tasks.append(asyncio.create_task(_forever(loop, app), name=f"{s.service_name}:{loop.__name__}"))
            try:
                yield
            finally:
                for t in tasks:
                    t.cancel()
                for t in tasks:
                    with contextlib.suppress(asyncio.CancelledError):
                        await t
                if self.relay:
                    # Whatever was committed during shutdown still goes out.
                    with contextlib.suppress(Exception):
                        await self.relay.flush()
                if self.on_stop:
                    await self.on_stop(app)
                if publisher:
                    await publisher.aclose()
                if self.db:
                    await self.db.dispose()

        return lifespan


def _named(name: str, fn: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
    async def check() -> None:
        await fn()

    check.__name__ = name
    return check


async def _forever(loop: Loop, app: FastAPI) -> None:
    """A periodic job that must never die of one bad iteration."""
    while True:
        try:
            await loop(app)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("background job %s failed; continuing", loop.__name__)
            await asyncio.sleep(5)


async def db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request. On success it commits and wakes the outbox
    relay, so events written by the request go out immediately.

    Always use it through ``Tx`` (``scope="function"``): FastAPI otherwise runs
    this cleanup *after* the response is sent, so a commit that fails would
    already have told the client it succeeded."""
    db: Database = request.app.state.db
    async with db.sessions() as session:
        async with session.begin():
            yield session
    relay: OutboxRelay | None = getattr(request.app.state, "relay", None)
    if relay is not None:
        relay.wake()


# The one way a route gets a database session: committed before the response.
Tx = Depends(db_session, scope="function")
