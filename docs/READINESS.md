# Production readiness scoreboard

**Ready for production** means that real people in the first market (DE/AT/CH) can sign up, list, book, pay and be paid out, on the web and in both stores. It must be lawful to run, safe for their data and money, and operable by an on-call human who is paged, has a runbook, and can roll back. The experience must also hold up against the best apps (GOAL 18). Each criterion below must be ✅ with evidence, or waived in writing by the owner.

**Verdict: NO-GO** (48 ✅ · 35 🟡 · 12 ❌ · 13 ⛔ of 108; §1-13 alone 48 / 24 / 11 / 13). Since the last round the gap has narrowed a lot (faebae7). The Impressum can no longer ship empty. Breach, chargeback and paging procedures exist. AWS security logging, locked backups, budgets and CI-gated deploys are in Terraform. `make test` is at 644 passed. Four technical problems still stop a launch:
- The card step has never run in a browser with Stripe test keys under the prod CSP.
- No verification round has passed clean, and none has walked the UX build at all.
- A rollback across a release that added a migration fails at the migrate step.
- An owner's chargeback debt is recorded but never collected, although the runbook says it is.

The owner's legal, insurance, AWS, store and Stripe steps are all still open.

Reviewed 2026-09-26 at `0a74b1c` (branch `prod-readiness`), read-only. Previous round: `edaccc1` (43 ✅, 23 🟡, 19 ❌, 11 ⛔). Status: ✅ met · 🟡 partial · ❌ not met · ⛔ blocked on the owner. Task ids refer to [`TASKS.md`](TASKS.md). `R2-n` tasks are from the readiness reviews; R2-19 and later are new in this round.

What was run this round:
- `make test`: `644 passed, 14 skipped` (the 14 are the Postgres and stripe-mock tests, which run in CI with services, `ci.yml`).
- Web:
  - `tsc --noEmit` is clean.
  - `check:i18n`: "1410 German and 1410 French entries, same keys, placeholders match".
  - `check:flags`, `check:a11y`, `check:attempt` and `check:money` pass.
  - `check:tokens`: "no new literals (text size 0, radius 0, hex 1, rgba 7, named colour 0, inline font size 1)".
  - `check:contrast`: "40 pairs pass in light and dark".
  - `check:size`: entry "154.5 kB gzipped (budget 170 kB)". This was measured on the existing `web/dist`, built 20:16:18, the time of `0a74b1c`. It was not rebuilt.
- Read-only curl against `localhost:8000/api`:
  - `/categories` answers 200.
  - `/inbox` and `/admin/payments/chargebacks` answer 401 signed out.
  - `/internal/busy` answers 404.
  - Headers seen: `x-request-id`, HSTS with preload, `nosniff`, `DENY`, `strict-origin-when-cross-origin`.
- **Not run:** `make e2e`, `make test-pg` and the load scripts, because they write to the running stack. Anything that needs real AWS, Stripe live, a browser walk or a device was **not verified**.
- **Verification round 8** (TASKS "V8") ran at `25e79d3`, before the UX build (`1daf0da`) and the V8 fixes (`933ed14`, `0a74b1c`). It found 23 items, and 20 are ticked. Nothing built since has been walked in a browser.

## Sources: what a readiness review covers

