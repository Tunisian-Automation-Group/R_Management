# 0003. Transactional outbox → SNS → one SQS queue per consumer

## Context
Services publish events inside the database transaction but before commit,
so a rollback announces something that never happened and a crash after
commit loses the event. The Redis Streams consumer acknowledges a message
even when its handler failed, never reclaims a dead consumer's pending
messages, and delivers each message to one instance per group — so matching's
cache invalidation reaches one replica in N.

## Decision
- **Outbox.** A service writes its event to an `outbox` table in the same
  transaction as the change. A relay in every replica claims unsent rows with
  `FOR UPDATE SKIP LOCKED`, publishes, and marks them sent. At-least-once,
  never phantom.
- **Transport.** One SNS topic (`cappy-events`); every consuming service owns
  one SQS queue subscribed with a filter policy on the event type, and a
  dead-letter queue after five receives.
- **Consumers are idempotent.** Each keeps a `processed_events` table keyed by
  event id; a redelivery is a no-op.
- **In tests** an in-memory bus with the same interface.

## Rejected
- *Fix Redis Streams* (retry counts, `XAUTOCLAIM`, a DLQ stream, `MAXLEN`).
  Possible, but it rebuilds what SQS gives for free, and adds a stateful
  cluster to run.
- *EventBridge.* Fine, but SNS+SQS is simpler, cheaper per message, and has
  native filtering and DLQs for exactly this fan-out.
- *Kafka/MSK.* Ordered replayable logs are not something this domain needs.

## Consequences
Redis leaves the stack entirely (nothing else needed it; ADR 0001 removes the
world cache). Events are at-least-once and unordered across types, which every
consumer is written for.
