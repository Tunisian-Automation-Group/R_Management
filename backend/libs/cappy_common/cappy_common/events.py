"""Events between services: transactional outbox → SNS → one SQS queue per consumer.

Why each piece exists (ADR 0003):

* **Outbox.** A service never publishes directly. It writes the event to its
  own ``outbox`` table *in the same transaction* as the change the event
  describes. Either both commit or neither does, so no event announces a
  change that rolled back, and no committed change goes unannounced.
* **Relay.** A background task in every replica claims unsent rows with
  ``FOR UPDATE SKIP LOCKED`` (so replicas never publish the same row twice
  concurrently), publishes them, and marks them sent. Delivery is
  at-least-once: a crash after publishing and before marking resends.
* **Idempotent consumers.** A consumer records every event id it has handled
  in ``processed_events``, in the same transaction as the handler's own
  writes. A redelivered event finds its id and does nothing.
* **Failures are never acknowledged.** A handler that raises leaves the
  message on the queue; SQS redelivers after the visibility timeout (30 s
  doubling to 15 min, jittered), and after 12 receives (about 2 h) moves it
  to the dead-letter queue, where an alarm fires.

Tests and single-process runs use ``memory://``: the same outbox and the same
idempotent processing, with an in-process broker in place of SNS/SQS.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from opentelemetry import propagate, trace
from sqlalchemy import Column, Index, Integer, MetaData, String, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .db import Database, JsonType, UtcDateTime
from .ids import new_id
from .timeutil import iso_from_datetime

log = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

# --- the catalogue of event types --------------------------------------------
# One place, so a producer and a consumer cannot disagree on a name. Adding a
# type means adding it here and to the SNS subscription filter in Terraform.
BOOKING_STATUS_CHANGED = "booking.status_changed"
BOOKING_RATED = "booking.rated"
# The owner rated the renter (two-way reviews).
RENTER_RATED = "booking.renter_rated"
# A message between the two sides of a booking.
BOOKING_MESSAGE = "booking.message"
PAYMENT_AUTHORISED = "payment.authorised"
PAYMENT_FAILED = "payment.failed"
PAYMENT_CAPTURED = "payment.captured"
PAYMENT_REFUNDED = "payment.refunded"
PAYOUT_SENT = "payment.payout_sent"
# Stripe Identity verified who someone is (document and selfie).
IDENTITY_VERIFIED = "payment.identity_verified"
# An owner can (ready=true) or can no longer (false) be paid, so be booked.
PAYOUTS_READY = "payment.payouts_ready"
PROFILE_CREATED = "profile.created"
# Someone deleted their account: forget what is theirs to forget.
PROFILE_DELETED = "profile.deleted"
# "Sign out everywhere": their refresh tokens go, and tokens issued before
# now stop counting in every service (cappy_common/guard.py, P-24).
PERSON_SIGNED_OUT = "person.signed_out"
# DSA Art. 16: someone reported content; Art. 17: a moderation decision.
REPORT_RECEIVED = "moderation.report_received"
MODERATION_DECISION = "moderation.decision"
OWNER_SUSPENDED = "moderation.owner_suspended"
OWNER_REINSTATED = "moderation.owner_reinstated"
LISTING_CHANGED = "listing.changed"
# Booking recomputed an owner's reliability (cancellations, no-shows; S-18).
OWNER_RELIABILITY = "booking.owner_reliability"
# Something for staff to look at that nobody reported: an owner cancelling a
# lot, a card shared with a suspended account (S-17, S-18).
PERSON_FLAGGED = "moderation.person_flagged"

ALL_TYPES = frozenset(
    {
        BOOKING_STATUS_CHANGED,
        BOOKING_RATED,
        RENTER_RATED,
        BOOKING_MESSAGE,
        PAYMENT_AUTHORISED,
        PAYMENT_FAILED,
        PAYMENT_CAPTURED,
        PAYMENT_REFUNDED,
        PAYOUT_SENT,
        PROFILE_CREATED,
        PROFILE_DELETED,
        PERSON_SIGNED_OUT,
        REPORT_RECEIVED,
        MODERATION_DECISION,
        OWNER_SUSPENDED,
        OWNER_REINSTATED,
        LISTING_CHANGED,
        PAYOUTS_READY,
        IDENTITY_VERIFIED,
        OWNER_RELIABILITY,
        PERSON_FLAGGED,
    }
)


@dataclass(frozen=True)
class Event:
    id: str
    type: str
    source: str
    occurred_at: str
    data: dict
    # W3C trace context of the request that caused it, so a trace follows the
    # event through the outbox, SNS and SQS into whoever handles it.
    trace: dict | None = None

    def to_json(self) -> str:
        body = {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "occurredAt": self.occurred_at,
            "data": self.data,
        }
        if self.trace:
            body["trace"] = self.trace
        return json.dumps(body)

    @classmethod
    def from_json(cls, raw: str) -> Event:
        d = json.loads(raw)
        return cls(
            id=d["id"],
            type=d["type"],
            source=d["source"],
            occurred_at=d["occurredAt"],
            data=d["data"],
            trace=d.get("trace"),
        )


def event_tables(metadata: MetaData) -> tuple[Table, Table]:
    """The outbox and the processed-events ledger, on a service's own metadata."""
    outbox = Table(
        "outbox",
        metadata,
        Column("id", String(40), primary_key=True),
        Column("type", String(80), nullable=False),
        Column("body", JsonType, nullable=False),
        Column("created_at", UtcDateTime, nullable=False),
        Column("sent_at", UtcDateTime, nullable=True),
        Column("attempts", Integer, nullable=False, default=0),
    )
    # The relay only ever scans unsent rows; a partial index keeps that scan
    # tiny however large the history grows.
    Index("ix_outbox_unsent", outbox.c.created_at, postgresql_where=outbox.c.sent_at.is_(None))
    processed = Table(
        "processed_events",
        metadata,
        Column("event_id", String(40), primary_key=True),
        Column("type", String(80), nullable=False),
        Column("processed_at", UtcDateTime, nullable=False),
    )
    # Every service with events also keeps which sessions ended early (P-24).
    from .guard import revocation_table

    revocation_table(metadata)
    return outbox, processed


