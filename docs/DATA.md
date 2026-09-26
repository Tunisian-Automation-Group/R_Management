# Data

The services, their tables, the events between them, who reads what, how
long things are kept, and where personal data lives. This is a living doc
(see [`CLAUDE.md`](../CLAUDE.md)). It describes the code **as committed at
`4e86866`**. This sync covered `7444e37` (booking's `booking_disputes`,
`booking_resolutions` and `booking_claims` and `bookings.extends_id`,
migration booking 0016; the staff audit log fed by `staff.action`, catalog
0019; `booking.dispute_offer`; `timeZone` on booking events; markets'
`time_zone`, refund limits and `late_fee_cap`; payments' internal payment
state; Austrian and Swiss districts and owners in the seed), `32338dd` (the
e2e's own second buyer), `22b5e0f` (`listings.hold_reason`, catalog 0020,
and the hourly out-of-market hold; `booking.notice`; `declineReason` on
`booking.status_changed`; `partially_refunded`; the payout notice's title
and start; batch `maxQuantity`) and `4e86866` (web only; no data change).
The sync before covered `42c777c` and `2257182`. Line references not touched
by this sync may have drifted by a few lines.

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
| catalog | `catalog` | yes | yes | hourly: orphan-photo sweep, public and private stores, with a CDN purge of every deleted file (since `747ed6b`); then reporters forgotten 6 months after the decision; then weekly schedules rolled on and `listing.idle` for listings with no free time next week (since `61b15b8`); then, since `42c777c`, up to 100 message decisions recorded before `747ed6b` attributed to their author by asking booking (`attribute_decisions_once`, to be dropped once none remain); then, since `22b5e0f` (V5-1), up to 500 live listings (`BATCH`) whose district is not in a live market or not in the owner's country held with a `hold_reason` and taken out of search, each logged and announced as `listing.changed` `held` (`hold_out_of_market_once`, `:123-137`) (`backend/services/catalog/catalog/jobs.py`) |
| booking | `booking` | yes | yes | expiry, auto-complete and review sweeps, and since `7444e37` disputes whose 72-hour deadline passed marked escalated (`escalate_due`, with a `booking.notice` to both sides since `22b5e0f`) (`backend/services/booking/booking/jobs.py:18-54`) |
| payments | `payments` | no | yes | Stripe reconciliation, every ~5 min; invoice purge after the retention period, daily (`backend/services/payments/payments/jobs.py:29-88`) |
| notifications | `notifications` | no | yes | hourly: bell items older than `INBOX_RETENTION_DAYS` (365) deleted (`notifications/jobs.py:16`, since `747ed6b`) |

