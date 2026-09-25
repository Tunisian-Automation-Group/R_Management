"""Alembic, the same way for every service.

Each service keeps its migrations in ``<service>/migrations/versions``. Its
``env.py`` is three lines that call ``run_env`` with its metadata. Deployed
schemas only ever change through these files: a one-off ``migrate`` task runs
``upgrade head`` before new code rolls out (and the new code must work with
the schema before and after, so a rollback never needs a down-migration).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from alembic import command, context
from alembic.config import Config
from sqlalchemy import MetaData, pool
from sqlalchemy.ext.asyncio import create_async_engine


def config(migrations_dir: Path, url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("version_path_separator", "os")
    return cfg


def upgrade(migrations_dir: Path, url: str, revision: str = "head") -> None:
    """Blocking. From async code, call it through ``asyncio.to_thread``."""
    command.upgrade(config(migrations_dir, url), revision)


def _render_item(type_: str, obj, autogen_context):  # noqa: ANN001
    """Write our custom column types as plain SQLAlchemy ones, so a migration
    never imports application code (which will have moved on by the time an
    old migration runs against a fresh database)."""
    from .db import UtcDateTime

    if type_ == "type" and isinstance(obj, UtcDateTime):
        return "sa.DateTime(timezone=True)"
    if type_ == "type" and type(obj).__name__ == "JSON" and getattr(obj, "_variant_mapping", None):
        autogen_context.imports.add("from sqlalchemy.dialects import postgresql")
        return "postgresql.JSONB(astext_type=sa.Text())"
    return False


def run_env(metadata: MetaData) -> None:
    """The body of every service's ``env.py``."""
    url = context.config.get_main_option("sqlalchemy.url") or os.environ["DATABASE_URL"]

    def run(connection) -> None:  # noqa: ANN001
        context.configure(
            connection=connection,
            target_metadata=metadata,
            compare_type=True,
            render_item=_render_item,
            # One transaction per migration file: a failure leaves the schema at
            # the last good revision, not half-way through one.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()

    if context.is_offline_mode():
        context.configure(url=url, target_metadata=metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    async def online() -> None:
        engine = create_async_engine(url, poolclass=pool.NullPool)
        async with engine.connect() as conn:
            await conn.run_sync(run)
        await engine.dispose()

    asyncio.run(online())


def main() -> None:
    """``python -m cappy_common.migrations <service>``: upgrade that service's
    database (``DATABASE_URL``) to head. The ``migrate`` task runs this."""
    import importlib.util
    import sys

    (service,) = sys.argv[1:]
    spec = importlib.util.find_spec(service)
    if spec is None or spec.origin is None:
        raise SystemExit(f"no such service package: {service}")
    upgrade(Path(spec.origin).parent / "migrations", os.environ["DATABASE_URL"])


if __name__ == "__main__":
    main()