| Framework | What it asks, in short | Source |
|---|---|---|
| Google SRE Production Readiness Review | System design and dependencies, observability of user-visible failures, emergency response and change management, performance against SLOs, safe rollout, incident history | https://sre.google/sre-book/evolving-sre-engagement-model/ |
| AWS Well-Architected | Six pillars: operational excellence, security, reliability, performance efficiency, cost optimisation, sustainability | https://docs.aws.amazon.com/wellarchitected/latest/framework/the-pillars-of-the-framework.html |
| OWASP ASVS 5.0.0 (May 2025), L2 | The level for applications that handle sensitive data: authentication, sessions, access control, input validation, cryptography, error handling and logging, data protection, API, configuration | https://github.com/OWASP/ASVS |
| PCI DSS v4.0.1, SAQ A | For fully outsourced card entry (iframes). Since 31 Mar 2025, 6.4.3 and 11.6.1 are out of SAQ A. The merchant must instead "confirm their site is not susceptible to attacks from scripts that could affect the merchant's e-commerce system(s)" and attest every year | https://blog.pcisecuritystandards.org/important-updates-announced-for-merchants-validating-to-self-assessment-questionnaire-a · https://docs.stripe.com/security/guide |
| Stripe.js CSP | `script-src`/`frame-src` need `https://*.js.stripe.com` and `https://js.stripe.com`. `frame-src` needs `https://hooks.stripe.com` for 3DS. `connect-src` needs `https://api.stripe.com` | https://docs.stripe.com/security/guide |
| App Store | Review Guidelines 1.2 (UGC), 2.1 (demo account), 3.1.3(e), 4.2, 4.8, 5.1.1(v). Privacy manifest, privacy label, DSA trader status, age rating | https://developer.apple.com/app-store/review/guidelines/ · [`research/2026-09-store-and-marketplace.md`](research/2026-09-store-and-marketplace.md) §1 |
| Google Play launch checklist | Privacy policy, App content declarations (ads, target audience, permissions, Data safety), sign-in instructions for review, content rating; for personal accounts, 12 testers for 14 days | https://support.google.com/googleplay/android-developer/answer/9859455 · https://support.google.com/googleplay/android-developer/answer/14151465 |
| GDPR operational duties | Records of processing (Art. 30), processor contracts (Art. 28), DPIA (Art. 35), breach notice within 72 h (Art. 33/34), data-subject rights (Art. 15-22) | https://gdpr-info.eu/art-33-gdpr/ · https://gdpr-info.eu/art-30-gdpr/ · https://gdpr-info.eu/art-35-gdpr/ |
| CCPA/CPRA | Notice at collection, request handling in 45 days, "do not sell or share". Only for the US cell | https://oag.ca.gov/privacy/ccpa |
| PIPEDA | Report breaches with a "real risk of significant harm", keep a record of **every** breach for two years. Only for Canada | https://www.priv.gc.ca/en/privacy-topics/business-privacy/breaches-and-safeguards/privacy-breaches-at-your-business/gd_pb_201810/ |
| Marketplace launch (trust and safety, support, payouts) | DSA Art. 11-18 from day one, notice-and-action, statements of reasons, trader identity (§ 5b UWG), insurance or guarantee, damage claims, dispute flow, chargebacks, DAC7 | [`research/2026-09-launch-gaps.md`](research/2026-09-launch-gaps.md) · [`research/2026-09-store-and-marketplace.md`](research/2026-09-store-and-marketplace.md) §2-3 · https://dsa-library.com/article/16/ |
| UI/UX (GOAL 18) | Apple HIG, Material 3, WCAG 2.2 AA, Core Web Vitals; the 12 criteria in §6 of the UI/UX review | [`research/2026-09-ui-ux-review.md`](research/2026-09-ui-ux-review.md) §6 · https://web.dev/articles/vitals |

## 1. Product completeness

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Sign-up with email verification, password reset, sign-in with a TOTP step | ✅ | PLAN Phase 9; `web/src/data/cognito.ts`; P-4 | TOTP not verifiable on cognito-local → R2-7 |
| Listing with photos, search, booking with authorise → capture → payout → refund, reviews, saved | ✅ | PLAN Phase 11 e2e journey; GOAL "Complete" ticked; V8 scripts 5, 8, 10, 12, 16 pass | `make e2e` not re-run this round (not verified) |
| Members only, enforced by the server | ✅ | curl: `/inbox` and `/admin/payments/chargebacks` 401 signed out, `/categories` 200; ADR/GOAL 13 | — |
| Welcome for first-timers | ✅ | U-2, U-3; example rentals with prices (UX-30, `58effe0`) | — |
| Messaging, blocks, reports, disputes, late return, extension, no-show | ✅ | G-3, G-4, S-11, S-12, S-21; an Inbox destination backed by `GET /api/inbox` with read receipts (`booking/inbox.py`, `933ed14`; web `0a74b1c`); V8 scripts 11, 13, 25, 26 pass | — |
| Owner damage claim and collecting on it | ⛔ | S-8, S-9 open | Blocked on insurance G-B1 |
| Independent verification: a full pass that finds nothing (GOAL 9) | ❌ | V8 (at `25e79d3`) found 23 items, and scripts 2, 4, 7, 9, 19, 23, 27 failed. 20 items are fixed (`933ed14`, `0a74b1c`); V8-20, V8-21 and V8-23 are open. No round has run since, and the whole UX build (`1daf0da`) is unwalked | R2-11, R2-22 |
| Help centre and a support contact | 🟡 | `Help.tsx`. The support address `VITE_LEGAL_EMAIL` now reaches the deployed build (`infra/platform/outputs.tf:52`, `faebae7`), and a release build refuses to build without it (`web/vite.config.ts:71`). No contact form | H-10; address value ⛔ V1-3 |

## 2. Correctness and data integrity

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| No double booking under concurrency | ✅ | `test_simultaneous_bookings_of_one_window_yield_exactly_one` (`booking/tests/test_booking_postgres.py:37`, runs in CI with Postgres); resilience F12 | — |
| No lost or phantom events (outbox, idempotent consumers) | ✅ | ADR 0003; resilience F27-F28; `outbox-set-aside` alarm | — |
| Idempotent webhooks | ✅ | `test_webhook_authorises_once_and_rejects_forgeries`, `test_a_lost_webhook_is_made_good_by_reconciliation` (`payments/tests/test_payments_api.py`) | — |
| Migrations match the models (drift) | ✅ | `test_migrations_build_exactly_the_models` (`test_booking_postgres.py:26`); new 0011 (payments), 0017 (booking), 0022/0023 (catalog) covered by the same test in CI | — |
| No startup path deletes data; demo only by CLI | ✅ | ADR 0010; `test_prod_refuses_unsafe_settings` (`cappy_common/tests/test_foundations.py`) | — |
| Money shown equals money moved (refunds, no-shows) | ✅ | `check:money` passes; V8-1 (held total) and V8-2 (Earn and Profile from `charged − refunded` / `ownerShare`) fixed in `0a74b1c` | Not re-walked in a browser (R2-22) |
| Chargeback lifecycle | 🟡 | Every `charge.dispute.*` event is handled (`payments/routes.py:489-560`, `faebae7`): a win pays out the held payout, a loss reverses the transfer or records `owner_owes`. There is a staff list and audited evidence submission, tested by `test_a_won_chargeback_pays_out_what_it_held` and `test_a_lost_chargeback_takes_the_payout_back_or_records_the_debt` (`test_payments_api.py:877,906`). **But** `owner_owes` is only written (`routes.py:548`) and listed (`:577`). No payout deducts it, although runbook "A chargeback" says "it is taken from their next payout". Staff have no console screen: the runbook has them POST to the API by hand | R2-20, R2-24 |
| Housekeeping tables pruned | ✅ | `prune_guards` (`cappy_common/guard.py:56-64`); PLAN reconciled (R2-12, `faebae7`) | — |

