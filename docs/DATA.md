# Data

The services, their tables, the events between them, who reads what, how
long things are kept, and where personal data lives. This is a living doc
(see [`CLAUDE.md`](../CLAUDE.md)). It describes the code **as committed at
`ac716b5`**. Changes that were still in the working tree when it was written
(for example `notifications/migrations/versions/0006_device_install.py` and
`cappy_common/guard.py`) are not described here.

References are `path:line` from the repository root. **PII** marks personal
data. **Sensitive** marks data that needs extra care: government ID and
biometrics, payment-card identifiers, precise addresses and access codes, and
free text that may contain any of these.

---

## 1. Services and their databases

One Aurora PostgreSQL 16 Serverless v2 cluster runs per cell. It has a writer
and a reader in different AZs (`infra/platform/data.tf:56-93`). Each service
that owns data has **its own database and its own role**, and the role owns
that database and nothing else. The migrate task creates them
(`backend/libs/cappy_common/cappy_common/migrations.py:89-113`, database list at
`infra/platform/data.tf:5`). No service can read another's tables. Anything
that crosses a boundary goes through an event (§3) or an `/internal/*` call (§4).

| Service | Database | Reader URL | Consumes events | Background loops |
|---|---|---|---|---|
| gateway | none | none | none | none (HTTP edge, routes `/api/*`, blocks `/internal/*`: `backend/services/gateway/gateway/routing.py:4`) |
| matching | none (stateless; asks catalog and booking) | none | none | none |
| catalog | `catalog` | yes | yes | orphan-photo sweep (`backend/services/catalog/catalog/jobs.py:20-42`) |
| booking | `booking` | yes | yes | expiry, auto-complete and review sweeps (`backend/services/booking/booking/jobs.py:18-54`) |
| payments | `payments` | no | yes | Stripe reconciliation (`backend/services/payments/payments/jobs.py:29-63`) |
| notifications | `notifications` | no | yes | none |

Every service that has a database also runs the outbox relay, its SQS consumer,
and an hourly prune of `outbox` and `processed_events`
(`backend/libs/cappy_common/cappy_common/runtime.py:124-132`, `:157-159`).

### Writer and reader: `Tx` and `ReadTx`

- **`Tx`** (`runtime.py:182-199`) gives one transaction per request, on the
  **writer**. It commits *before* the response is sent (`scope="function"`)
  and then wakes the outbox relay, so a request's events go out at once.
  Every route that writes uses it. Routes that must read their own writes use
  it too.
- **`ReadTx`** (`runtime.py:202-214`) is a `SET TRANSACTION READ ONLY` session
  on the **reader** endpoint. It is only for reads that can tolerate a few
  milliseconds of replica lag. It is configured by `DATABASE_READ_URL`
  (`runtime.py:101-105`). Without that variable, reads go to the writer.
  Terraform gives a reader URL to catalog and booking only
  (`infra/platform/data.tf:113-127`, `infra/platform/ecs.tf:74`).
  - catalog: `/districts`, `/cities`, `/districts/nearest`, `/owners/{id}`,
    `/listings/{id}`, `/listings/{id}/reviews`, `/search`, and
    `/internal/candidates`, `/internal/listings/{id}/context` and
    `/internal/owners/{id}` (`backend/services/catalog/catalog/routes.py:48`, `:374-442`, `:667-723`).
  - booking: `/internal/busy` only (`backend/services/booking/booking/routes.py:575-582`).
    A window booked a moment ago may still look free there. The exclusion
    constraint (§2.2) then refuses the booking.
- An alarm fires when the reader is more than 1 s behind
  (`infra/platform/data.tf:178-191`).
- Connections are sized against Aurora's limit
  (`infra/platform/data.tf:158-176`). Each task gets a pool of 5 plus 10
  overflow, a 5 s statement timeout and a 30 s idle-in-transaction timeout
  (`backend/libs/cappy_common/cappy_common/db.py:64-117`).

### Tables every database has

| Table | Purpose | Key | Retention |
|---|---|---|---|
| `outbox` | Events written in the same transaction as the change they describe (ADR 0003) | `id`. Partial index `ix_outbox_unsent` on `created_at WHERE sent_at IS NULL` (`events.py:150-162`) | Sent rows are kept **7 days** (`events.py:311`). A row that fails 20 times is set aside and kept until someone deals with it (`events.py:213`, `:249-253`). **PII:** the body is the whole event payload (§3) |
| `processed_events` | Ids of events this consumer has handled, for idempotency. Payments also stores Stripe webhook event ids here (`backend/services/payments/payments/routes.py:337-343`) | `event_id` | **21 days**, which outlives the DLQ's 14 (`events.py:312`) |
| `idempotency_keys` (catalog, booking) | `Idempotency-Key` replay for creating POSTs | (`principal`, `key`) (`backend/libs/cappy_common/cappy_common/idempotency.py:29-39`) | **Kept forever** (`idempotency.py:30`). **PII:** `response` is the first answer as JSON, for example a report's details or a listing |

---

## 2. Tables per service

Every instant is a `timestamptz` (`db.py:43-61`). Every constraint name is
deterministic (`db.py:26-32`). Unless a row says otherwise, a table has
**no time-based retention**: rows stay until account deletion changes them
(§5.4) or for ever.

### 2.1 catalog (`backend/services/catalog/catalog/tables.py`)

