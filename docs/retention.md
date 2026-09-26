# What we keep, for how long, and why

Every category of personal data Cappy keeps, the legal basis for keeping it,
and when it goes. Deletion paths are in [`DATA.md`](DATA.md); the test
`backend/libs/cappy_common/tests/test_privacy.py` fails when a table holding a
person's id is missing from the register in `cappy_common/privacy.py`.
Markets are Europe, the US and Canada (GOAL 16): periods marked **(market)**
are settings per issuing entity, not constants. Counsel confirms the periods
before launch in each market (G-B2, G-B3).

| Data | Kept | Basis | Then |
|---|---|---|---|
| Profile, listings, saved, photos | While the account exists | Contract (GDPR 6(1)(b)) | Deleted with the account; photos swept within the hour |
| Messages | While the account exists | Contract | The deleted person's words are replaced by "[removed]"; the other side keeps the conversation's shape |
| Bookings (dates, amounts, status) | For accounting | Legal obligation (6(1)(c)): commercial and tax records | Names, hand-over address and instructions, notes and evidence redacted on deletion; the row stays |
| Fee invoices | **(market)** Germany 10 years from the end of the year of issue (§ 147 AO; BEG IV shortened Buchungsbelege to 8 from 2025 — confirm), Austria 7, Canada 6, US states typically 7 | Legal obligation | Deleted by `purge_invoices_once` (daily) |
| Card fingerprint | While the account exists; a suspended person's for as long as the suspension matters | Legitimate interest (6(1)(f)): fraud prevention (S-17) | Cleared on deletion unless suspended |
| ID check (document, selfie) | At Stripe Identity, per its retention; our row only the status | Consent (P-18; Art. 9(2)(a) for the biometric check) | Redacted at the provider on deletion (D-6) |
| Reports: reporter's email and words | Until 6 months after the decision (DSA Art. 20 contest window) | Legal obligation (DSA Art. 16/17) | Redacted by `forget_reporters_once`; the case and the statement of reasons stay |
| Moderation decisions, statements of reasons | For the DSA record | Legal obligation (DSA Art. 17, 24) | Kept; they name the target by id |
| Notifications inbox | 12 months (`INBOX_RETENTION_DAYS`, hourly job), or until the account goes | Contract | Deleted with the account |
| Notification settings, devices | While the account exists | Contract | Deleted with the account; push endpoints deleted at SNS (D-7) |
| Idempotency answers | 24 hours | Contract (safe retries) | Expired hourly; deleted with the account |
| Revoked sessions | One row per person: an id and a timestamp | Security (6(1)(f)): tokens issued before it stop working | Kept; holds nothing but the pseudonymous id |
| Analytics lake | 2 years | Legitimate interest: product statistics | Only pseudonymous ids and allowlisted fields ever arrive (`scrub.py`) |
| SES account suppression list | Until removed | Legitimate interest: not mailing addresses that bounced or complained (also protects the sending reputation that sign-up codes depend on) | An address is removed on request (`aws sesv2 delete-suppressed-destination`) |
| Logs | 90 days in prod, 14 in staging (CloudWatch, `ecs.tf`) | Security and operations | Expire |
| Cognito sign-in | While the account exists | Contract | Deleted with the account (P-23) |