Every service that has a database also runs the outbox relay, its SQS consumer,
and an hourly prune of `outbox` and `processed_events` and, where the service
has one, of `idempotency_keys` older than 24 h
(`backend/libs/cappy_common/cappy_common/runtime.py:132-140`, `:165-178`), and
since `747ed6b` of `revoked_sessions` rows older than 25 h and `rate_hits`
older than 2 days (`prune_guards`, `cappy_common/guard.py:56`). It
also checks every signed-in request against its own `revoked_sessions` table
(`runtime.py:119`, `cappy_common/auth.py:168-178`; §1 "Tables every database
has"). Since `42c777c` the token's whole-second `iat` is compared with the
exact `not_before`, so a token issued in the same second as the revocation
is refused too (V4-24). Matching and the gateway have no database, so they do not.

### Writer and reader: `Tx` and `ReadTx`

- **`Tx`** (`runtime.py:190-207`) gives one transaction per request, on the
  **writer**. It commits *before* the response is sent (`scope="function"`)
  and then wakes the outbox relay, so a request's events go out at once.
  Every route that writes uses it. Routes that must read their own writes use
  it too.
- **`ReadTx`** (`runtime.py:210-222`) is a `SET TRANSACTION READ ONLY` session
  on the **reader** endpoint. It is only for reads that can tolerate a few
  milliseconds of replica lag. It is configured by `DATABASE_READ_URL`
  (`runtime.py:107-111`). Without that variable, reads go to the writer.
  Terraform gives a reader URL to catalog and booking only
  (`infra/platform/data.tf:113-127`, `infra/platform/ecs.tf:81`).
  - catalog: `/districts`, `/cities`, `/districts/nearest`, `/owners/{id}`,
    `/listings/{id}`, `/listings/{id}/reviews`, `/search`, and
    `/internal/candidates` and `/internal/listings/{id}/context`
    (`backend/services/catalog/catalog/routes.py:49`, `:421-500`, `:725-745`).
    The unused `/internal/owners/{id}` was removed in `235eeaa` (D-12).
  - booking: `/internal/busy` only (`backend/services/booking/booking/routes.py:626-633`).
    A window booked a moment ago may still look free there. The exclusion
    constraint (§2.2) then refuses the booking.
- An alarm fires when the reader is more than 1 s behind
  (`infra/platform/data.tf:193-206`).
- Connections are sized against Aurora's limit
  (`infra/platform/data.tf:173-191`). Each task gets a pool of 5 plus 10
  overflow, a 5 s statement timeout and a 30 s idle-in-transaction timeout
  (`backend/libs/cappy_common/cappy_common/db.py:64-117`).

### Tables every database has

| Table | Purpose | Key | Retention |
|---|---|---|---|
| `outbox` | Events written in the same transaction as the change they describe (ADR 0003) | `id`. Partial index `ix_outbox_unsent` on `created_at WHERE sent_at IS NULL` (`events.py:163`) | Sent rows are kept **7 days** (`events.py:325`). A row that fails 20 times is set aside and kept until someone deals with it (`events.py:218`, `:254-257`); since `235eeaa` the relay logs `OUTBOX_SET_ASIDE` for it (`:278-286`) and the `outbox-set-aside` alarm pages (D-14; runbook). **PII:** the body is the whole event payload (§3) |
| `processed_events` | Ids of events this consumer has handled, for idempotency. Payments also stores Stripe webhook event ids here, and `idv:<session>:<status>` keys for the identity webhook (`backend/services/payments/payments/routes.py:419-477`) | `event_id` | **21 days**, which outlives the DLQ's 14 (`events.py:326`) |
| `revoked_sessions` | "Tokens of this person issued before `not_before` no longer count" (P-24). Written by catalog when it takes a sign-out-everywhere or a deletion, and by every other service with a database when `person.signed_out` or `profile.deleted` reaches it (`backend/libs/cappy_common/cappy_common/guard.py:49-77`). Read on every signed-in request through a 30 s cache per replica (`guard.py:80-106`) | `sub` (`guard.py:28-34`, created by `event_tables`, `events.py:174-177`) | **25 hours** since `747ed6b` (`REVOCATION_KEPT`): a revocation only matters while a token issued before it can still be valid (Cognito caps access tokens at a day; ours last 15 min). Pruned hourly (`prune_guards`, `guard.py:56`). Pseudonymous id and a time |
| `rate_hits` (catalog only) | Per-person counters for limits no other table can count: `export:<sub>` (5 a day) and `sign-out:<sub>` (5 an hour) (`backend/services/catalog/catalog/routes.py:377-418`, P-12) | `id`; index `ix_rate_hits_key_at` (`guard.py:37-46`) | A key's rows older than its window are deleted on its next use (`guard.py:109-117`), and since `747ed6b` every row older than **2 days** by the hourly prune (`RATE_HITS_KEPT`, `prune_guards`). **PII:** the `sub` in the key |
| `idempotency_keys` (catalog, booking) | `Idempotency-Key` replay for creating POSTs | (`principal`, `key`) (`backend/libs/cappy_common/cappy_common/idempotency.py:34-44`) | **24 hours** (`KEEP`, `idempotency.py:31`): deleted by the hourly prune (`expire`, `:85-89`), and a person's rows on account deletion (`forget`, `:92-94`). D-4, `235eeaa`. **PII:** `response` is the first answer as JSON, for example a report's details or a listing |

---

## 2. Tables per service

Every instant is a `timestamptz` (`db.py:43-61`). Every constraint name is
deterministic (`db.py:26-32`). Unless a row says otherwise, a table has
**no time-based retention**: rows stay until account deletion changes them
(§5.4) or for ever. Every table that holds a person's id is in the register
`backend/libs/cappy_common/cappy_common/privacy.py` (since `235eeaa`, D-11),
which says whether deletion deletes, redacts or keeps it, whether the export
includes it, and why when it is kept or left out. `tests/test_privacy.py`
fails when a table with a person-id column is missing from it, or when the
deletion or export code named for a table never touches it. Periods and
legal bases: [`retention.md`](retention.md).

### 2.1 catalog (`backend/services/catalog/catalog/tables.py`)

| Table | Purpose and key columns | Constraints and indexes that matter | Personal data | Retention |
|---|---|---|---|---|
| `districts` (`:35-42`) | Reference places: `name` PK, `city`, `metro`, `country`, `lat`, `lng` | `ix_districts_lat_lng` (`:130`), `metro` index | none | Reference data |
| `owners` (`:45-80`) | Every signed-up person (id = Cognito `sub`): `name`, `initials`, `kind` (person/business), `district`, `country` (ISO 3166-1 alpha-2, default `DE`; since `235eeaa`, migration `0014_owner_country`, M-9), `verified` (set by a passed ID check since `235eeaa`, F-10), rating counters, `renter_*`, `joined_year`, `deleted_at`, `suspended_at`, `business` JSON, `adult_confirmed_at`, `cancellation_rate`, `response_mins` and `response_rate` (nullable since `61b15b8`, migration `0016_response_metrics`: measured by booking over 90 days, null under 3 requests; the old 60-minute default was cleared, H-1) | PK `id`; FK `district` → districts | **PII:** `name`, `initials`, `district` and `country` (coarse location; both public on the profile), `verified`, `business` (legal name, **address**, register number, VAT ID: `backend/libs/cappy_common/cappy_common/models.py:119-127`), `adult_confirmed_at`, reliability and suspension | Redacted on deletion: "Former member", `business`, `verified`, `cancellation_rate`, `response_mins` and `response_rate` cleared; the row stays as a shell (§5.4). The same `sub` signing up again starts afresh (FL-11) |
| `listings` (`:83-110`) | `owner_id`, `category`, `mode`, `title`, `blurb`, `district`, `instructions`, `address`, `moderated_at`, `held_at`, `rules`, `photos`, `active`, `spec` JSON (prices, sizes and, since `235eeaa`, `currency`; since `61b15b8` optionally `availability` (weekly hours, time zone), `location` (lat/lng), `country` and `postalCode`), `deleted_at` (soft delete), `scheduled_until` (how far the weekly schedule's windows reach; indexed) and `idle_notice_at` (the last "no free time next week" notice), both since `61b15b8` (migration `0017_weekly_schedule`); `hold_reason` (since `22b5e0f`, migration `0020_hold_reason`, `:106`): `market_not_live` or `district_not_in_country` when the listing is held for where it is rather than for the price check; such a hold also sets `active` false, the owner's move into an open market clears both, and staff approval is refused (409 with the reason as code). `spec` also carries a batch listing's optional `maxQuantity` since `22b5e0f` | `ix_listings_search` (`:112`); partial `ix_listings_live` and `ix_listings_live_district` `WHERE deleted_at IS NULL AND active` (`:115-120`, `:128-132`); `ix_listings_owner_created` (`:126`); trigram GIN `ix_listings_title_trgm`, `ix_listings_blurb_trgm`, created only in the migration (`catalog/migrations/versions/0001_initial_catalog_schema.py:153-154`; allowed list `tables.py:125`) | **Sensitive:** `address` (private until a booking is accepted: `:91-93`) and `instructions` (door codes, where the key is; never public: `backend/services/catalog/catalog/repository.py:109-133`). `photos`. **Sensitive:** `spec.location` and `spec.postalCode` (where the thing is, often someone's home): public answers snap the point to about 500 m and drop the postal code (`snapped`, `cappy_common/models.py:174`); the exact values go only to an accepted booking's hand-over (M-6). Since `2257182` the web sends the district's centre as `location`, the district's `country` and an optional `postalCode`. Seeded listings get an invented `address` from `seed.json` `listingAddresses` (since `42c777c`) | Soft-deleted for ever. On account deletion `title` becomes "Removed listing" and `blurb`, `instructions`, `rules`, `photos` and `address` are cleared, and the spec's personal keys go as listed in `privacy.LISTING_SPEC` (since `42c777c`): `extraLabel` and `machine` → "", `location` and `postalCode` removed. ~~`location` and `postalCode` stay~~ (fixed in `42c777c`). The rest of `spec` (numbers, categories, `country`, `availability`) stays (D-2) |
| `slots` (`:138-146`) | Idle windows: `listing_id`, `start`, `end`, `hours_usable`, `generated` (made from the weekly schedule, since `61b15b8`; a new schedule deletes the future generated ones) | FK cascade; `ix_slots_listing_end` (`:148`) | none | Kept with the listing |
| `reviews` (`:153-167`) | Renter → owner reviews: `rv_<bookingId>` PK, `author`, `initials`, `author_id`, `rating`, `on_time`, `text`, `tags`, `at` | `ix_reviews_listing_at` (`:170`); `owner_id` index | **PII:** `author` (shown as "Ada L.": `backend/services/catalog/catalog/handlers.py:14-17`), `author_id`, `text` (free text) | Author anonymised on deletion; the text stays. A moderation `remove_content` empties `text` and `tags` and keeps the rating (`catalog/moderation.py:339-349`, FL-7) |
| `saved_listings` (`:173-182`) | Hearts: (`user_id`, `listing_id`) PK, `saved_at` | `ix_saved_user_at` | **PII:** what someone shortlisted | Deleted with the account |
| `payable_owners` (`:185-193`) | Payments' latest word on `ready`, with `as_of` (older news loses) | PK `owner_id` | Pseudonymous | Deleted with the account |
| `reports` (`:196-215`) | DSA Art. 16 notices, plus system flags: `target_type`, `target_id`, `reason`, `details`, `reporter_id`, `reporter_email`, `status`, the decision, `statement`, `statement_of_reasons` | `ix_reports_status_created` (`:218`) | **PII:** `reporter_email` (people without an account), `reporter_id`, `details` (free text about someone) | Since `235eeaa` (D-3): `reporter_id`, `reporter_email` and `details` are cleared when the reporter deletes their account, and for every report **183 days after its decision** (DSA Art. 20 contest window; `REPORTER_KEPT`, `jobs.py:21`, `forget_reporters_once` `:45-60`). The case, decision and statement stay |
| `moderation_actions` (`:234-260`) | Since `7444e37` (H-7) **the one append-only audit log of every staff action**: `actor_id`, `action` (moderation's `dismiss`, `take_down`, `suspend`, `remove_content`, `reinstate`, `approve`, written directly; and from booking's `staff.action` events: `resolve_dispute`, `propose_resolution`, `approve_resolution`, `reject_resolution`, `confirm_claim`, `reject_claim`, and staff reads `read_case` and `read_evidence`, inserted once per event with id `sa_<event>`, `moderation.py:538-555`), target, `report_id`, `statement` (for a booking action: outcome, amount, reason code and the staff note), `statement_of_reasons`, `at`, `person_id` (whom the decision is about; since `747ed6b`, back-filled by migrations `0015` and `0018` and the hourly `attribute_decisions_once`), and since `7444e37` `request_id` (migration `0019_audit_request_id`). Nothing updates or deletes a row | `ix_moderation_actions_at`, `ix_moderation_actions_person`, and since `7444e37` `ix_moderation_actions_target` (`target_id`, `at`) and `ix_moderation_actions_actor` (`actor_id`, `at`) | **PII:** staff ids, statements about people (a resolution's note is free text), `person_id` | Kept for ever (the DSA record, Art. 17 and 24, and staff accountability; the register's reason) |
| `media` (`:239-253`) | Uploaded photos (content hash) per owner: (`name`, `owner_id`) PK, `bytes`, `width`, `height`, `used` | `owner_id` index | **PII:** photos can show people and places. Hand-over evidence has rows here too; its files are in the private store (`s3://<media>/private/`, never behind CloudFront: `catalog/media.py:155-175`, P-27) | Unused uploads swept after **1 day**, from both stores (`jobs.py:17`, `:24-42`). Used photos stay while the account exists; on deletion every row of the person is marked unused and dated 2000, so the next hourly sweep deletes the rows and the files, except a file another person also holds (D-1, `repository.py:212-214`) |
| `outbox`, `processed_events`, `revoked_sessions`, `rate_hits`, `idempotency_keys` | §1 | | | |

### 2.2 booking (`backend/services/booking/booking/tables.py`)

| Table | Purpose and key columns | Constraints and indexes that matter | Personal data | Retention |
|---|---|---|---|---|
| `bookings` (`:36-86`) | `requester_id`, `owner_id`, `listing_id`, `status`, `window_start`/`window_end`, `expires_at`, `amount` (minor units), `currency`, `requirement`, `match` (quote), `listing_snapshot` (since `7444e37` also `timeZone`, the listing's weekly-hours zone or its owner's market's `time_zone`), `decline_reason`, `outcome` (the renter's review), `renter_rating`, `refund_amount`, `rated_at`, `reviews_published_at`, `idempotency_key`, `request_hash`, `handover`, `no_show`, `card_fingerprint`, and since `7444e37` `extends_id` (`:81`, migration `0016`): the booking this one extends, for the same renter (S-12) | **`ex_bookings_no_double_booking`**: `EXCLUDE USING gist (listing_id WITH =, tstzrange(window_start, window_end, '[)') WITH &&) WHERE status IN ('awaiting_payment','requested','accepted','active','completed','disputed')` (`booking/migrations/versions/0003_completed_bookings_keep_their_window.py:21-31`; `btree_gist` in `0001_initial_booking_schema.py:21`; ADR 0004). Violations become 409 (`backend/services/booking/booking/routes.py:203-217`). `uq_bookings_requester_idempotency` and `ck_bookings_window_forward` (`:79-82`). Indexes `ix_bookings_requester_created`, `ix_bookings_owner_created`, `ix_bookings_listing_window`, `ix_bookings_status_expires`, `ix_bookings_status_window_end`, `ix_bookings_card_fingerprint` and, since `7444e37` (the staff case list), `ix_bookings_status_updated` (`:221-229`) | **PII:** both parties' ids; `listing_snapshot.ownerName` and `ownerBusiness` (`routes.py:184-194`); `handover` (**sensitive**: address and instructions copied at accept, `routes.py:111-113`); `outcome.note` and `decline_reason` (free text); **sensitive:** `card_fingerprint`. `currency` is the listing's (M-3), upper-case ISO 4217 since `747ed6b` (migration `0015_currency_upper` upper-cased old rows; the column has no default any more). `handover` since `61b15b8` also holds the listing's exact `location` and `postalCode` (**sensitive**). Since `42c777c` (V4-9) reading an `accepted` or `active` booking refreshes `handover` from catalog, so a corrected address reaches the renter; after that the last copy stands | Kept for ever as the financial record. Since `7444e37` every settled dispute goes through `settle` (`booking/support.py:266-285`): refunding everything cancels the booking with `refund_amount` = `amount`; a partial refund or paying the owner completes it, with `refund_amount` the part refunded (none for paying the owner). Since `235eeaa` account deletion redacts what names or locates the person: `handover`, the owner's snapshot name and business, the owner's `decline_reason`, the renter's `outcome.note` and, unless they are suspended, the renter's `card_fingerprint` (`redact_bookings`, `booking/handlers.py:38-65`, D-5; §5.4) |
| `booking_messages` (`:85-102`) | Chat per booking: `sender_id`, `body` (contact details masked before acceptance), `unmasked` (the words as written), `flagged` | FK cascade; `ix_booking_messages_booking_at` | **PII, sensitive:** free text, phone numbers and emails in `unmasked` | On deletion the sender's words are replaced (§5.4). A moderation `remove_content` replaces them with "[removed by Cappy: it broke our rules]" (`booking/routes.py:545-553`, FL-7) |
| `blocks` (`:105-111`) | (`blocker_id`, `blocked_id`) PK | | **PII** (who blocked whom) | Deleted with either account |
| `verified_people` (`:114-119`) | Copy of payments' identity outcome | PK `person_id` | **PII:** "ID-checked" | Deleted with the account |
| `suspended` (`:122-127`) | Copy of moderation's suspension | PK `person_id` | **PII** | Kept after deletion (fraud: card links, S-17). Removed on reinstatement |
| `booking_evidence` (`:130-141`) | Hand-over and return photos: `by`, `stage`, `photos` (URLs), `note` | `booking_id` index | **PII:** photos and `note`. `photos` hold `evidence:<name>` references to the private store; the two sides and staff (with MFA) get them as links signed for 15 minutes, served by booking itself (`booking/messages.py:299-370`, P-27). Rows from before `f303350` may still hold public URLs | Kept for disputes. On the author's deletion `photos` → `[]` and `note` → null (D-5), and catalog's sweep deletes the files |
| `booking_transitions` (`:148-158`) | Every status change: `from_status`, `to_status`, `by`, `at` | `booking_id` index | Pseudonymous ids (`by` is `support:<staff sub>` for a staff settlement) | Kept for ever (audit, reliability and, since `61b15b8`, response time: `owner_responsiveness`, `booking/repository.py:214`) |
| `booking_disputes` (`:161-176`, since `7444e37`, migration `0016`, S-21) | One per disputed booking: `booking_id` PK (FK cascade), `by` (who opened it), `reason`, `opened_at`, `respond_by` (72 hours after the opening or the latest offer; indexed), `escalated_at` (set by booking's sweep when `respond_by` passed with no agreement), and the offer on the table: `offer_amount` (a refund to the renter, minor units), `offer_by`, `offer_at`. The migration made a row for every booking already disputed, with 72 hours from the migration | PK; `ix_booking_disputes_respond_by` | **PII:** `reason` (free text), both ids | Register `redact`, exported: on the opener's deletion `reason` → "[removed: the account was deleted]"; amounts and dates stay |
| `booking_resolutions` (`:179-196`, since `7444e37`, H-6) | How a dispute was settled: `id` (`rs_…`), `booking_id`, `outcome` (`pay_owner`, `refund_buyer`, `partial`), `refund_amount`, `reason_code` (`damage`, `no_show`, `not_as_described`, `late_return`, `cleanliness`, `safety`, `goodwill`, `agreement`, `other`), `note`, `by` (the staff member, or the party who accepted an offer), `role` (`support`, `lead`, `parties`), `status` (`pending_approval`, `done`, `rejected`), `approved_by`, `created_at`, `decided_at` | FK cascade; `booking_id` index | **PII:** staff and party ids; `note` (a staff member's free text about the case) | Register `keep`, not exported (staff accountability, H-6); the export has each booking's outcome and refund |
| `booking_claims` (`:199-218`, since `7444e37`, S-12) | An owner's claim after a booking; today only `kind` `late_return`: `id` (`cl_…`), `booking_id`, `by`, `minutes_late`, `amount` (the extra time after 30 minutes' grace at the listing's hourly rate, rounded up to the quarter hour, plus one hour's rate capped at the market's `late_fee_cap`), `currency`, `note`, `status` (`open`, `confirmed`, `rejected`), `created_at`, `decided_by`, `decided_at`, `decision_note`. Nothing is charged (collecting needs S-9) | FK cascade; `booking_id` index; `uq_booking_claims_booking_kind` (one claim of a kind per booking) | **PII:** ids; `note` and `decision_note` (free text) | Register `redact`, exported: on the claimant's deletion `note` → null |
| `outbox`, `processed_events`, `revoked_sessions`, `idempotency_keys` | §1 | | | |

Booking states: `HOLDING` keeps the window and `OPEN` blocks account deletion
(`backend/services/booking/booking/state.py:44-51`).

### 2.3 payments (`backend/services/payments/payments/tables.py`)

| Table | Purpose and key columns | Constraints | Personal data | Retention |
|---|---|---|---|---|
| `payments` (`:21-45`) | One per booking: `booking_id` PK, `intent_id`, `requester_id`, `owner_id`, `amount`, `owner_net`, `currency` (upper-case since `747ed6b`, migration `0009_currency_upper`, which also upper-cased `invoices.currency`), `status` (created → authorised → captured → transferred, or cancelled, or refunded; since `22b5e0f` `partially_refunded` when part was refunded and the rest paid out: a late cancellation or a dispute settled in part; no migration, the column is a string), `charge_id`, `transfer_id`, `refund_id`, and what actually moved in minor units: `refunded_amount` and `paid_out_amount` (migration `0010_moved_amounts`; a renter no-show, nothing back and the owner paid, is `transferred`), `chargeback_at`, `card_fingerprint` | `intent_id` unique; indexes on requester and owner | Pseudonymous ids; **sensitive:** `card_fingerprint`. The card itself stays with Stripe | Kept for ever (financial record). `card_fingerprint` is cleared when either party deletes their account (`payments/handlers.py:157-175`, since `235eeaa`) |
| `identities` (`:47-61`) | ID-check outcome: `person_id` PK, `session_id` (the `IdentityProvider`'s session: Stripe Identity today, `payments/identity.py`, F-1), `status` (`pending`, `requires_input`, `failed`, `verified`), `verified_at`, and the recorded consent: `consent_at`, `consent_version` (`identity-2026-09`: `payments/routes.py:287-322`, P-18) | `session_id` unique; a verdict counts only for the row's current `session_id`, from the Stripe webhook or the identity webhook (`_identity_result`, `routes.py:325-340`, P-28) | **PII:** that an ID check happened, how it went, and when the person agreed to it. The document and selfie stay with the provider | Deleted with the account, and the session is redacted at the provider first (`IdentityProvider.redact`, D-6, since `235eeaa`) |
| `invoices` (`:64-85`) | The platform's fee invoice to an owner: `number` PK, `booking_id` unique, `owner_id`, `net`/`vat_rate_bps`/`vat`/`gross`, `currency`, `issued_at`, `title`, `service_start`/`end`, `recipient_name`, `recipient_address`, `recipient_vat_id` | Never updated once issued (GoBD) | **PII:** the recipient's name, address and VAT ID. Since `42c777c` (V4-7) `recipient_address` is a trader's business address, else the address the payout provider verified for a private owner, fetched from the provider when the invoice is issued (`Provider.account_address`; Stripe's connected-account address; the fake provider's "Musterstraße 1, 10115 Berlin, DE (test)"); null only when the provider did not answer | The issuer's legal period from the end of the year of issue: `INVOICE_RETENTION_YEARS`, 10 by default (`payments/invoices.py:50`, `payments/settings.py:40`), then deleted by the daily `purge_invoices_once` (`payments/jobs.py:61-77`, D-9, since `235eeaa`). Account deletion keeps them |
| `invoice_counters` (`:88-94`) | `year` PK, `last`, taken under a row lock | | none | Kept |
| `connect_accounts` (`:97-106`) | An owner's Stripe Express account, created in the country the app sends at onboarding (default `DE`; since `235eeaa`, M-9; since `747ed6b` only a live market's): `owner_id` PK, `account_id`, `payouts_enabled`, `details_submitted` | `account_id` unique | Pseudonymous. Identity and bank details stay with Stripe | Deleted with the account (the Stripe account is not) |
| `outbox`, `processed_events`, `revoked_sessions` | §1 | | | |

### 2.4 notifications (`backend/services/notifications/notifications/tables.py`)

| Table | Purpose and key columns | Personal data | Retention |
|---|---|---|---|
| `devices` (`:21-33`) | Push devices: `token` PK (APNs or FCM), `user_id`, `platform`, `endpoint` (SNS platform endpoint ARN), `created_at`, `install_hash` (sha256 of the app install's random id; a token moves to another person only from the same install, else 409 `device_taken`: `backend/services/notifications/notifications/routes.py:39-76`, P-33). At most 10 per person (`routes.py:29`, `:91-97`) | **PII:** device token | Removed on sign-out, sign-out-everywhere (`person.signed_out`), a dead endpoint, account deletion, the 10-device cap, or a move to another person. Since `235eeaa` every removal deletes the SNS endpoint first (`drop_devices`, `push.py:85-94`, D-7) |
| `inbox` (`:36-55`) | The bell: an id derived from (event, recipient, key), `user_id`, `kind`, `params`, `title`, `body`, `link`, `at`, `read_at`. Index `ix_inbox_user_at`. Also what limits message emails to one per conversation per 15 minutes (`_recently_told`, `notifications/handlers.py:88-99`, FL-3) | **PII:** what happened to someone; listing titles | **12 months** since `747ed6b` (`INBOX_RETENTION_DAYS` = 365, deleted by the hourly `expire_inbox`, `notifications/jobs.py`); deleted with the account |
| `notification_prefs` (`:58-65`) | `user_id` PK, `prefs` JSON | Preferences | Deleted with the account |
| `outbox`, `processed_events`, `revoked_sessions` | §1. Notifications publishes nothing, but the runtime creates the outbox anyway | | |

Email addresses are **not stored here**. Each time a message goes out,
notifications looks the address and locale up in Cognito
(`backend/services/notifications/notifications/mail.py:41-62`), and mails only
verified addresses (`mail.py:60-61`). The data export reads them the same way
(`person_of`, `mail.py:100-103`).

---

## 3. Events

### 3.1 Transport, ordering, idempotency

- **Outbox → SNS → one SQS queue per consumer** (ADR 0003). `Outbox.add`
  writes the event in the caller's transaction (`events.py:186-207`) and
  refuses types that are not in the catalogue (`events.py:86-111`, `:189-190`).
  The relay in every replica claims unsent rows with `FOR UPDATE SKIP LOCKED`,
  publishes batches of 10 and marks them sent (`events.py:234-321`,
  `:450-473`). Delivery is **at least once**: a crash after the publish sends
  the event again.
- **Envelope:** `{id, type, source, occurredAt, data, trace?}` (`events.py:114-147`).
  `type` is also a message attribute, and each queue's filter policy uses it
  (`infra/modules/messaging/main.tf:64-71`). Raw delivery is on.
- **Ordering:** standard SNS and SQS, so **no ordering** between events or
  within one type. Consumers are written for that:
  - catalog ignores a `payment.payouts_ready` older than the state it has
    (`asOf`: `backend/services/catalog/catalog/repository.py:298-306`);
  - booking's handlers only apply transitions the state machine allows from
    the current status (`backend/services/booking/booking/handlers.py:71-84`);
  - payments raises `NotReady` for a `completed` that arrives before the
    capture, so it is retried (`backend/services/payments/payments/handlers.py:149-152`);
  - catalog counts a rating once per booking (`catalog/handlers.py:38-41`).
- **Idempotency:** the `Dispatcher` inserts the event id into `processed_events`
  **in the same transaction** as the handler's writes. A duplicate hits the
  primary key and is skipped (`events.py:348-393`). Notifications is the
  exception by design: it sends the mail before the commit, so a crash can
  send it twice (`backend/services/notifications/notifications/handlers.py:1-6`).
  Its inbox rows use a deterministic id, so a repeat never shows twice
  (`handlers.py:245-265`). Payments' Stripe calls carry idempotency keys
  (`payments/handlers.py:10-12`).
- **Failures are never acknowledged.** The consumer deletes a message only
  after its handler has committed. Otherwise it resets the message's
  visibility with an exponential, jittered backoff from 30 s to 15 min
  (`events.py:221-231`, `:495-515`).
- **DLQs:** each consumer has a queue `cappy-<env>-<service>` with a 120 s
  visibility timeout and `maxReceiveCount = 12`, about 2 h of retries, and a
  DLQ `…-dlq` that keeps messages 14 days (`infra/modules/messaging/main.tf:29-47`;
  local copy `local/bootstrap.py`). There is one alarm per DLQ on any
  message (`infra/platform/observability.tf:74-88`) and one on queue age (`:90-106`):
  over 15 min for payments and 10 for notifications (their SLIs, since
  `7444e37`), 5 for the others. The `events.py` docstring (`events.py:16-19`), a dated
  correction in ADR 0003 and the runbook all say 12 receives (D-15, fixed in
  `235eeaa`).
- **Redrive** (`docs/runbook.md:58`): read the DLQ, fix the cause, then run
  `aws sqs start-message-move-task --source-arn <dlq-arn>`. This is safe
  because every handler is idempotent, as long as it happens within 21 days,
  the `processed_events` retention.
- **Analytics:** a second, **unfiltered** SNS subscription copies **every**
  event to Firehose → S3, kept 730 days (`infra/platform/analytics.tf:133-139`, `:18-35`).
  Since `f303350` a Firehose Lambda transform (`infra/platform/analytics/scrub.py`,
  wired at `analytics.tf:74-115`) keeps only the envelope (`id`, `type`,
  `source`, `occurredAt`) and an allowlist of scalar `data` fields: any key
  ending in `Id`, plus `from`, `to`, `by`, `amount`, `currency`,
  `refundAmount`, `noShow`, `windowStart`, `windowEnd`, `expiresAt`, `change`,
  `rating`, `quality`, `reason`, `targetType`, `decision`, `category`,
  `district`, `ready`, `status`, `cancellationRate`, `mode`, `hours`
  (`scrub.py:15-31`). Since `747ed6b` a `by` of `support:<who>` (a staff
  resolution) is rewritten to `staff`, so no staff identity reaches the lake
  (`scrub.py:35`). Names, business details, emails, card fingerprints,
  titles, statements, notes and the trace context never reach the lake. A
  record it cannot parse is dropped, never stored raw (P-6, fixed). Its
  self-check asserts that `outcome.note`, a moderation `statement` and
  `details` never arrive (`scrub.py:67-69`, D-8, `235eeaa`). A `staff.action`
  keeps only `action`, `targetType` and `at`: who acted, about whom, and the
  staff note stay in the audit log (`scrub.py` `STAFF_ACTION_FIELDS`, with
  its self-check). `booking.status_changed.declineReason`
  (free text since `22b5e0f`) and `booking.notice`'s list-valued `to` are not
  kept.
- **Stuck outbox rows** (20 failed publishes) log `OUTBOX_SET_ASIDE <id>
  <type>` (`events.py:278-286`) and page through the `outbox-set-aside` alarm
  (`infra/platform/observability.tf:159-186`, D-14, fixed in `235eeaa`); the
  runbook says how to send one again.

### 3.2 Catalogue

Consumers come from the subscriptions in `infra/platform/data.tf:6-11` (the
same list is in `local/bootstrap.py:30-63`, `infra/localstack/main.tf:27-32`
and `infra/localstack/check.py:13-46`). They match each service's handler
map: catalog `backend/services/catalog/catalog/main.py:36-44` (`HANDLERS`),
booking `backend/services/booking/booking/handlers.py:171-179`, payments
`backend/services/payments/payments/handlers.py:177`, notifications
`backend/services/notifications/notifications/handlers.py` (`handlers`). Since
`235eeaa` a test holds all of this together
(`backend/libs/cappy_common/tests/test_subscriptions.py`, D-13): the four
subscription lists must be equal, every subscribed type must be in the
catalogue and handled, and every handled type subscribed. It caught
`payment.failed` missing from the LocalStack check. The
runtime adds a revocation step in front of `person.signed_out` and
`profile.deleted` for every service with a database
(`cappy_common/guard.py:58-77`, `runtime.py:71-75`), which is why booking and
payments subscribe to `person.signed_out` without a handler of their own.
Every event also goes to analytics, scrubbed (§3.1). **PII** marks fields that are more than a
pseudonymous id. Ids (`sub`s) are pseudonymous personal data everywhere.

| Event | Producer (file:line) | Consumers | Payload (PII marked) |
|---|---|---|---|
| `booking.status_changed` | booking: `booking/repository.py` `move` (built by `status_event`, `:79-103`) | payments, notifications | `bookingId`, `from`, `to`, `by`, `requesterId`, `ownerId`, `listingId`, `title`, **`ownerName` (PII)**, **`ownerBusiness` (PII: legal name, address, register number, VAT ID)**, `amount`, `currency` (the listing's, upper-case since `747ed6b`), `refundAmount` (absent when nothing was charged, FL-8; since `7444e37` also on a `completed` that settles a dispute in part, which payments refunds and pays out the rest of), `noShow`, **`declineReason` (free text; since `22b5e0f`, only when `to` is `declined`)**, `windowStart`, `windowEnd`, `expiresAt`, and since `7444e37` `timeZone` (the snapshot's, else the market's of the currency) |
| `booking.rated` | booking: `repository.py:343-356` | catalog | `bookingId`, `ownerId`, `listingId`, `requesterId`, `outcome` {`quality`, `onTime`, **`note` (PII: free text)**, `tags`}, `at`, `ratedAt` |
| `booking.renter_rated` | booking: `repository.py:358-367` | catalog | `bookingId`, `renterId`, `ownerId`, `quality` |
| `booking.message` | booking: `booking/messages.py:191-195` | notifications | `bookingId`, `senderId`, `recipientId`, `title` (never the message text) |
| `booking.owner_reliability` | booking: `owner_reliability` (`repository.py:257-293`) and, since `61b15b8`, `owner_responsiveness` (`:214-255`; the latter on every `requested` → accepted, declined or expired) | catalog (`on_owner_reliability`: applies only the fields the event carries) | either `ownerId`, `rate`, `bookings`, `failures` (S-18), or `ownerId`, `responseMins`, `responseRate` (H-1; both null under 3 requests) |
| `moderation.person_flagged` | booking: `repository.py:245-253`, `booking/handlers.py:94-110` | catalog | `personId`, `reason`, **`details` (free text naming a booking and a suspended account)** |
| `payment.authorised` | payments: `payments/routes.py:112-114`; reconciliation `payments/jobs.py:51` (no fingerprint) | booking | `bookingId`, **`cardFingerprint` (sensitive)** |
| `payment.failed` | payments: `payments/handlers.py:78` | booking | `bookingId`, `ownerId`, `requesterId`, `stage` |
| `payment.captured` | payments: `handlers.py:81` | none (analytics only) | `bookingId`, `ownerId`, `requesterId`, `amount`, `currency` |
| `payment.refunded` | payments: `handlers.py:93` | none (analytics only) | the same |
| `payment.payout_sent` | payments: `handlers.py:129-131`, `:159-161` | notifications | the same (the owner's part), and since `22b5e0f` `title`, `windowStart` and `timeZone` copied from the `booking.status_changed` that caused it, so the notice names the listing and its start |
| `payment.identity_verified` | payments: `routes.py:282` (from either webhook, or at once with the fake) | booking; catalog since `235eeaa`, which sets `owners.verified` (`catalog/handlers.py:84-90`, F-10) | `personId` |
| `payment.payouts_ready` | payments: `routes.py:95-99`; dev CLI `payments/cli.py:80` | catalog | `ownerId`, `ready`, `asOf` |
| `profile.created` | catalog: `catalog/routes.py:340` (also when a deleted profile's `sub` signs up again, FL-11) | none (analytics only) | `ownerId`, `district` |
| `profile.deleted` | catalog: `routes.py:366` | booking, payments, notifications (each also records `revoked_sessions`; notifications deletes the Cognito user: `notifications/handlers.py:198-206`) | `ownerId` |
| `person.signed_out` | catalog: `routes.py:393` (`POST /me/sign-out-everywhere`) | booking, payments, notifications (each records `revoked_sessions`; notifications also runs `AdminUserGlobalSignOut` and deletes the person's devices and their SNS endpoints: `notifications/handlers.py:208-213`) | `personId` |
| `listing.changed` | catalog: `routes.py`; `catalog/moderation.py`; since `22b5e0f` `catalog/jobs.py:136` | booking (acts on `removed` only: `booking/handlers.py:114-128`) | `listingId`, `change` (created, updated, paused, resumed, removed, approved, and since `22b5e0f` `held` from the out-of-market job), and `by: "staff"` on a moderation removal (since `235eeaa`, FL-9), which words booking's decline reason |
| `moderation.report_received` | catalog: `moderation.py:201-210` | notifications | `reportId`, `reporterId`, **`reporterEmail` (PII)**, `targetType` |
| `moderation.decision` | catalog: `moderation.py:384-399`, `:426-437`, `:449-460` | notifications | `reportId?`, `action` (now also `remove_content`), `targetType`, `targetId`, `affectedId` (for a message or review, its author since `235eeaa`), `reporterId`, **`reporterEmail` (PII)**, **`statement` (free text)**, `statementOfReasons` |
| `moderation.owner_suspended` | catalog: `moderation.py:378`, `:448` | booking | `ownerId` |
| `moderation.owner_reinstated` | catalog: `moderation.py:475` | booking | `ownerId` |
| `listing.idle` (since `61b15b8`, H-4) | catalog: `keep_schedules_once`, `catalog/jobs.py:66` (a live, unheld listing with no window in the next 7 days, at most once a week: `listings.idle_notice_at`) | notifications (`listing_idle`, the `bookings` category) | `listingId`, `ownerId`, `title` |
| `staff.action` (since `7444e37`, H-7) | booking: `audit`, `booking/support.py:69-94` (a staff resolution, proposal, approval or rejection; a claim decision; a staff member opening a case, `read_case`, or a booking's hand-over photos, `read_evidence`, `booking/messages.py`) | catalog (`moderation.on_staff_action`: one `moderation_actions` row per event) | **`actorId` (a staff sub)**, `action`, `targetType` (`booking`), `targetId`, `personId`, **`reason` (free text: outcome, amount, reason code and the staff note)**, `requestId`, `service`, `at` |
| `booking.dispute_offer` (since `7444e37`, S-21) | booking: `make_offer`, `booking/support.py:327-339` | notifications (`dispute_offer`, the `bookings` category) | `bookingId`, `to` (the other side), `by`, `title`, `refundAmount`, `currency`, `respondBy`, `timeZone` |
| `booking.notice` (since `22b5e0f`, V5-7) | booking: `notice`, `booking/support.py:230-247`, from `settle` (every settlement: an accepted offer, a staff decision, an approval), `escalate_due`, `report_late_return` and `decide_claim` | notifications (the `kind` is the text key, the `bookings` category; the three settlements and both claim decisions always emailed) | `bookingId`, `kind` (`dispute_refunded`, `dispute_partial`, `dispute_owner_paid`, `dispute_escalated`, `claim_filed`, `claim_confirmed`, `claim_rejected`), `to` (a list of subs: both sides, or the renter for `claim_filed`), `title`, `currency`, `timeZone`, and `refundAmount` with `how` (`agreement` or `staff`) on a settlement, or `claimAmount` on a claim |

`booking.requested` and `booking.created`, declared but never produced, were
removed from the catalogue in `235eeaa` (D-12).

Since `7444e37` booking sends the `timeZone` that notifications reads on
`booking.status_changed`, `booking.dispute_offer` and `booking.notice`, so
times in emails read in the listing's zone. Since `22b5e0f` notifications
sends nothing for a `booking.status_changed` whose `from` is `disputed`
(`notifications/handlers.py:91-94`): the `booking.notice` says how it ended.

### 3.3 Producer → consumer matrix

| Producer ↓ / consumer → | catalog | booking | payments | notifications | analytics only |
|---|---|---|---|---|---|
| **catalog** | – | `listing.changed`, `moderation.owner_suspended`, `moderation.owner_reinstated`, `profile.deleted`, `person.signed_out` | `profile.deleted`, `person.signed_out` | `profile.deleted`, `person.signed_out`, `moderation.report_received`, `moderation.decision`, `listing.idle` | `profile.created` |
| **booking** | `booking.rated`, `booking.renter_rated`, `booking.owner_reliability`, `moderation.person_flagged`, `staff.action` | – | `booking.status_changed` | `booking.status_changed`, `booking.message`, `booking.dispute_offer`, `booking.notice` | – |
| **payments** | `payment.payouts_ready`, `payment.identity_verified` | `payment.authorised`, `payment.failed`, `payment.identity_verified` | – | `payment.payout_sent` | `payment.captured`, `payment.refunded` |
| **notifications** | – | – | – | – | – |

---

## 4. Who reads what across services (`/internal/*`)

Every `/internal/*` route requires `X-Internal-Token`
(`backend/libs/cappy_common/cappy_common/auth.py:242-261`), and the gateway never
forwards `/internal/*` (`gateway/routing.py:4`, `:35-36`). Since `f303350`
(P-10) each service holds only its own token, `<service>:<random>`
(`infra/platform/data.tf:150-165`, `ecs.tf:79`), and each callee accepts only
the callers in `local.internal_callers` (`data.tf:140-147`), by the sha256 of
their token in `INTERNAL_CALLERS` (`ecs.tf:71-74`, `cappy_common/settings.py:56-61`).
The check is per service, not per route: a caller may reach every internal
route of a service it is allowed to call. Deployed, a service refuses to start
without its own prefixed token and a caller list (`settings.py:147-154`).
Locally and in tests all services share one token.

| Caller → callee | Route | What crosses | Caller code | Callee code |
|---|---|---|---|---|
| matching → catalog | `POST /internal/candidates` | listings, owners, slots and districts for a search (ReadTx) | `backend/services/matching/matching/clients.py:46` | `catalog/routes.py:725-737` |
| matching → catalog | `GET /internal/listings/{id}/context` | one listing's world (ReadTx) | `matching/clients.py:51-52` | `catalog/routes.py:740-744` |
| matching → booking | `POST /internal/busy` | taken intervals (ReadTx) | `matching/clients.py:65` | `booking/routes.py:626-633` |
| booking → matching | `POST /internal/match-for-offer` | the quote (with its `currency` since `235eeaa`), listing and owner (including **owner name and business**) for a new booking | `backend/services/booking/booking/clients.py:79` | `backend/services/matching/matching/routes.py:233` |
| booking → catalog | `GET /internal/listings/{id}/handover` | **address and instructions (sensitive)**, and since `61b15b8` the exact `location` and `postalCode`, copied into `bookings.handover` at accept and, since `42c777c`, again on every read of an `accepted` or `active` booking (V4-9) | `booking/clients.py:61` | `catalog/routes.py:815-825` |
| booking → catalog | `POST /internal/media/evidence` | checks the `evidence:<name>` references are the person's own private uploads, marks them used (never swept) | `booking/clients.py:64` | `catalog/routes.py:752-764` |
| booking → catalog | `GET /internal/evidence/{name}` | **a hand-over photo's bytes**, for booking's signed link (P-27) | `booking/clients.py:66-67` | `catalog/routes.py:767-771` |
| booking → payments | `POST /internal/intents` | booking id, parties, amount, owner net, currency (the listing's) → client secret | `booking/clients.py:98` | `backend/services/payments/payments/routes.py:121` |
| booking → payments | `GET /internal/bookings/{id}/payment` (since `7444e37`, H-9) | where a booking's money stands, for the staff case view: `status`, `amount`, `ownerNet`, `currency`, `captured`, `refunded` and `paidOut` (booleans), `chargebackAt`, `updatedAt`; 404 when there is no payment | `booking/clients.py` `HttpPayments.state` | `payments/routes.py:345-375` |
| booking → matching | `POST /internal/match-for-offer` with `extension: true` (since `7444e37`, S-12) | the time straight after a booking for its renter: no lead time, and an empty `slotId` matches whichever idle slot holds the window | `booking/clients.py` | `matching/routes.py` |
| catalog → booking | `GET /internal/people/{p}/open` | open bookings count, and until when (account deletion) | `backend/services/catalog/catalog/clients.py:63-64` | `booking/routes.py:556-560` |
| catalog → booking | `GET /internal/people/{p}/export` | bookings, messages sent, evidence (with notes, and since `747ed6b` photo links signed for a day), who they blocked, `identityVerified`, `suspended`, their card fingerprints (data export; D-10) | `catalog/clients.py:66-68` | `booking/routes.py:591-633` |
| catalog → booking | `GET /internal/stats/active-people` | a count (DSA stats) | `catalog/clients.py:70-72` | `booking/routes.py:567-572` |
| catalog → booking | `GET /internal/messages/{id}` | **who wrote a reported message** (`senderId`), so moderation can suspend the author (FL-7, since `235eeaa`), and since `42c777c` so the hourly `attribute_decisions_once` can set `moderation_actions.person_id` on older message decisions | `catalog/clients.py:74-75` | `booking/routes.py:534-542` |
| catalog → booking | `POST /internal/messages/{id}/remove` | a moderation `remove_content`: the message's words are replaced | `catalog/clients.py:77-78` | `booking/routes.py:545-553` |
| catalog → payments | `GET /internal/people/{p}/open` | pending payouts (account deletion) | `catalog/clients.py:52-53` | `payments/routes.py:351-360` |
| catalog → payments | `GET /internal/people/{p}/export` | payout account, identity status (with `consentAt`, `consentVersion` since `747ed6b`), invoices (with the recipient fields), payments (charged, refunded, paid out, the renter's card fingerprint) | `catalog/clients.py:49-50` | `payments/routes.py:363-414` |
| catalog → notifications | `GET /internal/people/{p}/export` | inbox items, settings, devices (platform, registration time) and the Cognito email and locale (`signIn`) | `catalog/clients.py:96-98` | `backend/services/notifications/notifications/routes.py:184-200` |
| support (runbook) → booking | `POST /internal/bookings/{id}/resolve` | settles a dispute with the same rules as the console and the support role's limit; `by` (who decided) is required. Staff normally use `/admin/bookings/{id}/resolve`. The runbook runs it from a catalog task with catalog's token, since booking accepts only matching and catalog | `docs/runbook.md` | `booking/support.py:491-499` |

Booking's `GET /internal/people/{p}/bookings` and catalog's
`GET /internal/owners/{id}`, which had no caller, were removed in `235eeaa`
(D-12).

Services also call out to AWS and Stripe directly:

- notifications → Cognito `AdminGetUser`/`ListUsers` (email and locale), `AdminUserGlobalSignOut` and `AdminDeleteUser` (`notifications/mail.py:41-103`);
- catalog and booking → Cognito `AdminGetUser`, to check a staff account has TOTP MFA, cached 5 minutes (`cappy_common/auth.py:186-219`, P-3);
- booking → Cognito `ListUsers` with an `email = "…"` filter, to find a member's `sub` when staff search cases by email (`CognitoPeople`, `booking/clients.py`, since `7444e37`, H-9);
- notifications → SES `SendEmail` (`mail.py:106-121`);
- notifications → SNS Mobile Push, and `DeleteEndpoint` whenever a device row goes: a moved token, sign-out, sign-out-everywhere, deletion, the 10-device cap and a dead endpoint (`push.py:45-94`, D-7);
- catalog → S3 (`media/` public, `private/` evidence) and CloudFront invalidations, `/media/<name>`, through the `Cdn` seam: a taken-down listing's photos, and since `747ed6b` every file the hourly sweep deletes (`catalog/jobs.py:44`) (`catalog/media.py:116-175`, `catalog/cdn.py`, `catalog/moderation.py:242-253`, F-4);
- payments → Stripe: payments and Connect (`payments/provider.py`; since `42c777c` also the connected account's verified address, read when a fee invoice is issued, `account_address`), and Stripe Identity sessions and their redaction behind `IdentityProvider` (`payments/identity.py`, F-1).

---

## 5. Personal data map

### 5.1 Where each category lives

| Category | Our stores | Processors |
|---|---|---|
| **Identity** (account, `sub`, name) | Cognito user pool (email as username: `infra/platform/identity.tf:5-8`); `catalog.owners.name`/`initials`; copies in `bookings.listing_snapshot.ownerName` (redacted on deletion since `235eeaa`), `reviews.author`, `invoices.recipient_name`, and in events (`booking.status_changed.ownerName`) | Cognito |
| **Contact** (email, business address, VAT ID, a private owner's postal address) | Cognito `email`, `email_verified`, `locale` (`identity.tf:59-84`; since `2257182` the app writes the full locale, such as `en-US`); `owners.business`; `listing_snapshot.ownerBusiness`; `invoices.recipient_*` (since `42c777c` a private owner's `recipient_address` comes from Stripe's KYC); `reports.reporter_email`; events `reporterEmail` and `ownerBusiness`; SES account suppression list for bounces and complaints (`infra/platform/email.tf:50-51`) | Cognito, SES |
| **Messages** | `booking_messages.body`/`unmasked`; `bookings.outcome.note`, `decline_reason`; `reviews.text`; `reports.details`; `booking_evidence.note`; since `7444e37` `booking_disputes.reason`, `booking_claims.note` and `decision_note`, `booking_resolutions.note` (staff) and the audit log's `statement`; free text in `moderation.decision.statement`, `booking.rated.outcome.note`, `staff.action.reason` and, since `22b5e0f`, `booking.status_changed.declineReason` | SES, since message notices are emailed (FL-3), but only the listing title and a link, never the text (the `booking.message` event carries none) |
| **Photos** | S3 media bucket, content-addressed, versioned, old versions expire after 30 days (`infra/platform/storage.tf:10-47`): listing photos under `media/` (public through CloudFront), hand-over evidence under `private/` (CloudFront may read only `media/*`: `storage.tf:62-64`); `catalog.media`; `listings.photos`; `booking_evidence.photos`; `listing_snapshot.photo` | S3, CloudFront for listing photos only (a year of immutable caching, ADR 0007) |
| **ID checks** | Outcome and consent only: `payments.identities` (with `consent_at`, `consent_version`), `booking.verified_people`, `catalog.owners.verified` (since `235eeaa`), `payment.identity_verified`. The document and selfie stay with the provider, behind `IdentityProvider` (`payments/identity.py`), and are redacted there on deletion (`payments/tables.py:47-61`) | Stripe Identity |
| **Payments** | `payments.payments`, `invoices`, `connect_accounts`; `bookings.amount`/`refund_amount`/`currency`; **card fingerprints** in `payments.card_fingerprint`, `bookings.card_fingerprint` and `payment.authorised` (cleared on deletion, except booking's copy for a suspended person) | Stripe (cards, Connect KYC and bank details) |
| **Location** | `owners.district` and `country` (since `235eeaa`; also sent to Stripe as the Connect account's country); `listings.address` (private) and `district`; since `61b15b8` `listings.spec.location` (exact point, public only snapped to ~500 m), `country` and `postalCode` (private until accepted; since `2257182` the web sets the point to the district's centre, so it says no more than the district until a geocoder exists); `bookings.handover.address`, and its `location` and `postalCode`; `profile.created.district`. `GET /districts/nearest?lat&lng` does not store the coordinates (`catalog/routes.py:435-445`); the web keeps the chosen district in `localStorage` (`web/src/app/store.tsx:79`, `:97`) | none (Amazon Location is planned, M-7) |
| **Device tokens** | `notifications.devices.token`, `endpoint` and `install_hash`; SNS platform endpoints (deleted with their row since `235eeaa`) | SNS Mobile Push → APNs (Apple) and FCM (Google) |
| **Analytics** | S3 analytics lake: every event reduced to the allowlist in §3.1 (pseudonymous ids, statuses, amounts, times, categories, districts), gzipped JSON, 730 days, Glacier after 90 (`infra/platform/analytics.tf`, `analytics/scrub.py`); Athena `cappy_events` | Firehose, Lambda, S3, Athena |
| **Logs** | CloudWatch, 90 days in prod and 14 elsewhere (`infra/platform/ecs.tf:129-133`); client crash reports are logged with emails and phone numbers replaced (`backend/services/gateway/gateway/main.py:103-109`, P-34), other free text kept. WAF keeps no sampled requests (`sampled_requests_enabled = false` on every rule, `40fbc5f`) | CloudWatch |
| **On the device** | refresh token (`web/src/data/auth.ts:34-58`); the last session, **with the email** and staff flag, for offline starts (`cappy.session.v1`, `auth.ts:89-117`); the signed-in `sub`; drafts and flags (`web/src/app/device.ts`); language; in the store apps a random install id (`cappy.install.v1`, `web/src/native.ts:102-111`), kept across sign-outs | none |
| **Backups** | Aurora automated backups: 14 days in prod, 3 elsewhere; a final snapshot on destroy in prod (`infra/platform/data.tf:68-73`) | RDS |

### 5.2 Processors

| Processor | What it holds | Region today |
|---|---|---|
| **Amazon Cognito** | email, password hash, TOTP MFA secret (staff must have one deployed), locale, sign-in history (threat protection when on: `identity.tf:10-17`) | eu-central-1 |
| **Stripe** (Payments, Connect Express, Identity) | cards, charges, refunds, transfers; owners' KYC, bank and tax data; ID documents and selfies | Stripe's EU and US infrastructure (one DE platform account) |
| **Amazon SES** | every transactional email in transit; the suppression list | eu-central-1 |
| **SNS Mobile Push → APNs and FCM** | device tokens, notification title and body | SNS in eu-central-1; Apple and Google in the US |
| **CloudFront and WAF** | the web bundle, listing photos (cached at the edge, `PriceClass_100`: `infra/platform/edge.tf:448`), API responses (hand-over photos pass through as `private` answers), request metadata; WAF in us-east-1 | global edge; us-east-1 |
| **Aurora, S3, Firehose, Lambda, Athena, CloudWatch** | everything above | eu-central-1 |

The DPAs, records of processing and the DPIA for ID checks are business
tasks (G-B3, P-17, P-30).

### 5.3 Export coverage (`GET /me/export`)

`catalog/routes.py:397-418` assembles one JSON file, at most 5 times a day
per person (`rate_hits`, P-12), from:

- catalog `repository.export` (`catalog/repository.py:242-296`);
- booking `/internal/people/{p}/export` (`booking/routes.py:586-623`);
- payments `/internal/people/{p}/export` (`payments/routes.py:363-414`);
- notifications `/internal/people/{p}/export` (`notifications/routes.py:184-200`).

Since `235eeaa` (D-10) the register (`cappy_common/privacy.py`) marks each
table exported or not, with a reason for every table left out, and
`test_privacy.py` checks the export code touches every table marked exported.

| Data | Exported? |
|---|---|
| Profile (name, kind, district, country, business, ratings) | yes (`profile`) |
| Listings, including private address and instructions | yes (`listings`, `private=True`) |
| Saved listings | yes |
| Reviews written | yes (rating, text, date) |
| Reviews about them | yes (`reviewsAboutMe`, since `235eeaa`) |
| Photos | names and upload times (`photos`); a listing photo's file is at `/media/<name>`. Hand-over photos are in the private store, which `/media/` does not serve; booking's part links them (next row) |
| Bookings (both sides) | yes (`bookings`, as the viewer sees them) |
| Messages sent | yes, the unmasked words |
| Hand-over evidence | stage, the `note` (since `235eeaa`) and, since `747ed6b`, each photo as a booking link signed for a day (`EXPORT_LINK_TTL`, `booking/routes.py:597-625`), so the file can be saved from it. Rows from before `f303350` keep their public URLs |
| Blocks they made; verified and suspended flags; their card fingerprints (booking) | yes (`blocked`, `identityVerified`, `suspended`, `cardFingerprints`, since `235eeaa`) |
| Disputes they opened and claims they made (since `7444e37`) | yes (`disputes`: booking, reason, when, and the offer amount when the offer was theirs; `claims`: kind, minutes late, amount, note, status, when; `booking/routes.py:581-648`). Staff resolutions are not exported (register: kept for accountability); the booking's outcome and refund are |
| Payments | yes: amount, currency, status, whether charged, refunded and paid out, and the renter's card fingerprint (`235eeaa`) |
| Invoices | yes, with currency and the recipient's name, address and VAT ID (`235eeaa`) |
| Payout account, identity status | yes, as summaries (connected, payouts enabled; status and `verifiedAt`), and since `747ed6b` the recorded consent (`consentAt`, `consentVersion`, `payments/routes.py:381`) |
| Reports they filed, with their details and `reporter_email` | yes (`reportsFiled`, since `235eeaa`) |
| Moderation decisions about them | yes (`moderationDecisionsAboutMe`: action, target, statement, statement of reasons). Since `747ed6b` the query also matches `moderation_actions.person_id` (`catalog/repository.py:278`), so decisions on their messages and reviews are in. ~~Such decisions recorded before `747ed6b` are still missing~~: **fixed in `42c777c`**: migration catalog `0018` back-fills review decisions, and the hourly `attribute_decisions_once` asks booking for each message's author; a message booking no longer knows stays unattributed |
| Notifications and settings | yes |
| Push devices | yes: platform and registration time (`devices`, `235eeaa`) |
| Email and locale (Cognito) | yes (`signIn`, read from Cognito at export time, `235eeaa`) |
| Idempotency-key responses | no, by design: kept 24 h and they repeat what the export holds (register) |
| `revoked_sessions`, `booking_transitions`, `payable_owners` | no, by design (register: a pseudonymous id and a time; the audit trail of status changes, whose current state the export has; a derived flag) |
| Analytics events about them | no (pseudonymous ids and allowlisted fields only) |

### 5.4 Deletion coverage, table by table

`DELETE /me` (`catalog/routes.py:347-367`) first refuses while a booking is
open or a payout is pending: it asks booking and payments over `/internal`.
Then catalog runs `repository.forget` (`catalog/repository.py:189-240`),
records the person in its `revoked_sessions` (so their tokens stop working in
catalog at once: `routes.py:370-375`) and writes `profile.deleted` in the same
transaction. Notifications deletes the Cognito user on that event
(`AdminDeleteUser`, `notifications/handlers.py:198-206`, P-23), and booking,
payments and notifications stop honouring the person's tokens when it reaches
them (P-24; the notifications test checks deletion through the export since
`7ef9b2c`, because the old token is rightly refused). Access tokens last 15
minutes (`infra/platform/identity.tf:90-92`); only matching, which verifies
tokens but has no revocation table, still accepts one until it expires. The
app still calls Cognito `DeleteUser` itself afterwards, as the quick path, and
signs out whatever happens (`web/src/data/auth.ts:282-287`, `Profile.tsx`
`remove`). ~~The `delete_me` docstring is wrong~~: rewritten in `747ed6b` to
say what happens.

Every row below is pinned by the register (`cappy_common/privacy.py`:
`delete`, `redact` or `keep`, with the reason for each `keep`) and checked
by `test_privacy.py` (D-11, `235eeaa`).

| Store | On deletion | Where |
|---|---|---|
| Cognito user | deleted by notifications on `profile.deleted`, and by the app | `notifications/mail.py:90-98`; `auth.ts:282` |
| `revoked_sessions` (every database) | a row for the person is written (an id and a time), pruned after 25 h since `747ed6b` | `guard.py` |
| `catalog.owners` | name → "Former member", initials → "—", `business` → null, `verified` → false, `cancellation_rate`, `response_mins` and `response_rate` → null, `deleted_at` set; `district`, `country`, `adult_confirmed_at`, the rating counters and `suspended_at` kept. The same `sub` signing up again gets a fresh record (counters reset, 18+ asked again), and a suspension stays (FL-11) | `repository.py:224-238`, `:406-415` |
| `catalog.listings` | all of them (also ones removed before): soft-deleted, `title` → "Removed listing", `blurb` and `instructions` → "", `rules` and `photos` → `[]`, `address` → null; the spec's keys in `privacy.LISTING_SPEC`: `extraLabel` and `machine` → "" (since `747ed6b`), `location` and `postalCode` removed (since `42c777c`; ~~kept~~); the rest of `spec` kept | `repository.py` `forget`; `cappy_common/privacy.py` `LISTING_SPEC`, tested in `test_privacy.py` |
| `catalog.saved_listings` | deleted | `:220` |
| `catalog.payable_owners` | deleted | `:221` |
| `catalog.reviews` they wrote | author → "Former member", `author_id` → null; **`text` kept** | `:239-243` |
| `catalog.reviews` about them | kept | none |
| `catalog.media` and the S3 objects (`media/` and `private/`) | every row marked unused and dated 2000, so the next hourly sweep deletes the rows and the files in both stores, except a file another person also holds (D-1). Since `747ed6b` the sweep also purges each deleted file from CloudFront (`jobs.py:44`) | `repository.py:233`, `jobs.py:24-45` |
| `catalog.reports` they filed | `reporter_id` and `reporter_email` → null, `details` → "[removed: the account was deleted]"; the case stays (D-3). Reports about them are kept; every report loses its reporter 183 days after the decision | `repository.py:215-219`, `jobs.py:45-60` |
| `catalog.moderation_actions` | kept (DSA record) | none |
| `catalog.idempotency_keys` | deleted | `repository.py:220` (`idempotency.forget`) |
| `booking.bookings` | the row stays (accounting). `handover` → null; where they were the owner, `listing_snapshot.ownerName` → "Former member", `ownerBusiness` removed and `decline_reason` → "[removed: …]"; where they were the renter, `outcome.note` → null and `card_fingerprint` → null unless they are suspended (fraud prevention, S-17) (D-5) | `booking/handlers.py:38-65` |
| `booking.booking_messages` they sent | `body` → "[removed: the account was deleted]", `unmasked` → null | `booking/handlers.py:161-167` |
| `booking.blocks` (either side) | deleted | `:158` |
| `booking.verified_people` | deleted | `:159` |
| `booking.suspended` | kept (a suspension outlives the account) | none |
| `booking.booking_evidence` they added | `photos` → `[]`, `note` → null; the files go with catalog's sweep | `booking/handlers.py:65` |
| `booking.booking_transitions` | kept (audit trail, ids only) | none |
| `booking.booking_disputes` they opened | `reason` → "[removed: the account was deleted]"; amounts, offers and dates kept (since `7444e37`) | `booking/handlers.py:68-71` |
| `booking.booking_claims` they made | `note` → null; amounts and the decision kept (since `7444e37`) | `booking/handlers.py:72` |
| `booking.booking_resolutions` | kept (how a dispute was settled and by whom; register `keep`) | none |
| `booking.idempotency_keys` | deleted | `booking/handlers.py:169` |
| `payments.connect_accounts` | deleted locally. The Stripe account stays with Stripe | `payments/handlers.py:163-165` |
| `payments.identities` | the session is redacted at the provider (`IdentityProvider.redact`: Stripe's `verification_sessions/{id}/redact`), then the row is deleted (D-6) | `payments/handlers.py:166-170`, `payments/identity.py:105-112` |
| `payments.payments` | kept (financial); `card_fingerprint` → null on payments they were either party to | `payments/handlers.py:171-175` |
| `payments.invoices` | kept, until the issuer's period ends (§2.3) | `payments/jobs.py:61-77` |
| `notifications.devices` | deleted, each SNS platform endpoint first (D-7) | `notifications/handlers.py:188-196`, `push.py:85-94` |
| `notifications.inbox` | deleted (and otherwise kept 12 months since `747ed6b`) | `notifications/handlers.py:205` |
| `notifications.notification_prefs` | deleted | `:206` |
| `outbox` and `processed_events` | expire after 7 and 21 days | `events.py:325-326` |
| SQS DLQs | expire after 14 days | `messaging/main.tf:32` |
| **Analytics lake** | **kept 730 days**, but holds only pseudonymous ids and the allowlisted fields (§3.1), nothing that names the person once the other stores have forgotten them | `analytics.tf:18-35`, `analytics/scrub.py` |
| CloudWatch logs | expire after 90 days | `ecs.tf:132` |
| Aurora backups | expire after 14 days | `data.tf:68` |
| SES suppression list | kept (legitimate interest; removed on request, `retention.md`) | `email.tf:50-51` |
| On the device | refresh token, last session and drafts cleared by sign-out (`web/src/data/auth.ts:73-81`, `web/src/app/device.ts:69`); the install id stays | |

### 5.5 Legal retention and the gaps

The periods and legal bases, per category, are in
[`retention.md`](retention.md) (since `235eeaa`). In the code:

- **Invoices:** the issuer's period from the end of the year of issue,
  `INVOICE_RETENTION_YEARS` (10 by default: GoBD, § 147 AO, § 14b UStG;
  `retention.md` notes BEG IV may have cut it to 8 for Buchungsbelege, to be
  confirmed, G-B2). They are never changed once issued
  (`payments/tables.py:64-66`, `payments/invoices.py:65-118`), and the daily
  `purge_invoices_once` deletes them once the period ends (D-9).
- **Booking and payment records:** booking ledgers and payments count as
  business records (6 to 10 years under HGB and AO). They are kept for ever,
  redacted on deletion, and no retention job exists.
- **DSA:** notices and statements of reasons must stay available for
  complaints (Art. 20: at least 6 months after the decision). Decisions are
  kept for ever; a report's reporter and their words are cleared 183 days
  after the decision (D-3).

The gaps, with their tasks:

| Gap | Task |
|---|---|
| ~~Names, business identity and reporter emails in event payloads reach the two-year lake~~. **Fixed in `f303350`**: the Firehose scrub keeps an allowlist (§3.1). The payloads still carry them between services, in `outbox` (7 days) and the DLQs (14 days) | P-6 |
| ~~The Cognito user survives when the app skips `DeleteUser`~~. **Fixed in `f303350`** (`AdminDeleteUser` on `profile.deleted`). ~~Names still stay in booking snapshots~~: redacted since `235eeaa` (D-5) | P-23 |
| ~~Tokens stay valid for up to 60 min after deletion~~. **Fixed in `f303350`**: services with a database refuse them once the event arrives, and tokens last 15 min. Matching still accepts one until it expires | P-24 |
| ID-check data is special-category: CAI declaration, the DPA. Consent is recorded before a session starts (**`f303350`**, P-18), only the person's current session counts (**`f303350`**, P-28), ~~nothing redacts the Stripe Identity session on deletion~~ (**fixed in `235eeaa`**, D-6), and `retention.md` gives the schedule. ~~The recorded consent is not in the export~~ (**fixed in `747ed6b`**) | P-17 |
| ~~Evidence photos sit behind public URLs~~. **Fixed in `f303350`**: a private prefix and 15-minute signed links. Rows from before it keep their public URLs | P-27 |
| Client error logs keep free text. **Partly fixed in `f303350`**: emails and phone numbers are replaced, and the per-address limit uses the trusted proxy hop | P-34 |
| ~~WAF sampled requests keep headers in us-east-1~~. **Fixed in `40fbc5f`** (sampled requests off on every rule) | P-20 |
| ~~Photos, listing text and `instructions` survive deletion; `reports` have no retention; `idempotency_keys` are kept for ever; SNS endpoints are not deleted; the export misses Cognito email and locale, reports, decisions, reviews about them, blocks, flags, fingerprints, invoice recipients, charges and refunds, devices and evidence notes; no invoice purge; no test that catches the next table~~. **Fixed in `235eeaa`** | D-1 to D-11 |
| The privacy policy omits categories: messages, photos, reports, ID checks, push. **Partly fixed in `2257182`**: the English policy now lists them like the German, and a French one exists; all three are copy for counsel, not reviewed | P-15, P-16 |
| No breach process or incident register | P-13 |
| Nothing documents the transfers (US and Canadian data in Frankfurt; EU data to US processors) | P-19 |
| No CCPA/CPRA request process | P-29 |
| No DPAs, records of processing or DPIA | G-B3, P-30 |
| ~~CloudFront keeps a deleted person's listing photos; the export gives hand-over photos as unusable `evidence:` references, omits the ID-check consent and misses moderation decisions on the person's messages and reviews; the `inbox` has no retention; `revoked_sessions` rows are kept for ever; a listing's `spec` free text survives deletion; the `delete_me` docstring is wrong~~. **Fixed in `747ed6b`**; ~~message and review decisions recorded before it stay unattributed~~: **fixed in `42c777c`** (migration 0018, `attribute_decisions_once`) | none |
| ~~A deleted person's listings keep `spec.location` and `spec.postalCode`~~. **Fixed in `42c777c`**: `forget` drops both (`privacy.LISTING_SPEC`, tested) | M-6 |

---

## 6. Money data

- **Minor units, as integers:** `Cents = int` (`backend/libs/cappy_common/cappy_common/models.py:19`).
  - Quotes: `backend/services/matching/matching/domain/pricing.py:54-73`.
  - Bookings: `bookings.amount` and `refund_amount`.
  - Payments: `amount` and `owner_net`.
  - Invoices: `net`, `vat` and `gross`.
  - Events: `amount`.
  - No floats anywhere on the money path.
- **Currency** (M-3, since `235eeaa`): every listing carries one of thirteen
  ISO 4217 codes (ISK added in `747ed6b`), upper-case (`Currency`,
  `cappy_common/models.py`; stored in `listings.spec`). Since `747ed6b` a
  listing without one takes its owner's market's currency, and another one
  is refused (`currency_not_in_market`). A quote carries its listing's
  (`Quote.currency`, set at `pricing.py:64`). **Upper-case everywhere since
  `747ed6b`:** the booking (`Booking.currency`, default `"EUR"`; the column
  has no default), the intent (which accepts either case and stores
  upper-case), `payments.currency`, `invoices.currency`,
  `booking.status_changed.currency` and the cancellation quote. Migrations
  booking `0015_currency_upper` and payments `0009_currency_upper` upper-cased
  existing rows. Only the Stripe adapter lower-cases it
  (`payments/provider.py`, `create_intent` and `transfer`). Nothing converts
  between currencies.
- **Market thresholds** (M-2, since `747ed6b`): `cappy_common/markets.json`
  holds, per country, `id_check_above`, `held_listing_above` and
  `max_rate_per_hour` in the market's own minor units (DE and AT: 30 000,
  10 000 and 1 000 000 EUR cents; CH: 28 000, 9 500 and 950 000 CHF
  centimes), and since `7444e37` `refund_limit_support` and
  `refund_limit_lead` (what one staff member may refund alone when settling
  a dispute: DE and AT 25 000 and 250 000 cents, CH 23 300 and 233 300
  centimes; above it a second staff member approves) and `late_fee_cap` (DE,
  AT 5 000; CH 4 700), plus `time_zone` (the market's main IANA zone, the
  default when a listing names none). A booking stores only its currency, so
  these are looked up by `market_of_currency` (the live market with that
  currency; markets sharing a currency share the values). Booking's ID-check gate and catalog's held-listing rule use the
  listing owner's market (`market(owner.country)`); `_check_numbers` caps
  every money field at the market's `max_rate_per_hour`.
  `VERIFY_ABOVE_CENTS`, `REVIEW_ABOVE_CENTS`, `_MONEY_SCALE` and
  `PAYOUT_COUNTRIES` are gone. Emails format amounts per currency and
  language (`money`, `notifications/texts.py`, HUF and ISK without
  decimals).
- **Fee:** 15% (`PLATFORM_FEE_BPS = 1500`, `pricing.py:14`), inside the total.
  `owner_net = total - fee` (`pricing.py:61-72`). A partial refund pays the
  owner their pro-rata share of what is kept (`payments/handlers.py:98-135`):
  a late cancellation, and since `7444e37` a dispute settled in part (a
  `completed` with `refundAmount`); the payment then ends
  `partially_refunded` (since `22b5e0f`; `refunded` only for the whole
  amount). A late-return claim moves no money (S-12 waits on S-9).
  `markets.json` has no fee field, so the fee is still one for every market.
- **Invoices** (`payments/invoices.py`) are issued once per booking, at the
  payout or when a late cancellation keeps a fee (`payments/handlers.py:107-115`, `:134-142`).
  - **Numbering:** `CAP-<year>-<7 digits>`, one series per calendar year of
    the issuer's time zone (Europe/Berlin), with no gaps. The number is taken
    under a row lock on `invoice_counters` (`invoices.py:74-88`).
  - A redelivered event finds the existing invoice (`invoices.py:69-73`).
  - VAT: German 19% included, by default (`invoices.py:33-48`, from settings: `:51-52`).
  - The recipient fields are copied from `ownerBusiness`, or from `ownerName`,
    in the event (`invoices.py:84-102`). Since `42c777c` (V4-7) a private
    owner's address is the one the payout provider verified
    (`Provider.account_address`, asked for at issue, best effort), so the
    invoice names the recipient's address as § 14 (4) Nr. 1 UStG requires.
  - Per-entity series, templates and tax come with M-11, M-12 and M-13.
- **Stripe** (ADR 0005): the request authorises, the accept captures, and
  completion transfers (separate charges and transfers). A cancellation
  before the accept releases the hold and records no `refund_amount` (FL-8,
  `booking/routes.py:228-231`, `:327-329`; `cancellation.py` returns 0 when
  nothing was charged). Webhooks are the source of truth. They are
  signature-verified and handled once per Stripe event id
  (`payments/routes.py:419-460`). Chargebacks hold payouts
  (`payments/routes.py:450-457`, `handlers.py:122-124`). Connect accounts are
  created in the owner's country with the full service agreement
  (`payments/provider.py:160-175`), M-9, and since `747ed6b` only in a live
  market (DE, AT, CH; others get 422 `country_unsupported`,
  `payments/routes.py:236`).
- **Reconciliation:** every ~5 minutes (`payments/jobs.py:80-82`), intents
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
  throwaway SQLite (`runtime.py:82-87`).
- **Expand and contract:** new code must work with the schema before and
  after its migration, so a rollback never needs a down-migration
  (`migrations.py:5-7`).
  Destructive migrations check the data first. For example, 0003 refuses to
  add the exclusion constraint while overlapping bookings exist
  (`booking/migrations/versions/0003_completed_bookings_keep_their_window.py:34-48`).
- **Deploy order:** the CD pipeline runs every service's `migrate` task, and
  **no service rolls unless every one exits 0** (`.github/workflows/deploy.yml:93-114`).
  With `ADMIN_DATABASE_URL`, the task first creates or rotates the service's
  role and database (`migrations.py:116-131`).
- **Drift checks.** In each `test_<service>_postgres.py`, run by `make test-pg`
  (`Makefile:41-42`) and in CI with a Postgres service (`.github/workflows/ci.yml:19-40`):
  - `test_migrations_build_exactly_the_models` upgrades a fresh database to
    head and asserts that Alembic's `compare_metadata` against the models is
    empty (for example `backend/services/catalog/tests/test_catalog_postgres.py:25-35`).
  - Only the raw-SQL trigram indexes are allowed to differ (`catalog/tables.py:125`).
  - `make test` (SQLite) does not run these checks.
- **Subscriptions agree** (since `235eeaa`, D-13):
  `backend/libs/cappy_common/tests/test_subscriptions.py`, in `make test`,
  fails when the Terraform subscriptions (`infra/platform/data.tf:6-11`),
  `infra/localstack/main.tf:27-32`, `infra/localstack/check.py` and
  `local/bootstrap.py:30-63` differ, or when a service's handler map and its
  subscriptions disagree (§3.2).
- **Personal data is accounted for** (since `235eeaa`, D-11):
  `backend/libs/cappy_common/tests/test_privacy.py`, in `make test`, fails
  when a table with a person-id column is not in `cappy_common/privacy.py`, or
  when deletion or export ignores a table the register says they touch.

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
  market config (`cappy_common/markets.json`, built since `747ed6b`: each
  market names its `cell`, `eu` or `na`) and DNS are global.
- A person belongs to one cell, chosen from their country at sign-up. The app
  stores the cell and talks to `https://<cell>.api.<domain>` (M-22). Someone
  with accounts in both cells has two separate accounts, each exported and
  deleted separately.
- A listing's market is its owner's today (`747ed6b`); from its geocoded
  address once there is a geocoder (M-7; listings carry a `country` since
  `61b15b8`, but nothing uses it for the market yet). A booking
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
  processor). Update §5.3 and §5.4 and the register in
  `cappy_common/privacy.py` (its test fails otherwise), and add a task to
  `docs/TASKS.md` for any new gap;
- retention (prune constants, lifecycle rules, log retention, backups, the
  catalog and payments jobs). Update §1, §2 and §5, and `retention.md`;
- money types, currency, fees or invoices. Update §6;
- migration tooling or CI drift checks. Update §7;
- cells or regions (ADR 0013, `infra/envs/*`). Update §8.

Check that the line references still point at the right code.