# --- producing -------------------------------------------------------------------


class Outbox:
    def __init__(self, table: Table, source: str) -> None:
        self.table = table
        self.source = source

    async def add(self, session: AsyncSession, type_: str, data: dict) -> Event:
        """Record an event in the caller's transaction. Nothing is sent until it
        commits and the relay picks it up."""
        if type_ not in ALL_TYPES:
            raise ValueError(f"unknown event type {type_}")
        now = datetime.now(UTC)
        carrier: dict = {}
        propagate.inject(carrier)  # empty unless tracing is on
        event = Event(
            id=new_id("ev"),
            type=type_,
            source=self.source,
            occurred_at=iso_from_datetime(now),
            data=data,
            trace=carrier or None,
        )
        await session.execute(
            insert(self.table).values(
                id=event.id, type=event.type, body=json.loads(event.to_json()), created_at=now, attempts=0
            )
        )
        return event


class Publisher:
    async def publish(self, events: list[Event]) -> None:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


MAX_ATTEMPTS = 20


def retry_delay(receives: int, base: int = 30, cap: int = 900) -> int:
    """How long a failed message waits before its next try: doubling from 30 s
    to 15 min, jittered. With maxReceiveCount 12 that is about two hours of
    retries (a dependency outage) before the dead-letter queue and its alarm."""
    return int(jittered(min(cap, base * 2 ** max(0, receives - 1))))


def jittered(seconds: float) -> float:
    """Between half and all of ``seconds``, so replicas that failed together
    do not retry together (AWS Builders' Library: backoff with jitter)."""
    return seconds * random.uniform(0.5, 1.0)