## 3. Security (OWASP ASVS L2 lens)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Authentication: JWKS verification, no trusted identity header, 15-min access tokens, revocation | ✅ | PLAN DoD "Safe"; P-24; V8 script 21 (the old token got 401 at once) | V8-23 (the toast after "Sign out everywhere", unconfirmed) |
| Staff MFA and four eyes | 🟡 | P-3, P-4, H-6; prod refuses `ADMIN_MFA_REQUIRED` off | Never exercised against real Cognito; V8 script 24 four-eyes blocked → R2-7 |
| Access control: `/internal` unreachable, per-caller internal tokens | ✅ | curl `/api/internal/busy` 404; P-10; `test_prod_needs_per_caller_internal_tokens` | — |
| Input limits, rate limits, load shedding | ✅ | P-1, P-12, P-22, T-01; WAF rate rules `edge.tf` | Per-user limits beyond these: runbook "Known limits" (accepted) |
| Security headers and CSP | 🟡 | Headers seen by curl. The Stripe.js CSP now follows Stripe's guide (`edge.tf:415`, `:421-422`, `faebae7`). `style-src 'unsafe-inline'` remains (`edge.tf:418`). Not checked against a deployed page | P-26, R2-2 |
| Encryption in transit and at rest | ✅ | INFRA §4 "Encryption"; `data.tf`; P-11 Service Connect TLS, `verify-full` | Validated only, never applied (GOAL 12) |
| Secrets out of the repository | 🟡 | `.env` ignored. The LocalStack and GitHub tokens pasted in chat are not rotated, and `Capacity_Exchange_*.pptx` are still in history (`0ba8d2c`) | ⛔ R2-13 |
| Supply chain | 🟡 | `pip-audit --strict`, `npm audit --omit=dev` in CI; Dependabot; actions pinned by tag, not SHA | P-32 note (SHA pins) |
| Detection: CloudTrail, GuardDuty, Security Hub | ✅ | `infra/platform/security.tf` (`faebae7`): a multi-region trail with log validation into an object-locked bucket (`:13-104`), GuardDuty (`:105`), Security Hub with the foundational standard (`:111-121`), and alarms for root use and IAM changes (`:172-195`). On by default (`variables.tf:130-134`) | Validated only, never applied. Topic policies lack a source condition → R2-23 |
| Event forgery between services | 🟡 | Notifications' `sns:Publish` is scoped to `endpoint/*` (`ecs.tf`). There is still no publisher allow-list policy on the events topic (only `alarms` and `tickets` got topic policies) | P-9 |
| WAF sampled requests keep no tokens | ✅ | Every `sampled_requests_enabled = false`; P-20 ticked (R2-12) | — |
| Store shells hardened | ❌ | `external-path` in `android/.../xml/file_paths.xml:3`; `minifyEnabled false`; `<access origin="*" />`; refresh token in Preferences (`web/src/native.ts`); no CSP in the shells. Unchanged | P-31, P-5, U-17 |
| Independent penetration test before real money | ❌ | Internal reviews only | R2-17 |

