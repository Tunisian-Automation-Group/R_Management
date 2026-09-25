"""Nothing but what the event runtime needs: which events were handled."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

from cappy_common.db import new_metadata
from cappy_common.events import event_tables


class Base(DeclarativeBase):
    metadata = new_metadata()


OUTBOX, PROCESSED = event_tables(Base.metadata)