class OutboxRelay:
    """Moves committed outbox rows onto the bus."""

    def __init__(
        self, db: Database, table: Table, publisher: Publisher, *, batch_size: int = 100, idle_seconds: float = 1.0
    ) -> None:
        self.db = db
        self.table = table
        self.publisher = publisher
        self.batch_size = batch_size
        self.idle_seconds = idle_seconds
        self._wake = asyncio.Event()

    def wake(self) -> None:
        """Call after a commit that wrote events, so they go out now rather than
        on the next idle tick."""
        self._wake.set()

    async def _once(self) -> int:
        async with self.db.transaction() as s:
            # A row that keeps failing is set aside after MAX_ATTEMPTS so it cannot
            # hold up everything behind it (the log says so each time it fails).
            q = select(self.table.c.id, self.table.c.body).where(
                self.table.c.sent_at.is_(None), self.table.c.attempts < MAX_ATTEMPTS
            )
            q = q.order_by(self.table.c.created_at).limit(self.batch_size)
            if self.db.is_postgres:
                q = q.with_for_update(skip_locked=True)
            rows = (await s.execute(q)).all()
            if not rows:
                return 0
            events = [Event.from_json(json.dumps(r.body)) for r in rows]
            try:
                await self.publisher.publish(events)
            except Exception:
                # Leave them unsent; count the attempt so a poison row is visible.
                log.exception("publishing %d event(s) failed; will retry", len(events))
                await s.rollback()
                async with self.db.transaction() as s2:
                    await s2.execute(
                        update(self.table)
                        .where(self.table.c.id.in_([r.id for r in rows]))
                        .values(attempts=self.table.c.attempts + 1)
                    )
                    aside = await s2.execute(
                        select(self.table.c.id, self.table.c.type).where(
                            self.table.c.id.in_([r.id for r in rows]), self.table.c.attempts >= MAX_ATTEMPTS
                        )
                    )
                    for row in aside:
                        # The alarm on this word (Terraform: outbox-set-aside) pages:
                        # the change committed, its event will not go out by itself.
                        log.error("OUTBOX_SET_ASIDE %s %s after %d attempts", row.id, row.type, MAX_ATTEMPTS)
                raise
            await s.execute(
                update(self.table).where(self.table.c.id.in_([r.id for r in rows])).values(sent_at=datetime.now(UTC))
            )
            return len(rows)

    async def flush(self) -> int:
        """Publish everything pending. Tests call this; so does shutdown."""
        total = 0
        while True:
            n = await self._once()
            total += n
            if n < self.batch_size:
                return total

    async def run(self) -> None:
        backoff = self.idle_seconds
        while True:
            try:
                await self.flush()
                backoff = self.idle_seconds
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - logged in _once; keep the relay alive
                backoff = min(backoff * 2, 30.0)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=jittered(backoff))
            self._wake.clear()


# --- consuming ------------------------------------------------------------------

Handler = Callable[[AsyncSession, Event], Awaitable[None]]


# Sent events are kept a week for investigation. Processed markers must outlive
# anything that could still be redelivered: the dead-letter queue keeps
# messages 14 days, so markers are kept 21.
SENT_RETENTION = timedelta(days=7)
PROCESSED_RETENTION = timedelta(days=21)


async def prune(db: Database, outbox: Table, processed: Table, *, batch: int = 5000) -> int:
    """Delete what is past retention, in small batches so no statement holds
    locks or runs into the statement timeout. Returns rows deleted."""
    now = datetime.now(UTC)
    total = 0
    for table, key, ts, older in (
        (outbox, outbox.c.id, outbox.c.sent_at, now - SENT_RETENTION),
        (processed, processed.c.event_id, processed.c.processed_at, now - PROCESSED_RETENTION),
    ):
        while True:
            async with db.transaction() as s:
                ids = select(key).where(ts.is_not(None), ts < older).limit(batch).scalar_subquery()
                n = (await s.execute(delete(table).where(key.in_(ids)))).rowcount or 0
            total += n
            if n < batch:
                break
    return total