## 4. Privacy and legal

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Impressum and DSA Art. 11/12 contact points **in the deployed build** | ⛔ | Technically closed in `faebae7`. `web_config` carries `VITE_LEGAL_COMPANY/ADDRESS/EMAIL/VAT/REGISTER` from `var.legal` (`outputs.tf:45-60`), and the deploy writes them to `.env.production.local` (`deploy.yml:196`). A release build refuses to build without company, address and email (`vite.config.ts:68-92`). `var.legal` has no default. What is left is the owner's details. `releaseProblems` has no test | ⛔ V1-3; R2-21 (test) |
| Data export and deletion (Art. 15/17/20), register tested | ✅ | `test_every_table_holding_a_person_is_in_the_register` (`cappy_common/tests/test_privacy.py`); D-27 done (`933ed14`) | — |
| Retention schedule | 🟡 | [`retention.md`](retention.md); counsel confirms the periods | ⛔ G-B3 |
| Privacy policy complete in every language shown in DACH | 🟡 | The German policy is complete. The English one omits messages, photos, reports, ID checks and push, and the two drift apart | P-15, P-16 |
| RoPA, DPAs, DPIA for ID checks | ⛔ | G-B3, P-17 | Owner with counsel |
| Breach procedure (GDPR 72 h) and incident register | ✅ | Runbook "Security or personal-data incident (a breach)" (`runbook.md:123`) with the notification table; [`incidents/TEMPLATE.md`](incidents/TEMPLATE.md) as the register entry and [`incidents/POSTMORTEM.md`](incidents/POSTMORTEM.md); P-13 ticked (`faebae7`) | Counsel reviews it with G-B3 |
| Consumer law at checkout (PAngV, § 312j, withdrawal button, trader label, § 5b UWG) | 🟡 | G-6, S-4; the amount is on the pay button (UX-23, `fbbfe25`). Withdrawal is not varied by category | ⛔ S-19 (counsel) |
| Terms, age 18+, P2B | ⛔ | G-B2, S-5, S-22 | Counsel |
| DAC7 | ⛔ | G-10 (tags done); G-B4; S-31 | Owner |
| Cookie/TDDDG consent not needed | ✅ | Server-side analytics only; fonts self-hosted; the theme choice is device-local (`theme.ts`) and needs no consent | Keep crash reports identifier-free |

## 5. Payments and money

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Card data never touches Cappy (SAQ A shape) | ✅ | Payment Element in an iframe (`PayStep.tsx`), themed with the Appearance API (UX-24, `58effe0`); ADR 0005 | Annual SAQ A attestation → R2-15 |
| SAQ A eligibility: the site is not open to script attacks | 🟡 | Strict `script-src 'self'` plus Stripe only (`edge.tf:415`) | Not verified against a deployed page; R2-2 |
| Card step in a real browser with Stripe test keys, 3DS, under the prod CSP | ❌ | PLAN Phase 9 box still unticked. R2-2's walk is still open. V8 script 6 "fake provider only". Wallets were added to the Payment Element (`0a74b1c`) and are also untested | R2-2 |
| Webhooks subscribed to what is handled | ✅ | Runbook step 4 (`runbook.md:44`) lists every `charge.dispute.*` kind that `routes.py:489` now handles | — |
| Reconciliation, retries, payout kill switch | ✅ | R-1, T-16, R-10; resilience F16-F21 | — |
| Fee invoices, gapless numbers | 🟡 | G-11; 19% German VAT for everyone (`payments/invoices.py:44`) | M-12, ⛔ M-11/G-B2 |
| Stripe live platform activated (Connect Express, Identity, Radar, negative-balance liability) | ⛔ | Runbook "First deploy" step 4 | R2-15 |

## 6. Reliability and resilience

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Failure catalogue with a decision for each scenario | ✅ | [`resilience.md`](resilience.md) F1-F36 | — |
| Multi-AZ, deletion protection, PITR 14 days | ✅ | `data.tf` | — |
| Backups out of reach of a compromised deploy role | ✅ | `infra/platform/backup.tf:10-70` (`faebae7`): AWS Backup daily (35 days) and monthly (365 in prod) for Aurora and the media bucket, into a vault under Vault Lock (`min_retention_days` 35, `changeable_for_days` 3), so no role can delete a recovery point early. Failed jobs open a ticket (`:72-84`) | Validated only. The copy is in the same account and region (a ponytail, `backup.tf:6-8`); a second copy is after launch |
| Restore rehearsed; RTO known | ❌ | "Last rehearsal: never. Do one before launch." (`runbook.md:331`) | R2-7 (needs the first AWS apply) |
| Game day | ❌ | Runbook table; none run | R2-7 |
| Region loss | 🟡 | Decided: one region, RTO hours (T-26) | Accepted for launch |

## 7. Performance and capacity

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| No query whose cost grows with the database | ✅ | [`bench.md`](bench.md); the inbox query is new (`booking/inbox.py`) and is not benched | Bench `GET /inbox` with the next L-run (not verified) |
| Load, spike, soak (local) | ✅ | L-1, L-2, L-3 | — |
| Mixed open-model journeys | 🟡 | `make load-mixed` exists; no result recorded | L-4 |
| Sized on real AWS (breakpoint, ACUs, task maxima) | ⛔ | Never applied (GOAL 12) | L-5 |
| Connection budget | ✅ | Terraform `check` (`data.tf`) | — |
| Web budget | ✅ | `check:size` 154.5 kB gz of 170 kB (up 4.9 kB since the last round) | Web vitals UX-45/S-23 |
| App cold start | ❌ | Not measured | S-24 |

