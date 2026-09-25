"""Async SQLAlchemy plumbing shared by the services that own a database.

Postgres (Aurora in AWS) in every deployed environment; SQLite in memory for
unit tests. Schema changes go through Alembic migrations; ``create_all`` exists
only for tests and throwaway local runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, MetaData, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.types import TypeDecorator

# Deterministic constraint names, so Alembic migrations can refer to them and
# autogenerate never produces an anonymous constraint it cannot later drop.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# JSONB on Postgres (binary, indexable), plain JSON on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")


def new_metadata() -> MetaData:
    return MetaData(naming_convention=NAMING)


class UtcDateTime(TypeDecorator):
    """``timestamptz`` on Postgres; always returns an aware UTC datetime, on
    SQLite too (which would otherwise hand back naive values and quietly break
    every comparison with an aware one)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime; every instant must carry a timezone")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Database:
    def __init__(
        self,
        url: str,
        *,
        application_name: str = "cappy",
        pool_size: int = 5,
        max_overflow: int = 10,
        statement_timeout_ms: int = 5_000,
    ) -> None:
        self.url = url
        self.is_postgres = url.startswith("postgresql")
        kwargs: dict = {}
        if url.startswith("sqlite"):
            # One in-memory database shared across connections for tests.
            from sqlalchemy.pool import StaticPool

            kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        elif self.is_postgres:
            kwargs = {
                # Small pools per task; Aurora Serverless scales connections, but
                # 50 tasks x 15 connections is still a number to respect.
                "pool_size": pool_size,
                "max_overflow": max_overflow,
                "pool_pre_ping": True,
                "pool_recycle": 1800,
                "connect_args": {
                    "server_settings": {
                        "application_name": application_name,
                        # A runaway query is cancelled rather than holding a
                        # connection and locks until the client gives up.
                        "statement_timeout": str(statement_timeout_ms),
                        "idle_in_transaction_session_timeout": "30000",
                    }
                },
            }
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        if url.startswith("sqlite"):
            # SQLite ignores foreign keys unless asked. Postgres enforces them, so
            # tests must too, or an insert-order bug only shows up in production.
            @event.listens_for(self.engine.sync_engine, "connect")
            def _fk_on(dbapi_conn, _record):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
                # pysqlite opens transactions lazily and not before a SAVEPOINT,
                # so RELEASE would commit and a later rollback would not undo
                # it. Take transaction control away from the driver (the recipe
                # in SQLAlchemy's SQLite docs) so SQLite behaves like Postgres.
                dbapi_conn.isolation_level = None

            @event.listens_for(self.engine.sync_engine, "begin")
            def _begin(conn):  # noqa: ANN001
                conn.exec_driver_sql("BEGIN")

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_all(self, metadata: MetaData) -> None:
        """Tests and throwaway local runs only. Deployed schemas are migrated."""
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as s:
            yield s

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as s, s.begin():
            yield s

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