class Dispatcher:
    """Routes an event to its handler exactly once per consumer, in one
    transaction with the handler's own writes."""

    def __init__(self, db: Database, processed: Table, handlers: dict[str, Handler]) -> None:
        self.db = db
        self.processed = processed
        self.handlers = handlers

    @property
    def types(self) -> frozenset[str]:
        return frozenset(self.handlers)

    async def handle(self, event: Event) -> bool:
        """True if the event was handled now, False if it was a redelivery or not
        ours. Raises if the handler failed, so the caller does not acknowledge.

        The processed marker and the handler's writes share one transaction:
        either the event is handled and recorded, or neither. A concurrent
        duplicate blocks on the marker's primary key until the first commits,
        then sees the conflict and skips."""
        handler = self.handlers.get(event.type)
        if handler is None:
            return False
        with _tracer.start_as_current_span(
            f"handle {event.type}", context=propagate.extract(event.trace or {}), kind=trace.SpanKind.CONSUMER
        ):
            return await self._handle(handler, event)

    async def _handle(self, handler: Handler, event: Event) -> bool:
        async with self.db.session() as s:
            try:
                await s.execute(
                    insert(self.processed).values(event_id=event.id, type=event.type, processed_at=datetime.now(UTC))
                )
            except IntegrityError:
                await s.rollback()
                log.info("event %s (%s) already processed; skipping", event.id, event.type)
                return False
            try:
                await handler(s, event)
                await s.commit()
            except BaseException:
                await s.rollback()
                raise
        return True


class Consumer:
    async def run(self) -> None:
        raise NotImplementedError

    async def aclose(self) -> None:
        """Release resources."""


# --- in-memory transport (tests, single process) ----------------------------------


class MemoryBroker(Publisher):
    """Keeps every published event, and hands each to every subscribed
    dispatcher (fan-out, like SNS to several queues)."""

    def __init__(self) -> None:
        self.published: list[Event] = []
        self._subscribers: dict[str, list[Dispatcher]] = defaultdict(list)

    def subscribe(self, dispatcher: Dispatcher) -> None:
        for t in dispatcher.types:
            self._subscribers[t].append(dispatcher)

    async def publish(self, events: list[Event]) -> None:
        for e in events:
            self.published.append(e)
            for d in self._subscribers.get(e.type, []):
                try:
                    await d.handle(e)
                except Exception:  # noqa: BLE001 - mirrors a queue: the publisher is unaffected
                    log.exception("in-memory consumer failed on %s", e.type)

    def of_type(self, type_: str) -> list[Event]:
        return [e for e in self.published if e.type == type_]


# --- AWS transport ---------------------------------------------------------------


def aws_client(service: str, settings: Any, endpoint_url: str = ""):
    """A boto3 client; locally pointed at LocalStack (or ``endpoint_url``)."""
    import boto3
    from botocore.config import Config

    # Adaptive retries back off when AWS throttles (SES, Cognito quotas).
    kwargs: dict[str, Any] = {
        "region_name": settings.aws_region,
        "config": Config(retries={"mode": "adaptive", "max_attempts": 8}, connect_timeout=5, read_timeout=25),
    }
    if endpoint_url or settings.aws_endpoint_url:
        kwargs["endpoint_url"] = endpoint_url or settings.aws_endpoint_url
    return boto3.client(service, **kwargs)


class SnsPublisher(Publisher):
    """Publishes to one topic; the event type rides as a message attribute so
    each queue's subscription filter picks only what its service handles."""

    def __init__(self, topic_arn: str, settings: Any) -> None:
        self.topic_arn = topic_arn
        self._sns = aws_client("sns", settings)

    async def publish(self, events: list[Event]) -> None:
        for i in range(0, len(events), 10):
            chunk = events[i : i + 10]
            entries = [
                {
                    "Id": str(n),
                    "Message": e.to_json(),
                    "MessageAttributes": {"type": {"DataType": "String", "StringValue": e.type}},
                }
                for n, e in enumerate(chunk)
            ]
            result = await asyncio.to_thread(
                self._sns.publish_batch, TopicArn=self.topic_arn, PublishBatchRequestEntries=entries
            )
            if result.get("Failed"):
                raise RuntimeError(f"SNS rejected {len(result['Failed'])} event(s): {result['Failed'][:1]}")