| Table | Purpose and key columns | Constraints and indexes that matter | Personal data | Retention |
|---|---|---|---|---|
| `districts` (`:32-39`) | Reference places: `name` PK, `city`, `metro`, `country`, `lat`, `lng` | `ix_districts_lat_lng` (`:130`), `metro` index | none | Reference data |
| `owners` (`:42-75`) | Every signed-up person (id = Cognito `sub`): `name`, `initials`, `kind` (person/business), `district`, `verified`, rating counters, `renter_*`, `joined_year`, `deleted_at`, `suspended_at`, `business` JSON, `adult_confirmed_at`, `cancellation_rate` | PK `id`; FK `district` → districts | **PII:** `name`, `initials`, `district` (coarse location), `business` (legal name, **address**, register number, VAT ID: `backend/libs/cappy_common/cappy_common/models.py:117-125`), `adult_confirmed_at`, reliability and suspension | On deletion: the name becomes "Former member", `business` is nulled, and the row stays as a shell (§5.4) |
| `listings` (`:78-105`) | `owner_id`, `category`, `mode`, `title`, `blurb`, `district`, `instructions`, `address`, `moderated_at`, `held_at`, `rules`, `photos`, `active`, `spec` JSON, `deleted_at` (soft delete) | `ix_listings_search` (`:109`); partial `ix_listings_live` and `ix_listings_live_district` `WHERE deleted_at IS NULL AND active` (`:112-117`, `:125-129`); `ix_listings_owner_created` (`:123`); trigram GIN `ix_listings_title_trgm`, `ix_listings_blurb_trgm`, created only in the migration (`catalog/migrations/versions/0001_initial_catalog_schema.py:153-154`; allowed list `tables.py:122`) | **Sensitive:** `address` (private until a booking is accepted: `:88-90`) and `instructions` (door codes, where the key is; never public: `backend/services/catalog/catalog/repository.py:86-98`). `photos` | Soft-deleted for ever; `address` is nulled on account deletion |
| `slots` (`:133-141`) | Idle windows: `listing_id`, `start`, `end`, `hours_usable` | FK cascade; `ix_slots_listing_end` (`:145`) | none | Kept with the listing |
| `reviews` (`:148-162`) | Renter → owner reviews: `rv_<bookingId>` PK, `author`, `initials`, `author_id`, `rating`, `on_time`, `text`, `tags`, `at` | `ix_reviews_listing_at` (`:165`); `owner_id` index | **PII:** `author` (shown as "Ada L.": `backend/services/catalog/catalog/handlers.py:14-17`), `author_id`, `text` (free text) | Author anonymised on deletion; the text stays |
| `saved_listings` (`:168-177`) | Hearts: (`user_id`, `listing_id`) PK, `saved_at` | `ix_saved_user_at` | **PII:** what someone shortlisted | Deleted with the account |
| `payable_owners` (`:180-188`) | Payments' latest word on `ready`, with `as_of` (older news loses) | PK `owner_id` | Pseudonymous | Deleted with the account |
| `reports` (`:191-210`) | DSA Art. 16 notices, plus system flags: `target_type`, `target_id`, `reason`, `details`, `reporter_id`, `reporter_email`, `status`, the decision, `statement`, `statement_of_reasons` | `ix_reports_status_created` (`:213`) | **PII:** `reporter_email` (people without an account), `reporter_id`, `details` (free text about someone) | **Not touched by deletion; no retention** (§5.5) |
| `moderation_actions` (`:216-231`) | Audit trail: `actor_id`, `action`, target, `report_id`, `statement`, `statement_of_reasons`, `at` | `ix_moderation_actions_at` | **PII:** staff ids, statements about people | Kept for ever (audit) |
| `media` (`:234-248`) | Uploaded photos (content hash) per owner: (`name`, `owner_id`) PK, `bytes`, `width`, `height`, `used` | `owner_id` index | **PII:** photos can show people and places; hand-over evidence is stored here too | Unused uploads swept after **1 day** (`jobs.py:16-37`). **Used photos are never deleted** (§5.5) |
| `outbox`, `processed_events`, `idempotency_keys` | §1 | | | |

### 2.2 booking (`backend/services/booking/booking/tables.py`)