## 8. Operability (observability, alerts, runbooks, on-call)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Structured logs with a request id, traces | ✅ | `x-request-id` in curl; T-33 ADOT → X-Ray | — |
| SLOs and burn-rate alarms per journey | ✅ | [`slo.md`](slo.md); `observability.tf` | — |
| Synthetic canary | ✅ | `synthetics.tf`; T-34 | — |
| Alarms reach a human who is paged | 🟡 | `faebae7` splits page and ticket topics (`observability.tf:9-15`) and subscribes a pager to pages when `pager_endpoint` is set (`:29-35`). Runbook "Severity and on-call" (`runbook.md:99`) and the postmortem template are in. But `check "prod_has_a_pager"` (`:37-42`) only warns. The pager service, its URL and the rota are the owner's | ⛔ R2-6 (rota, pager account) |
| Runbooks: alarms, disputes, moderation, kill switches, restore, rollback, breach, chargebacks | 🟡 | Breach (`runbook.md:123`), chargeback (`:156`) and releasing and rolling back (`:55`) added in `faebae7` | No store release (S-25). "A chargeback" promises a deduction that does not exist (R2-20). Rollback as written fails across migrations (R2-19) |
| Dashboards | 🟡 | None in Terraform; Container Insights, X-Ray | M-45 (later) |
| Public status page | ❌ | — | H-22 |