class SqsConsumer(Consumer):
    """Long-polls one queue. Deletes a message only after its handler
    committed; everything else is left for redelivery, then the DLQ."""

    def __init__(self, queue_url: str, dispatcher: Dispatcher, settings: Any, *, wait_seconds: int = 20) -> None:
        self.queue_url = queue_url
        self.dispatcher = dispatcher
        self.wait_seconds = wait_seconds
        self._sqs = aws_client("sqs", settings)

    async def _poll(self) -> None:
        resp = await asyncio.to_thread(
            self._sqs.receive_message,
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self.wait_seconds,
            MessageSystemAttributeNames=["ApproximateReceiveCount"],
        )
        # Concurrently, so the last message of a batch is not still waiting its
        # turn when its visibility timeout runs out (and counted as a failed
        # receive towards the dead-letter queue without ever being tried).
        await asyncio.gather(*(self._one(m) for m in resp.get("Messages", [])))

    async def _one(self, msg: dict) -> None:
        try:
            event = Event.from_json(_unwrap_sns(msg["Body"]))
            await self.dispatcher.handle(event)
        except Exception:  # noqa: BLE001
            receives = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", "1"))
            delay = retry_delay(receives)
            log.exception(
                "handling message %s failed (attempt %d); retrying in %ds", msg.get("MessageId"), receives, delay
            )
            with contextlib.suppress(Exception):
                await asyncio.to_thread(
                    self._sqs.change_message_visibility,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                    VisibilityTimeout=delay,
                )
            return
        await asyncio.to_thread(self._sqs.delete_message, QueueUrl=self.queue_url, ReceiptHandle=msg["ReceiptHandle"])

    async def run(self) -> None:
        while True:
            try:
                await self._poll()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("polling %s failed; retrying", self.queue_url)
                await asyncio.sleep(jittered(2))


def _unwrap_sns(body: str) -> str:
    """Raw message delivery is on in Terraform, so the body is the event. If a
    subscription ever lacks it, the event is inside SNS's envelope instead."""
    d = json.loads(body)
    if isinstance(d, dict) and d.get("Type") == "Notification" and "Message" in d:
        return d["Message"]
    return body


# --- wiring ---------------------------------------------------------------------

_memory_broker: MemoryBroker | None = None


def memory_broker() -> MemoryBroker:
    """The process-wide in-memory broker, so services built in one test process
    can talk to each other the way they would through SNS."""
    global _memory_broker
    if _memory_broker is None:
        _memory_broker = MemoryBroker()
    return _memory_broker


def reset_memory_broker() -> MemoryBroker:
    global _memory_broker
    _memory_broker = MemoryBroker()
    return _memory_broker


def make_publisher(settings: Any) -> Publisher:
    url: str = settings.event_bus_url
    if url.startswith("memory://"):
        return memory_broker()
    if url.startswith("sns://"):
        return SnsPublisher(url.removeprefix("sns://"), settings)
    raise ValueError(f"unsupported event bus url: {url}")


def make_consumer(settings: Any, dispatcher: Dispatcher) -> Consumer | None:
    """The consumer for this service, or None when it handles nothing. With
    ``memory://`` the dispatcher subscribes to the in-process broker and there
    is nothing to poll."""
    if not dispatcher.handlers:
        return None
    if settings.event_bus_url.startswith("memory://"):
        memory_broker().subscribe(dispatcher)
        return None
    if not settings.event_queue_url:
        raise ValueError(f"{settings.service_name} handles events but EVENT_QUEUE_URL is not set")
    return SqsConsumer(settings.event_queue_url, dispatcher, settings)