| Table | Purpose and key columns | Constraints and indexes that matter | Personal data | Retention |
|---|---|---|---|---|
| `bookings` (`:36-82`) | `requester_id`, `owner_id`, `listing_id`, `status`, `window_start`/`window_end`, `expires_at`, `amount` (minor units), `currency`, `requirement`, `match` (quote), `listing_snapshot`, `decline_reason`, `outcome` (the renter's review), `renter_rating`, `refund_amount`, `rated_at`, `reviews_published_at`, `idempotency_key`, `request_hash`, `handover`, `no_show`, `card_fingerprint` | **`ex_bookings_no_double_booking`**: `EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end, '[)') WITH &&) WHERE status IN ('awaiting_payment','requested','accepted','active','completed','disputed')` (`booking/migrations/versions/0003_completed_bookings_keep_their_window.py:21-31`; `btree_gist` in `0001_initial_booking_schema.py:21`; ADR 0004). Violations become 409 (`backend/services/booking/booking/routes.py:204-214`). `uq_bookings_requester_idempotency` and `ck_bookings_window_forward` (`:79-82`). Indexes `ix_bookings_requester_created`, `ix_bookings_owner_created`, `ix_bookings_listing_window`, `ix_bookings_status_expires`, `ix_bookings_status_window_end` and `ix_bookings_card_fingerprint` (`:157-164`) | **PII:** both parties' ids; `listing_snapshot.ownerName` and `ownerBusiness` (`routes.py:183-193`); `handover` (**sensitive**: address and instructions copied at accept, `routes.py:111-113`); `outcome.note` and `decline_reason` (free text); **sensitive:** `card_fingerprint` | Kept for ever as the financial record. Account deletion does not change it (§5.4) |
| `booking_messages` (`:85-102`) | Chat per booking: `sender_id`, `body` (contact details masked before acceptance), `unmasked` (the words as written), `flagged` | FK cascade; `ix_booking_messages_booking_at` | **PII, sensitive:** free text, phone numbers and emails in `unmasked` | On deletion the sender's words are replaced (§5.4) |
| `blocks` (`:105-111`) | (`blocker_id`, `blocked_id`) PK | | **PII** (who blocked whom) | Deleted with either account |
| `verified_people` (`:114-119`) | Copy of payments' identity outcome | PK `person_id` | **PII:** "ID-checked" | Deleted with the account |
| `suspended` (`:122-127`) | Copy of moderation's suspension | PK `person_id` | **PII** | Kept after deletion (fraud: card links, S-17). Removed on reinstatement |
| `booking_evidence` (`:130-141`) | Hand-over and return photos: `by`, `stage`, `photos` (URLs), `note` | `booking_id` index | **PII:** photos (public CloudFront URLs, P-27) and `note` | Kept for ever (disputes) |
| `booking_transitions` (`:144-154`) | Every status change: `from_status`, `to_status`, `by`, `at` | `booking_id` index | Pseudonymous ids | Kept for ever (audit and reliability, `backend/services/booking/booking/repository.py:188-233`) |
| `outbox`, `processed_events`, `idempotency_keys` | §1 | | | |

Booking states: `HOLDING` keeps the window and `OPEN` blocks account deletion
(`backend/services/booking/booking/state.py:44-51`).

### 2.3 payments (`backend/services/payments/payments/tables.py`)

| Table | Purpose and key columns | Constraints | Personal data | Retention |
|---|---|---|---|---|
| `payments` (`:21-44`) | One per booking: `booking_id` PK, `intent_id`, `requester_id`, `owner_id`, `amount`, `owner_net`, `currency`, `status` (created → authorised → captured → transferred, or cancelled or refunded), `charge_id`, `transfer_id`, `refund_id`, `chargeback_at`, `card_fingerprint` | `intent_id` unique; indexes on requester and owner | Pseudonymous ids; **sensitive:** `card_fingerprint`. The card itself stays with Stripe | Kept for ever (financial record) |
| `identities` (`:47-56`) | Stripe Identity outcome: `person_id` PK, `session_id`, `status`, `verified_at` | `session_id` unique | **PII:** that an ID check happened and how it went. The document and selfie stay with Stripe | Deleted with the account (the Stripe session is not: §5.5) |
| `invoices` (`:59-80`) | The platform's fee invoice to an owner: `number` PK, `booking_id` unique, `owner_id`, `net`/`vat_rate_bps`/`vat`/`gross`, `currency`, `issued_at`, `title`, `service_start`/`end`, `recipient_name`, `recipient_address`, `recipient_vat_id` | Never updated once issued (GoBD) | **PII:** the recipient's name, address and VAT ID | **10 years by law** (GoBD / § 147 AO). The code keeps them for ever and nothing purges them after 10 years |
| `invoice_counters` (`:83-89`) | `year` PK, `last`, taken under a row lock | | none | Kept |
| `connect_accounts` (`:92-101`) | An owner's Stripe Express account: `owner_id` PK, `account_id`, `payouts_enabled`, `details_submitted` | `account_id` unique | Pseudonymous. Identity and bank details stay with Stripe | Deleted with the account (the Stripe account is not) |
| `outbox`, `processed_events` | §1 | | | |

### 2.4 notifications (`backend/services/notifications/notifications/tables.py`)

| Table | Purpose and key columns | Personal data | Retention |
|---|---|---|---|
| `devices` (`:21-30`) | Push devices: `token` PK (APNs or FCM), `user_id`, `platform`, `endpoint` (SNS platform endpoint ARN), `created_at`. At most 10 per person (`backend/services/notifications/notifications/routes.py:27`, `:63-72`) | **PII:** device token | Removed on sign-out, sign-out-everywhere, a dead endpoint, or account deletion |
| `inbox` (`:33-52`) | The bell: an id derived from (event, recipient, key), `user_id`, `kind`, `params`, `title`, `body`, `link`, `at`, `read_at`. Index `ix_inbox_user_at` | **PII:** what happened to someone; listing titles | **No retention**; deleted with the account |
| `notification_prefs` (`:55-62`) | `user_id` PK, `prefs` JSON | Preferences | Deleted with the account |
| `outbox`, `processed_events` | §1. Notifications publishes nothing, but the runtime creates the table anyway | | |

Email addresses are **not stored here**. Each time a message goes out,
notifications looks the address and locale up in Cognito
(`backend/services/notifications/notifications/mail.py:38-59`), and mails only
verified addresses (`mail.py:57-58`).

---

## 3. Events

### 3.1 Transport, ordering, idempotency

- **Outbox → SNS → one SQS queue per consumer** (ADR 0003). `Outbox.add`
  writes the event in the caller's transaction (`events.py:181-202`) and
  refuses types that are not in the catalogue (`events.py:84-109`, `:184-185`).
  The relay in every replica claims unsent rows with `FOR UPDATE SKIP LOCKED`,
  publishes batches of 10 and marks them sent (`events.py:247-277`,
  `:436-459`). Delivery is **at least once**: a crash after the publish sends
  the event again.
- **Envelope:** `{id, type, source, occurredAt, data, trace?}` (`events.py:112-145`).
  `type` is also a message attribute, and each queue's filter policy uses it
  (`infra/modules/messaging/main.tf:64-71`). Raw delivery is on.
- **Ordering:** standard SNS and SQS, so **no ordering** between events or
  within one type. Consumers are written for that:
  - catalog ignores a `payment.payouts_ready` older than the state it has
    (`asOf`: `backend/services/catalog/catalog/repository.py:211-217`);
  - booking's handlers only apply transitions the state machine allows from
    the current status (`backend/services/booking/booking/handlers.py:40-53`);
  - payments raises `NotReady` for a `completed` that arrives before the
    capture, so it is retried (`backend/services/payments/payments/handlers.py:143-146`);
  - catalog counts a rating once per booking (`catalog/handlers.py:38-41`).
- **Idempotency:** the `Dispatcher` inserts the event id into `processed_events`
  **in the same transaction** as the handler's writes. A duplicate hits the
  primary key and is skipped (`events.py:334-379`). Notifications is the
  exception by design: it sends the mail before the commit, so a crash can
  send it twice (`backend/services/notifications/notifications/handlers.py:1-6`).
  Its inbox rows use a deterministic id, so a repeat never shows twice
  (`handlers.py:194-213`). Payments' Stripe calls carry idempotency keys
  (`payments/handlers.py:10-12`).
- **Failures are never acknowledged.** The consumer deletes a message only
  after its handler has committed. Otherwise it resets the message's
  visibility with an exponential, jittered backoff from 30 s to 15 min
  (`events.py:216-226`, `:485-503`).
- **DLQs:** each consumer has a queue `cappy-<env>-<service>` with a 120 s
  visibility timeout and `maxReceiveCount = 12`, about 2 h of retries, and a
  DLQ `…-dlq` that keeps messages 14 days (`infra/modules/messaging/main.tf:29-47`;
  local copy `local/bootstrap.py:78-90`). There is one alarm per DLQ on any
  message (`infra/platform/observability.tf:74-88`) and one on queue age over
  5 min (`:90-104`). **Drift:** ADR 0003, the `events.py` docstring
  (`events.py:17-18`) and the runbook (`docs/runbook.md:55`) still say "five
  receives".
- **Redrive** (`docs/runbook.md:55`): read the DLQ, fix the cause, then run
  `aws sqs start-message-move-task --source-arn <dlq-arn>`. This is safe
  because every handler is idempotent, as long as it happens within 21 days,
  the `processed_events` retention.
- **Analytics:** a second, **unfiltered** SNS subscription copies **every**
  event to Firehose → S3, kept 730 days (`infra/platform/analytics.tf:85-91`, `:18-33`).
  Any personal data in a payload therefore lands in the lake (P-6).
- **Stuck outbox rows** (20 failed publishes) have no alarm, only a log line (`events.py:263-273`).

### 3.2 Catalogue

Consumers come from the subscriptions in `infra/platform/data.tf:6-11` (the
same list is in `local/bootstrap.py:30-49`). They match each service's handler
map: catalog `backend/services/catalog/catalog/main.py:37-43`, booking
`backend/services/booking/booking/handlers.py:134-142`, payments
`backend/services/payments/payments/handlers.py:161`, notifications
`backend/services/notifications/notifications/handlers.py:165-172`. Every
event also goes to analytics. **PII** marks fields that are more than a
pseudonymous id. Ids (`sub`s) are pseudonymous personal data everywhere.

| Event | Producer (file:line) | Consumers | Payload (PII marked) |
|---|---|---|---|
| `booking.status_changed` | booking: `booking/repository.py:170`, `:180` (built at `:73-93`) | payments, notifications | `bookingId`, `from`, `to`, `by`, `requesterId`, `ownerId`, `listingId`, `title`, **`ownerName` (PII)**, **`ownerBusiness` (PII: legal name, address, register number, VAT ID)**, `amount`, `currency`, `refundAmount`, `noShow`, `windowStart`, `windowEnd`, `expiresAt` |
| `booking.rated` | booking: `repository.py:321-334` | catalog | `bookingId`, `ownerId`, `listingId`, `requesterId`, `outcome` {`quality`, `onTime`, **`note` (PII: free text)**, `tags`}, `at`, `ratedAt` |
| `booking.renter_rated` | booking: `repository.py:336-345` | catalog | `bookingId`, `renterId`, `ownerId`, `quality` |
| `booking.message` | booking: `booking/messages.py:157-161` | notifications | `bookingId`, `senderId`, `recipientId`, `title` (never the message text) |
| `booking.owner_reliability` | booking: `repository.py:218-222` | catalog | `ownerId`, `rate`, `bookings`, `failures` |
| `moderation.person_flagged` | booking: `repository.py:225-233`, `booking/handlers.py:70-78` | catalog | `personId`, `reason`, **`details` (free text naming a booking and a suspended account)** |
| `payment.authorised` | payments: `payments/routes.py:102-104`; reconciliation `payments/jobs.py:51` (no fingerprint) | booking | `bookingId`, **`cardFingerprint` (sensitive)** |
| `payment.failed` | payments: `payments/handlers.py:72` | booking | `bookingId`, `ownerId`, `requesterId`, `stage` |
| `payment.captured` | payments: `handlers.py:75` | none (analytics only) | `bookingId`, `ownerId`, `requesterId`, `amount`, `currency` |
| `payment.refunded` | payments: `handlers.py:87` | none (analytics only) | the same |
| `payment.payout_sent` | payments: `handlers.py:106`, `:133` | notifications | the same (the owner's part) |
| `payment.identity_verified` | payments: `routes.py:250` | booking | `personId` |
| `payment.payouts_ready` | payments: `routes.py:85-89`; dev CLI `payments/cli.py:80` | catalog | `ownerId`, `ready`, `asOf` |
| `profile.created` | catalog: `catalog/routes.py:330` | none (analytics only) | `ownerId`, `district` |
| `profile.deleted` | catalog: `routes.py:355` | booking, payments, notifications | `ownerId` |
| `listing.changed` | catalog: `routes.py:510`, `:541`, `:571-573`, `:593`; `catalog/moderation.py:259`, `:509` | booking (acts on `removed` only: `booking/handlers.py:83-93`) | `listingId`, `change` (created, updated, paused, resumed, removed, approved) |
| `moderation.report_received` | catalog: `moderation.py:187-196` | notifications | `reportId`, `reporterId`, **`reporterEmail` (PII)**, `targetType` |
| `moderation.decision` | catalog: `moderation.py:354-369`, `:396-407`, `:419-430` | notifications | `reportId?`, `action`, `targetType`, `targetId`, `affectedId`, `reporterId`, **`reporterEmail` (PII)**, **`statement` (free text)**, `statementOfReasons` |
| `moderation.owner_suspended` | catalog: `moderation.py:348`, `:418` | booking | `ownerId` |
| `moderation.owner_reinstated` | catalog: `moderation.py:445` | booking | `ownerId` |
| `booking.requested`, `booking.created` | **declared but never produced** (`events.py:52`, `:59`) | none | dead constants |

Notifications reads a `timeZone` field on `booking.status_changed`
(`notifications/handlers.py:57`). No producer sends it.

### 3.3 Producer → consumer matrix

| Producer ↓ / consumer → | catalog | booking | payments | notifications | analytics only |
|---|---|---|---|---|---|
| **catalog** | – | `listing.changed`, `moderation.owner_suspended`, `moderation.owner_reinstated`, `profile.deleted` | `profile.deleted` | `profile.deleted`, `moderation.report_received`, `moderation.decision` | `profile.created` |
| **booking** | `booking.rated`, `booking.renter_rated`, `booking.owner_reliability`, `moderation.person_flagged` | – | `booking.status_changed` | `booking.status_changed`, `booking.message` | – |
| **payments** | `payment.payouts_ready` | `payment.authorised`, `payment.failed`, `payment.identity_verified` | – | `payment.payout_sent` | `payment.captured`, `payment.refunded` |
| **notifications** | – | – | – | – | – |

---

## 4. Who reads what across services (`/internal/*`)

Every `/internal/*` route requires `X-Internal-Token`
(`backend/libs/cappy_common/cappy_common/auth.py:188`), and the gateway never
forwards `/internal/*` (`gateway/routing.py:4`). All services share one token
(`infra/platform/data.tf:138-150`, `ecs.tf:72`), so any service could call any
of these routes. P-10 tracks per-caller credentials.

| Caller → callee | Route | What crosses | Caller code | Callee code |
|---|---|---|---|---|
| matching → catalog | `POST /internal/candidates` | listings, owners, slots and districts for a search (ReadTx) | `backend/services/matching/matching/clients.py:46` | `catalog/routes.py:667-679` |
| matching → catalog | `GET /internal/listings/{id}/context` | one listing's world (ReadTx) | `matching/clients.py:51-52` | `catalog/routes.py:682-686` |
| matching → booking | `POST /internal/busy` | taken intervals (ReadTx) | `matching/clients.py:65` | `booking/routes.py:575-582` |
| booking → matching | `POST /internal/match-for-offer` | the quote, listing and owner (including **owner name and business**) for a new booking | `backend/services/booking/booking/clients.py:72` | `backend/services/matching/matching/routes.py:233` |
| booking → catalog | `GET /internal/listings/{id}/handover` | **address and instructions (sensitive)**, copied into `bookings.handover` at accept | `booking/clients.py:57` | `catalog/routes.py:713-718` |
| booking → catalog | `POST /internal/media/evidence` | marks evidence photos as used (never swept) | `booking/clients.py:60` | `catalog/routes.py:694-705` |
| booking → payments | `POST /internal/intents` | booking id, parties, amount, owner net, currency → client secret | `booking/clients.py:91` | `backend/services/payments/payments/routes.py:111` |
| catalog → booking | `GET /internal/people/{p}/open` | open bookings count, and until when (account deletion) | `backend/services/catalog/catalog/clients.py:57` | `booking/routes.py:519-523` |
| catalog → booking | `GET /internal/people/{p}/export` | bookings, messages sent, evidence (data export) | `catalog/clients.py:61` | `booking/routes.py:550-572` |
| catalog → booking | `GET /internal/stats/active-people` | a count (DSA stats) | `catalog/clients.py:65` | `booking/routes.py:530-535` |
| catalog → payments | `GET /internal/people/{p}/open` | pending payouts (account deletion) | `catalog/clients.py:46` | `payments/routes.py:283-292` |
| catalog → payments | `GET /internal/people/{p}/export` | payout account, identity status, invoices, payments | `catalog/clients.py:43` | `payments/routes.py:295-326` |
| catalog → notifications | `GET /internal/people/{p}/export` | inbox items and settings | `catalog/clients.py:85` | `backend/services/notifications/notifications/routes.py:159-170` |
| support (runbook) → booking | `POST /internal/bookings/{id}/resolve` | settles a dispute. Staff normally use `/admin/bookings/{id}/resolve` | `docs/runbook.md` | `booking/routes.py:493-510` |
| no caller | `GET /internal/people/{p}/bookings` | superseded by `/export` | none (tests only) | `booking/routes.py:544-547` |
| no caller | `GET /internal/owners/{id}` | an owner (the seam P-6 proposes) | none | `catalog/routes.py:721-723` |

Services also call out to AWS and Stripe directly:

- notifications → Cognito `AdminGetUser`/`ListUsers` (email and locale) and `AdminUserGlobalSignOut` (`notifications/mail.py:38-90`);
- notifications → SES `SendEmail` (`mail.py:93-108`);
- notifications → SNS Mobile Push (`push.py:39-50`);
- catalog → S3 and CloudFront invalidations (`catalog/media.py:151`, `catalog/moderation.py:228-250`);
- payments → Stripe (`payments/provider.py`).

---

## 5. Personal data map

### 5.1 Where each category lives

| Category | Our stores | Processors |
|---|---|---|
| **Identity** (account, `sub`, name) | Cognito user pool (email as username: `infra/platform/identity.tf:5-8`); `catalog.owners.name`/`initials`; copies in `bookings.listing_snapshot.ownerName`, `reviews.author`, `invoices.recipient_name`, and in events (`booking.status_changed.ownerName`) | Cognito |
| **Contact** (email, business address, VAT ID) | Cognito `email`, `email_verified`, `locale` (`identity.tf:59-84`); `owners.business`; `listing_snapshot.ownerBusiness`; `invoices.recipient_*`; `reports.reporter_email`; events `reporterEmail` and `ownerBusiness`; SES account suppression list for bounces and complaints (`infra/platform/email.tf:50-51`) | Cognito, SES |
| **Messages** | `booking_messages.body`/`unmasked`; `bookings.outcome.note`, `decline_reason`; `reviews.text`; `reports.details`; `booking_evidence.note`; free text in `moderation.decision.statement` and `booking.rated.outcome.note` | none (the `booking.message` event carries no text) |
| **Photos** | S3 media bucket, content-addressed, versioned, old versions expire after 30 days (`infra/platform/storage.tf:10-47`); `catalog.media`; `listings.photos`; `booking_evidence.photos`; `listing_snapshot.photo` | S3, CloudFront (a year of immutable caching, ADR 0007) |
| **ID checks** | Outcome only: `payments.identities`, `booking.verified_people`, `payment.identity_verified`. The document and selfie stay at Stripe (`payments/tables.py:47-49`) | Stripe Identity |
| **Payments** | `payments.payments`, `invoices`, `connect_accounts`; `bookings.amount`/`refund_amount`; **card fingerprints** in `payments.card_fingerprint`, `bookings.card_fingerprint` and `payment.authorised` | Stripe (cards, Connect KYC and bank details) |
| **Location** | `owners.district`; `listings.address` (private) and `district`; `bookings.handover.address`; `profile.created.district`. `GET /districts/nearest?lat&lng` does not store the coordinates (`catalog/routes.py:388-395`); the web keeps the chosen district in `localStorage` (`web/src/app/store.tsx:79`, `:97`) | none (Amazon Location is planned, M-7) |
| **Device tokens** | `notifications.devices.token` and `endpoint`; SNS platform endpoints | SNS Mobile Push → APNs (Apple) and FCM (Google) |
| **Analytics** | S3 analytics lake: every event, gzipped JSON, 730 days, Glacier after 90 (`infra/platform/analytics.tf`); Athena `cappy_events`. `docs/analytics.md` says events "carry ids, never names or emails", which is **false today** (P-6) | Firehose, S3, Athena |
| **Logs** | CloudWatch, 90 days in prod and 14 elsewhere (`infra/platform/ecs.tf:122-126`); client crash reports log free text (P-34); WAF sampled requests (P-20) | CloudWatch, WAF (us-east-1) |
| **On the device** | refresh token (`web/src/data/auth.ts:87-109`), signed-in `sub`, drafts and flags (`web/src/app/device.ts`), language | none |
| **Backups** | Aurora automated backups: 14 days in prod, 3 elsewhere; a final snapshot on destroy in prod (`infra/platform/data.tf:68-73`) | RDS |

### 5.2 Processors

| Processor | What it holds | Region today |
|---|---|---|
| **Amazon Cognito** | email, password hash, MFA, locale, sign-in history (threat protection when on: `identity.tf:10-17`) | eu-central-1 |
| **Stripe** (Payments, Connect Express, Identity) | cards, charges, refunds, transfers; owners' KYC, bank and tax data; ID documents and selfies | Stripe's EU and US infrastructure (one DE platform account) |
| **Amazon SES** | every transactional email in transit; the suppression list | eu-central-1 |
| **SNS Mobile Push → APNs and FCM** | device tokens, notification title and body | SNS in eu-central-1; Apple and Google in the US |
| **CloudFront and WAF** | the web bundle, photos (cached at the edge, `PriceClass_100`: `infra/platform/edge.tf:448`), API responses, request metadata; WAF in us-east-1 | global edge; us-east-1 |
| **Aurora, S3, Firehose, Athena, CloudWatch** | everything above | eu-central-1 |

The DPAs, records of processing and the DPIA for ID checks are business
tasks (G-B3, P-17, P-30).

### 5.3 Export coverage (`GET /me/export`)

`catalog/routes.py:359-371` assembles one JSON file from:

- catalog `repository.export` (`catalog/repository.py:194-209`);
- booking `/internal/people/{p}/export` (`booking/routes.py:550-572`);
- payments `/internal/people/{p}/export` (`payments/routes.py:295-326`);
- notifications `/internal/people/{p}/export` (`notifications/routes.py:159-170`).

| Data | Exported? |
|---|---|
| Profile (name, kind, district, business, ratings) | yes (`profile`) |
| Listings, including private address and instructions | yes (`listings`, `private=True`) |
| Saved listings | yes |
| Reviews written | yes (rating, text, date) |
| Photos | **names only**, not the files (`repository.py:208`) |
| Bookings (both sides) | yes (`bookings`, as the viewer sees them) |
| Messages sent | yes, the unmasked words (`booking/routes.py:566-568`) |
| Hand-over evidence | photos and stage; **the `note` is missing** (`booking/routes.py:569-571`) |
| Payments, invoices, payout account, identity status | yes, as summaries. Invoices omit the recipient fields; payments omit refunds, charge ids and **the card fingerprint** (`payments/routes.py:311-326`) |
| Notifications and settings | yes |
| **Email and locale (Cognito)** | **no** |
| **Reports they filed, and their `reporter_email`** | **no** |
| **Moderation decisions and statements about them** | **no** |
| **Reviews about them** | **no** (only what shows on listings) |
| **Blocks, verified and suspended flags** | **no** |
| **Push devices** | **no** |
| **Card fingerprint** (booking and payments) | **no** |
| **Idempotency-key responses** | **no** |
| **Analytics events about them** | **no** |

### 5.4 Deletion coverage, table by table

`DELETE /me` (`catalog/routes.py:337-356`) first refuses while a booking is
open or a payout is pending: it asks booking and payments over `/internal`.
Then catalog runs `repository.forget` (`catalog/repository.py:171-192`) and
writes `profile.deleted` in the same transaction. The app then deletes the
Cognito user with `DeleteUser`. The server does not, so a client that skips
that step leaves the user behind (P-23). Access tokens stay valid for up to an
hour afterwards (P-24).

| Store | On deletion | Where |
|---|---|---|
| Cognito user | deleted by the app, not the server | P-23 |
| `catalog.owners` | name → "Former member", initials → "—", `business` → null, `deleted_at` set; `district`, `adult_confirmed_at`, stats and `suspended_at` kept | `repository.py:183-187` |
| `catalog.listings` | soft-deleted, `address` → null; **`title`, `blurb`, `instructions`, `photos` and `spec` kept**; no CDN purge | `repository.py:176-180` |
| `catalog.saved_listings` | deleted | `:181` |
| `catalog.payable_owners` | deleted | `:182` |
| `catalog.reviews` they wrote | author → "Former member", `author_id` → null; **`text` kept** | `:188-192` |
| `catalog.reviews` about them | kept | none |
| `catalog.media` and the S3 objects | **kept** (the rows are `used`, so the orphan sweep never touches them) | `jobs.py:20-37`, `repository.py:780-787` |
| `catalog.reports` (as reporter or target) | **kept, with `reporter_email` and `details`** | none |
| `catalog.moderation_actions` | kept (audit) | none |
| `catalog.idempotency_keys` | **kept** | none |
| `booking.bookings` | **kept, including `listing_snapshot.ownerName`/`ownerBusiness`, `handover`, `outcome.note`, `decline_reason` and `card_fingerprint`**. The docstring's claim that bookings "hold no personal data" (`catalog/routes.py:341-342`) is wrong | `booking/handlers.py:117-118` |
| `booking.booking_messages` they sent | `body` → "[removed: the account was deleted]", `unmasked` → null | `booking/handlers.py:124-132` |
| `booking.blocks` (either side) | deleted | `:122` |
| `booking.verified_people` | deleted | `:123` |
| `booking.suspended` | kept (fraud linking) | none |
| `booking.booking_evidence` | **kept (photos and note)** | none |
| `booking.booking_transitions` | kept | none |
| `booking.idempotency_keys` | **kept** | none |
| `payments.connect_accounts` | deleted locally. The Stripe account stays with Stripe | `payments/handlers.py:151-156` |
| `payments.identities` | deleted locally. **The Stripe Identity session (document and selfie) is not redacted** | `:157-159` |
| `payments.payments` | kept (financial), including `card_fingerprint` | none |
| `payments.invoices` | kept (10 years by law) | none |
| `notifications.devices` | deleted. **SNS platform endpoints are not deleted** (the IAM allows `sns:DeleteEndpoint`, `ecs.tf:216`, but no code calls it) | `notifications/handlers.py:161` |
| `notifications.inbox` | deleted | `:162` |
| `notifications.notification_prefs` | deleted | `:163` |
| `outbox` and `processed_events` | expire after 7 and 21 days | `events.py:311-312` |
| SQS DLQs | expire after 14 days | `messaging/main.tf:32` |
| **Analytics lake** | **kept 730 days**, including `ownerName`, `ownerBusiness`, `reporterEmail`, statements and review notes | `analytics.tf:18-33` |
| CloudWatch logs | expire after 90 days | `ecs.tf:125` |
| Aurora backups | expire after 14 days | `data.tf:68` |
| SES suppression list | kept | `email.tf:50-51` |
| On the device | cleared by sign-out (`web/src/data/auth.ts:108-109`, `web/src/app/device.ts:69`) | |

### 5.5 Legal retention and the gaps

What the law asks us to keep:

- **Invoices: 10 years** (GoBD, § 147 AO, § 14b UStG). They are never changed
  once issued (`payments/tables.py:59-61`, `payments/invoices.py:65-68`).
  Nothing purges them after 10 years yet.
- **Booking and payment records:** booking ledgers and payments count as
  business records (6 to 10 years under HGB and AO). They are kept for ever,
  and no retention job exists.
- **DSA:** notices and statements of reasons must stay available for
  complaints (Art. 20: at least 6 months after the decision). They are kept
  for ever.

The gaps, with their tasks:

| Gap | Task |
|---|---|
| Names, business identity and reporter emails in event payloads, and so in the two-year lake. Also missing from P-6: `booking.rated.outcome.note`, `moderation.decision.statement`, `moderation.person_flagged.details` | P-6 |
| The Cognito user survives when the app skips `DeleteUser`. Names stay in booking snapshots | P-23 |
| Tokens stay valid for up to 60 min after deletion | P-24 |
| ID-check data is special-category: consent, retention schedule, CAI declaration. Nothing redacts the Stripe Identity session on deletion | P-17, P-18, P-28 |
| Evidence photos sit behind public URLs | P-27 |
| Client error logs keep free text | P-34 |
| WAF sampled requests keep headers in us-east-1 | P-20 |
| The privacy policy omits categories: messages, photos, reports, ID checks, push | P-15, P-16 |
| No breach process or incident register | P-13 |
| Nothing documents the transfers (US and Canadian data in Frankfurt; EU data to US processors) | P-19 |
| No CCPA/CPRA request process | P-29 |
| No DPAs, records of processing or DPIA | G-B3, P-30 |
| No task yet: photos, listing text and `instructions` survive deletion; `reports` (including `reporter_email`) have no retention; `idempotency_keys` are kept for ever; SNS endpoints are not deleted; the export is missing the items in §5.3; there is no 10-year purge for invoices; the `inbox` has no retention | none |

---

## 6. Money data

- **Minor units, as integers:** `Cents = int` (`backend/libs/cappy_common/cappy_common/models.py:19`).
  - Quotes: `backend/services/matching/matching/domain/pricing.py:54-72`.
  - Bookings: `bookings.amount` and `refund_amount`.
  - Payments: `amount` and `owner_net`.
  - Invoices: `net`, `vat` and `gross`.
  - Events: `amount`.
  - No floats anywhere on the money path.
- **Currency:** a 3-letter lower-case code travels with every amount
  (`payments.currency`, `invoices.currency`, `booking.status_changed.currency`),
  validated `^[a-z]{3}$` at the intent (`payments/routes.py:44`). Today every
  booking is created in **`"eur"`** (`booking/routes.py:180`, column default
  `booking/tables.py:50`). `Money(amount_minor, currency)` and per-market
  currencies come with M-3 and M-4 (GOAL 16, ADR 0013). Nothing converts
  between currencies.
- **Fee:** 15% (`PLATFORM_FEE_BPS = 1500`, `pricing.py:14`), inside the total.
  `owner_net = total - fee` (`pricing.py:61-72`). A partial refund pays the
  owner their pro-rata share of what is kept (`payments/handlers.py:88-106`).
  Per-market fees come with M-2.
- **Invoices** (`payments/invoices.py`) are issued once per booking, at the
  payout or when a late cancellation keeps a fee (`payments/handlers.py:107-115`, `:134-142`).
  - **Numbering:** `CAP-<year>-<7 digits>`, one series per calendar year of
    the issuer's time zone (Europe/Berlin), with no gaps. The number is taken
    under a row lock on `invoice_counters` (`invoices.py:74-88`).
  - A redelivered event finds the existing invoice (`invoices.py:69-73`).
  - VAT: German 19% included, by default (`invoices.py:33-48`, from settings: `:51-52`).
  - The recipient fields are copied from `ownerBusiness`, or from `ownerName`,
    in the event (`invoices.py:84-102`).
  - Per-entity series, templates and tax come with M-11, M-12 and M-13.
- **Stripe** (ADR 0005): the request authorises, the accept captures, and
  completion transfers (separate charges and transfers). Webhooks are the
  source of truth. They are signature-verified and handled once per Stripe
  event id (`payments/routes.py:332-379`). Chargebacks hold payouts
  (`payments/routes.py:369-376`, `handlers.py:116-118`).
- **Reconciliation:** every ~5 minutes (`payments/jobs.py:61-63`), intents
  still `created` after 10 minutes are looked up at Stripe:
  - `requires_capture` → authorised, and `payment.authorised` is sent;
  - `canceled` → cancelled (`jobs.py:29-58`).

  Payouts wait in the queue, with retries, while they are switched off or
  something blocks them (`NotReady`: `handlers.py:43-45`, `:120-124`).
  There is no ledger-level reconciliation against Stripe balance
  transactions yet.

---

## 7. Migrations policy and drift checks

- **Alembic per service**, in `<service>/migrations/versions`, with a shared
  `env.py` driver (`backend/libs/cappy_common/cappy_common/migrations.py:1-8`).
  Each migration file runs in its own transaction (`:67-69`). The deployed
  schema changes **only** through migrations: `create_all` runs only for
  throwaway SQLite (`runtime.py:75-81`).
- **Expand and contract:** new code must work with the schema before and
  after its migration, so a rollback never needs a down-migration
  (`migrations.py:5-7`).
  Destructive migrations check the data first. For example, 0003 refuses to
  add the exclusion constraint while overlapping bookings exist
  (`booking/migrations/versions/0003_completed_bookings_keep_their_window.py:34-48`).
- **Deploy order:** the CD pipeline runs every service's `migrate` task, and
  **no service rolls unless every one exits 0** (`.github/workflows/deploy.yml:83-104`).
  With `ADMIN_DATABASE_URL`, the task first creates or rotates the service's
  role and database (`migrations.py:116-131`).
- **Drift checks.** In each `test_<service>_postgres.py`, run by `make test-pg`
  (`Makefile:41-42`) and in CI with a Postgres service (`.github/workflows/ci.yml:19-40`):
  - `test_migrations_build_exactly_the_models` upgrades a fresh database to
    head and asserts that Alembic's `compare_metadata` against the models is
    empty (for example `backend/services/catalog/tests/test_catalog_postgres.py:25-35`).
  - Only the raw-SQL trigram indexes are allowed to differ (`catalog/tables.py:122`).
  - `make test` (SQLite) does not run these checks.
- **No automated check** that the Terraform subscriptions
  (`infra/platform/data.tf:6-11`), `local/bootstrap.py:30-49` and each
  service's handler map agree. Today they match (§3.2). `events.py:50-51`
  asks for the three to change together.

---

## 8. Data residency (ADR 0013)

**Today.** There is one cell, in **eu-central-1** (Frankfurt):

- Aurora, Cognito, SES, SNS/SQS, S3 (media and analytics), Firehose and
  CloudWatch all run there (`infra/platform/variables.tf:10-13`,
  `infra/envs/prod/main.tf:20`).
- CloudFront certificates and WAF are in us-east-1 (`infra/envs/prod/main.tf:27-29`).
- CloudFront serves from edges in Europe and North America (`PriceClass_100`).
- Stripe runs on one DE platform account. APNs and FCM are in the US.
- North American users' data would sit in Frankfurt, and EU data already
  reaches US processors. No transfer safeguards are documented (P-19).

**With the North America cell** (ADR 0013 §2-4):

- A second, complete copy of `infra/platform` runs in **ca-central-1**
  (M-21), with its own Aurora cluster, Cognito pool, SES, SNS/SQS, S3,
  analytics lake and Stripe secrets (M-10). It is validated and applied to
  LocalStack only (GOAL 12).
- **Nothing is replicated between cells.** Only the static web bundle, the
  market config (M-2) and DNS are global.
- A person belongs to one cell, chosen from their country at sign-up. The app
  stores the cell and talks to `https://<cell>.api.<domain>` (M-22). Someone
  with accounts in both cells has two separate accounts, each exported and
  deleted separately.
- A listing's market comes from its geocoded address (M-5, M-7). A booking
  takes the listing's market, currency and entity (M-23). A booking across
  cells is refused.
- The US and Canadian tables, events and lake stay in Canada, and Québec
  data does not leave Canada except to processors (Stripe US platform, APNs
  and FCM). Those transfers need Law 25 PIAs (M-29, P-19).
- The EU cell stays EEA, CH and UK only.
- Every table in §2 exists once per cell, unchanged. What changes is who is
  in each database. Everything in §5 holds per cell.

---

## 9. How to keep this file true

This file is a living doc (see [`CLAUDE.md`](../CLAUDE.md), "Living docs").
Update it **in the same commit** as any change to:

- a table, column, constraint or index (a model in `*/tables.py` and its
  migration). Update §2 and, if it holds personal data, §5;
- an event type, payload field, producer or handler (`cappy_common/events.py`,
  `*/handlers.py`, `outbox.add` calls). Update §3.2 and §3.3, and keep
  `infra/platform/data.tf`, `local/bootstrap.py` and the handler maps in step;
- queue, DLQ or retry settings (`infra/modules/messaging`, `events.py`). Update §3.1;
- an `/internal/*` route or client (`*/routes.py`, `*/clients.py`). Update §4;
- anything that stores, exports or deletes personal data (`/me/export`,
  `DELETE /me`, `/internal/people/*`, `profile.deleted` handlers, a new
  processor). Update §5.3 and §5.4, and add a task to `docs/TASKS.md` for any
  new gap;
- retention (prune constants, lifecycle rules, log retention, backups). Update §1, §2 and §5;
- money types, currency, fees or invoices. Update §6;
- migration tooling or CI drift checks. Update §7;
- cells or regions (ADR 0013, `infra/envs/*`). Update §8.

Check that the line references still point at the right code.