## 9. Delivery (CI/CD, migrations, rollback)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| CI lints, tests, audits, builds images, validates Terraform, runs e2e | ✅ | `ci.yml` jobs backend, web (now with `check:contrast` and `check:tokens`, `ci.yml:71-72`), images, infra, e2e | e2e skipped without `LOCALSTACK_AUTH_TOKEN` |
| CD with OIDC, migrations before the roll, automatic rollback | ✅ | `deploy.yml:130-152`; ECS circuit breaker and alarms (`deploy.yml:165-170` checks what is running) | — |
| Prod deploy only for a SHA that CI passed | ✅ | `deploy.yml:7-11` (`workflow_run` on `ci` for main), and the `gate` job (`:38-51`) refuses any sha without a successful `ci` run on main, also for a manual run (`faebae7`) | — |
| One-step rollback to a named release | 🟡 | A `release:` input redeploys any sha (`deploy.yml:19-22`, `:35`). **But** the jobs check out that sha (`:66-67`, `:113-114`), run its migrate task, and apply its Terraform. `cappy_common/migrations.py:131` runs `upgrade head` with the old code. When the database is at a revision the old code does not have, Alembic cannot locate it, and the job stops with "a migration failed; nothing was rolled out" (`deploy.yml:152`). So a rollback past any release that added a migration fails. Applying an older Terraform would also try to destroy what came later, and a Vault-Locked vault cannot be destroyed | R2-19 |
| Web deploy doesn't break open sessions | 🟡 | No `--delete`; assets older than 30 days and gone from the build are pruned (`deploy.yml:237-247`, `faebae7`) | Reload on `vite:preloadError` still missing (`grep -r preloadError web/src` finds nothing) → R2-9 |
| Expand-then-contract migrations | ✅ | Runbook "Releasing and rolling back" (`runbook.md:64-74`) | — |
| First real apply | ⛔ | PLAN Phase 10 unticked (owner's call) | R2-7 |

## 10. Mobile and store

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Privacy manifest, camera strings, arm64, no backup | ✅ | `ios/App/App/PrivacyInfo.xcprivacy`; `Info.plist`; `AndroidManifest.xml` | German `InfoPlist.strings` (S-2) |
| Account deletion in the app and on the web | ✅ | FLOWS §21; `/account/delete` public; R-13 | — |
| Review notes and demo accounts | ✅ | [`app-review.md`](app-review.md) | ⛔ accounts made in the prod pool at submission |
| Deep links in the release build | ⛔ | No longer a placeholder (`faebae7`). `var.apps` feeds `VITE_APPLE_TEAM_ID`/`VITE_ANDROID_SHA256` (`outputs.tf:55-56`). With no value, no app-link file is published. An all-zero or malformed fingerprint fails the release build (`vite.config.ts:76-81`). The team id and signing key are the owner's | Owner (store accounts); R2-21 (test) |
| A repeatable signed release build (API URL, signing, versioning) | ❌ | No workflow builds a shell | R2-10 |
| Tested on real devices (camera, push, edge-to-edge, 200% text) | ❌ | S-2, S-14, U-26, V5-28 need a device | R2-10, S-14 |
| Privacy label, Data safety, age rating, DSA trader, Play org account | ⛔ | S-3, S-5, S-6 | Owner |
| Push credentials (APNs, FCM) | ⛔ | Runbook step 5 | Owner |
| Staged rollout process | ❌ | — | S-25 |

## 11. Accessibility and localisation

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| DE and EN complete (FR too) | ✅ | `check:i18n` 1410/1410; emails EN/DE/FR in the second person (V8-9, `933ed14`); reasons by code in every language (V8-3/4/5) | — |
| Swiss languages (it for Ticino; fr-CH) | 🟡 | CH is `live` with `it` among its languages (`cappy_common/markets.json:109-116`); the app has no Italian | ⛔ R2-16 |
| WCAG 2.2 AA / BFSG | 🟡 | `check:a11y` (static, 24 px targets) and `check:contrast` (40 token pairs in both themes, in CI, `0a74b1c`); reduced motion as short fades (`theme.css:1043`). No axe run: UX-35 says it is not installed | UX-35/U-30, M-36; ⛔ R2-18 |
| 200% text on the phone | 🟡 | V8-6 (headings wrap and hyphenate, `theme.css:363`) and V8-14 fixed in `0a74b1c`, but not re-walked; V5-28 (dock labels) still open | V5-28, R2-22 |
| Locale formats (money, dates, zones) | ✅ | M-3, M-4, M-15 in part; FR typography enforced by `check:i18n` (`scripts/check-i18n.ts:15-21`) | — |

## 12. Support and trust and safety

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Notice-and-action, statements of reasons, audit | ✅ | G-2, S-13, H-7; a report with no target answers 404 (V8-19); the reporter is answered in the form's language (V8-12, `933ed14`) | — |
| Staff console: cases, refunds with limits, four eyes | ✅ | H-6, H-9; audit lines with names (V8-11, `0a74b1c`) | V4-15 (raw codes left); no chargeback screen (R2-24) |
| Fraud rules: velocity, held listings, card linkage | ✅ | G-9, T-20, S-17 | S-20 pHash (later) |
| A staffed support channel with SLAs | ⛔ | H-23 (owner); the contact form H-10 is open | H-10, H-23 |
| Damage protection | ⛔ | G-B1 | Owner |

## 13. Cost

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Cost drivers known | 🟡 | INFRA §6 "Main cost drivers" (three prices) | The monthly estimate that R2-4 asked for is still open |
| Budgets and anomaly alerts | ✅ | `backup.tf:112-160` (`faebae7`): a monthly budget per environment (prod $4000, `envs/prod/main.tf:128`), warning at 80% forecast and 100% actual, and Cost Anomaly Detection per service (≥ $50), all to the tickets topic | Validated only. The `env` cost-allocation tag must be activated once (runbook step 1) |
| Expensive options off by default and switchable | ✅ | Bot Control and threat protection are switches; one NAT in staging; log retention | — |
| Sustainability (right-sizing, ARM) | 🟡 | Serverless v2 scales to 1 ACU; Fargate architecture not checked (not verified) | After launch |

## 14. UI/UX (GOAL 18)

These are the criteria from §6 of [`research/2026-09-ui-ux-review.md`](research/2026-09-ui-ux-review.md). The score runs from 1 (far from best-in-class) to 5 (on par with Airbnb, Revolut or Linear), and the review put the app at 2.5 overall. **All of the UX build (`1daf0da`, `0a74b1c`) is read from code only.** Verification round 8 ran before it. A criterion is ✅ only with a browser or device walk, so none is ✅ yet.

Several UX tasks are done in code but still unticked in `TASKS.md`: UX-1, UX-2, UX-4, UX-5 (part), UX-6, UX-9, UX-13, UX-15, UX-23, UX-25, UX-30, UX-36 and U-40. See R2-20.

| # | Criterion | Score | Status | Evidence | Gap → task |
|---|---|---|---|---|---|
| 1 | Imagery truth: the owner's photo or a designed fallback, no unrelated stock, a gallery | 3 | 🟡 | `Gallery.tsx`: a swipe strip with n / N on the phone, a mosaic on the desktop, full screen with pinch, alt "Photo n of N, title" (`fe69a9a`). The grid never shows one photo twice (`Photo.tsx`). Designed category plates stand in for missing photos (`Cover.tsx`, `7051660`). Uploads come in 400/800/1600 renditions with a colour placeholder (`catalog/media.py`, `933ed14`) | Demo data is still Unsplash stock (`Photo.tsx:18`; `images.unsplash.com` in the non-prod CSP, `edge.tf:420`). Prod shows only uploads. Not walked (R2-22). UX-42 illustrations |
| 2 | Type legibility: no figure in the display serif; every size from the scale | 4 | 🟡 | Bodoni only at 28 px and up; prices, times and ratings in Archivo tabular (`edd0521`). `check:tokens` passes with text size 0 | One inline font size left (`ui.tsx:197`, the avatar) and it is allowlisted. Not walked |
| 3 | Token system: tiered DTCG tokens the only source; light and dark; Figma in sync | 3 | 🟡 | Semantic roles and scales as CSS variables and Tailwind utilities (`theme.css`, `theme.ts`). Dark mode under `data-theme=dark` is set before first paint (`public/theme-init.js`) and follows the system or a setting in Profile; `theme-color` follows (`theme.ts:28`). `check:tokens` blocks new literals, and the allowlist still holds hex 1 and rgba 7 | No DTCG `.tokens.json` or Style Dictionary (UX-5 rest). No Figma library (UX-43). The shell status bar does not follow the theme (UX-37) |
| 4 | Contrast and accessibility: axe clean everywhere in both themes and three languages at 390 and 1440 px; 44 pt targets; visible focus; reduced motion | 2 | 🟡 | `check:contrast` measures 40 token pairs in both themes (in CI, `0a74b1c`). Focus is blue ink, apart from the error red (UX-6, `edd0521`). Reduced motion keeps short fades (`theme.css:1043`) | No axe at all (UX-35). Targets are only checked at 24 px, and chips are `min-h-[38px]` (`ui.tsx:144`) → UX-34 |
| 5 | Price clarity: one `PriceSummary` everywhere, total before the button, one fee name, dated policy, no host money for the renter | 3 | 🟡 | `PriceSummary.tsx` (`fbbfe25`): price × hours, the fee named once, the total, the policy as a dated line, the amount on the button, never the owner's net for the renter | Used only on the listing (`Listing.tsx`, 2 places). The booking page and Earn keep their own price cards. One fee name in every language is open (UX-22) |
| 6 | Search completeness: What, When, Where; removable applied filters; a real map with price pins | 2 | 🟡 | When: a day and a start hour, in the URL (`3759014`), honoured by matching (`matching/domain/match.py`, `933ed14`) | No duration in search, and no composite step sheet (UX-15 rest). Applied-filter chips missing (UX-18). No map (UX-16) |
| 7 | Navigation model: an Inbox destination; detail screens own the phone's bottom edge; staff shell | 3 | 🟡 | Dock: Explore · Bookings · Inbox · Earn · You, with an unread badge from `/api/inbox` (`8ea479c`, `0a74b1c`). The dock steps aside on listing, booking, add/edit and staff detail (`AppShell.tsx`, `fbbfe25`) | Staff still share the consumer shell (UX-14) |
| 8 | Motion and feedback: tokens used; draggable sheets with detents; press states; optimistic UI; haptics | 3 | 🟡 | Motion tokens (`edd0521`). `Sheet` drags between medium and large detents and closes at 30% or on a flick; the grabber is a button; a dialog from 768 px (`ui.tsx:547-624`, `fbbfe25`). Press states. Push/pop on phones and a tab crossfade (`0a74b1c`) | No optimistic UI (UX-10). No haptics (UX-11). Not walked |
| 9 | Perceived performance: field p75 LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1; placeholders; no jumps | 2 | 🟡 | Colour placeholders, `srcset`, `width`/`height` (UX-3, `0a74b1c`). Skeletons after 300 ms that are shaped like the layout (`edd0521`) | No field or lab measurement (UX-45, S-23). The field numbers can only exist after launch, so a lab Lighthouse run on staging stands in for launch |
| 10 | Native feel: status bar, splash, keyboard and back on real iOS and Android 16; bounce and pull to refresh | 1 | ❌ | — | UX-37 (plugins not installed), UX-38, S-14, R2-10 |
| 11 | Consistency: one card, one sheet, one set of state styles; a design review signs off each key screen | 2 | 🟡 | One `Sheet` | `ListingCard` only in Browse (UX-17). No state styles (UX-7). No design sign-off against review §3.6 |
| 12 | Localisation layout: no truncation or overflow in DE/FR at 200%; FR punctuation; hyphenation; the original language labelled | 3 | 🟡 | FR spacing enforced by `check:i18n`. Headings hyphenate and wrap (V8-6); chips wrap (V8-14) | Not re-walked. Dock labels at 200% (V5-28). `hyphens` on body text and "Translated · Show original" (UX-33) |

For GO, criteria 1-8, 11 and 12 must be ✅ for the web, and 10 for the stores. Criterion 9 is met at launch by placeholders plus a lab run, and by field data within the first month.

## Status counts

| | ✅ | 🟡 | ❌ | ⛔ | Rows |
|---|---|---|---|---|---|
| §1-13 | 48 | 24 | 11 | 13 | 96 |
| §14 UI/UX | 0 | 11 | 1 | 0 | 12 |
| **All** | **48** | **35** | **12** | **13** | **108** |

Since `edaccc1` (43 / 23 / 19 / 11), §1-13 moved as follows:
- ❌ → ✅: detection, the breach procedure, locked backups, budgets and the CI gate.
- ❌ → 🟡: paging.
- ❌ → ⛔: the Impressum and deep links. Their code is done; the values are the owner's.
- Chargebacks stayed 🟡: they are handled, but the debt is never collected.
- One-step rollback stayed 🟡, with a new defect (R2-19).

## Blockers for GO (first launch, DE/AT/CH)

### What the team can still do (ranked)

1. **R2-2 (S)** Walk the Stripe card step in a browser with test keys, under the exact prod header set:
   - 3DS, a decline and the Identity modal;
   - the wallets in the Payment Element.

   Money has never moved through the real UI.
2. **R2-11 + R2-22 (M)** Verification round 9 on the web and at 390 px in EN/DE/FR. Include every UX-build screen: dark mode, sheets, gallery, inbox, When, the desktop buy box and 200%. Repeat until clean (GOAL 9). Close V8-20, V8-21 and V8-23.
3. **R2-19 (S)** Make rollback work across migrations. Rolling back must redeploy the old images without running the old code's `upgrade head`, and must not apply the old sha's Terraform. Rehearse it in staging.
4. **R2-20 (S)** Chargeback debt:
   - collect `owner_owes` from the owner's next payout, or remove the promise from runbook "A chargeback" until counsel confirms the clause;
   - tick the done UX and U-40 boxes.
5. **R2-9 web (S)** Reload once on `vite:preloadError`.
6. **UX P0 for the web (M-L)**:
   - UX-35: axe in CI over every route, in both themes and all three languages;
   - UX-34: 44 pt targets;
   - UX-17: one card;
   - UX-18: applied filters;
   - UX-22: one fee name;
   - PriceSummary on the booking page (criterion 5);
   - UX-14: a staff shell.
7. **P-15/P-16 (M)** English privacy policy at parity with the German one, from one source; counsel reviews.
8. **P-9 (S)** A publisher allow-list on the events topic. **R2-23 (S)** A source-account condition on the alarm and ticket topic policies.
9. **R2-21 (S)** A test for `releaseProblems`, so the Impressum guard cannot silently break. **R2-24 (S)** A console screen for chargebacks.
10. **Store part only:**
    - P-31 (S), P-5 + U-17 (M), S-2 (S), S-25 (S);
    - UX-37/UX-38 (S, the plugins need a network install);
    - R2-10 (M): signed builds and a device pass.

    A web-first launch could defer these; the owner decides.

Done since the last round: R2-1 (technical part), R2-3 (except collecting the debt), R2-4, R2-5, R2-6 (technical part), R2-8, R2-9 (infra part), P-13, P-14 and the Stripe CSP half of R2-2.

### What only the owner can do

| Item | Task | Size |
|---|---|---|
| Company details for the Impressum, the DSA contact points and invoices (the `LEGAL` variable; the release build now refuses without them) | V1-3 | S |
| Insurance partner or damage guarantee; decide whether vans launch | G-B1 (unblocks S-8, S-9, H-19) | L |
| Counsel: terms, cancellation, withdrawal by category, 18+, P2B mediators, VAT on the fee, the chargeback-deduction clause, a review of the breach procedure | G-B2, S-5, S-19, S-22, M-11, P-13 review | L |
| DPAs, RoPA, DPIA for ID checks, biometric consent wording | G-B3, P-17 | M |
| DAC7: BZSt registration, Stripe platform tax reporting and withholding | G-B4, G-10, S-31 | S |
| Real AWS account, domain `cappy.app`, GitHub environments, first apply, SES production access, the env cost-allocation tag. Then the staging acceptance run: e2e with Stripe test mode, staff TOTP, restore rehearsal, game day | Phase 10, R2-7, R2-14 | L |
| A pager account (PAGER_ENDPOINT) and an on-call rota; staffed support with SLAs | R2-6, H-23 | M |
| Stripe live activation: platform verification, Connect Express, Identity, Radar, webhook endpoint, SAQ A attestation, negative-balance policy | R2-15 | M |
| Store accounts: Apple team id and Android signing key (for deep links), Apple DSA trader status, Play organisation account (D-U-N-S), privacy label and Data safety, age rating, APNs and FCM keys | S-3, S-5, S-6, runbook step 5 | M |
| Rotate the pasted tokens; purge the decks from history; make the repository private | R2-13 | S |
| Switzerland: MWST position, FADP representative, Italian (or launch DE+AT first) | M-43, R2-16 | S (decision) |
| BFSG micro-enterprise status (decides whether a full WCAG audit blocks launch) | R2-18 | S (decision) |

## Not needed for the first launch

| What | Why it can wait |
|---|---|
| North America cell (M-1, M-21..M-31), CCPA/CPRA (P-29, M-28), PIPEDA/Law 25 (P-21, M-29), French for Québec (M-17) | No US or CA users at launch. `markets.json` has them `planned` |
| UK (M-42), the other EU markets, per-market legal pages (M-19), miles (M-18) | Not live in `markets.json` |
| Places as geo points and geocoding (M-5, M-7, M-8, H-34) | Districts work for DACH |
| A second-region or second-account backup copy, the status page (H-22), dashboards (M-45), the INFRA §6 cost estimate | Needed within the first weeks, not on day one |
| External penetration test (R2-17) | Before real volume or card-network scrutiny |
| Breakpoint on AWS (L-5), mixed load (L-4), RDS Proxy (T-24), Global Database (F26) | Launch traffic in one market is far below the local results |
| DSA Sections 3-4, KYBC, transparency reports | Micro and small enterprise exemption (Art. 19) |
| UX P1/P2 beyond the blockers above: UX-10 optimistic UI, UX-11 haptics, UX-16 map, UX-19 AddListing steps, UX-21 SlotPicker, UX-26 Earn Today, UX-27 Profile, UX-28/29/31/32/39..44, UX-45 field vitals | Polish and growth, not safety or law |
| Growth features: H-13, H-14, H-25, H-31, S-27, S-28, S-20, U-14, S-23/S-24, F-5..F-9 | Quality and growth, not safety or law |

## How this is re-scored each round

- After each build and verification round, a reviewer who did not write the code re-reads this file against the code and the latest `TASKS.md`.
- Every row keeps its evidence as `file:line`, a test name, command output, a commit or a task id. A row changes status only when that evidence changes.
- A ⛔ row moves only when the owner records the decision, with a date, in `TASKS.md`.
- Rows marked "not verified" are re-run first. A UI/UX row is ✅ only after a browser or device walk.
- The verdict turns GO only when every "Blockers for GO" item is ✅ or waived in writing by the owner. The status counts are recomputed by counting the icons in the tables.
