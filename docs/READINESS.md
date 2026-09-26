# Production readiness scoreboard

**Ready for production** means that real people in the first market (DE/AT/CH) can sign up, list, book, pay and be paid out, on the web and in both stores. It must be lawful to run, safe for their data and money, and operable by an on-call human who is paged, has a runbook, and can roll back. Each criterion below must be ✅ with evidence, or waived in writing by the owner.

**Verdict: NO-GO.** The code is well past a first launch in most areas (581 tests green, every web check green, the server enforces members-only). But the deployed web build would publish an Impressum without the operator's name. The live card flow has never run in a browser under the production CSP. There is no paging, no breach procedure and no rehearsed restore. And the owner's legal, insurance, store and Stripe steps are all still open.

Reviewed 2026-09-26 at `25e79d3` (branch `prod-readiness`), read-only. Status: ✅ met · 🟡 partial · ❌ not met · ⛔ blocked on the owner. Task ids refer to [`TASKS.md`](TASKS.md). `R2-n` tasks are new in this review.

What was run this round:
- `make test`: `581 passed, 14 skipped` (the 14 are the Postgres and stripe-mock tests, which run in CI with services, `ci.yml:16-46`).
- Web: `tsc --noEmit` clean. `check:i18n` "1365 German and 1365 French entries, same keys". `check:flags`, `check:a11y`, `check:attempt` and `check:money` all pass. `check:size`: entry "149.6 kB gzipped (budget 170 kB)", measured on the existing `web/dist`, which was not rebuilt.
- Read-only curl against `localhost:8000/api`:
  - `/categories` and `/app-config` answer 200.
  - `/search?q=saw`, `/listings/l9`, `/bookings`, `/me`, `/me/export` and `/admin/reports` answer 401 signed out.
  - `/internal/busy` answers 404.
  - Headers seen: `x-request-id`, HSTS with preload, `nosniff`, `DENY`, `strict-origin-when-cross-origin`.
- **Not run:** `make e2e`, `make test-pg` and the load scripts, because they write to the stack the verifier is using. Anything that needs real AWS, Stripe live or a device was **not verified**.

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

## 1. Product completeness

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Sign-up with email verification, password reset, sign-in with a TOTP step | ✅ | PLAN Phase 9; `web/src/data/cognito.ts`; P-4 | TOTP not verifiable on cognito-local → R2-7 |
| Listing with photos, search, booking with authorise → capture → payout → refund, reviews, saved | ✅ | PLAN Phase 11 e2e journey; GOAL "Complete" ticked; V7 scripts 3-12 pass | `make e2e` not re-run this round (not verified) |
| Members only, enforced by the server | ✅ | curl: product routes 401 signed out; public only `/categories`, `/app-config`; ADR/GOAL 13 | — |
| Welcome for first-timers | ✅ | U-2, U-3 | — |
| Messaging, blocks, reports, disputes, late return, extension, no-show | ✅ | G-3, G-4, S-11, S-12, S-21 (backend and web built); V7 scripts 13, 25-27 | — |
| Owner damage claim and collecting on it | ⛔ | S-8, S-9 open | Blocked on insurance G-B1 |
| Independent verification: a full pass that finds nothing (GOAL 9) | ❌ | V7 found 30 items (all ticked). Scripts 7, 9, 13, 23, 27 failed; 1, 15, 20, 22 blocked. No round after the fixes | R2-11 |
| Help centre and a support contact | 🟡 | `Help.tsx`; support address from `VITE_LEGAL_EMAIL` (`Help.tsx:214`), which no deploy sets | H-10, R2-1 |

## 2. Correctness and data integrity

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| No double booking under concurrency | ✅ | `test_simultaneous_bookings_of_one_window_yield_exactly_one` (`booking/tests/test_booking_postgres.py:37`, runs in CI with Postgres); resilience F12 (50 buyers × 3 rounds × 6) | — |
| No lost or phantom events (outbox, idempotent consumers) | ✅ | ADR 0003; resilience F27-F28; `outbox-set-aside` alarm | — |
| Idempotent webhooks | ✅ | `test_webhook_authorises_once_and_rejects_forgeries` (`payments/tests/test_payments_api.py:238`), `test_a_lost_webhook_is_made_good_by_reconciliation` (`:439`) | — |
| Migrations match the models (drift) | ✅ | `test_migrations_build_exactly_the_models` (`test_booking_postgres.py:26`); DATA §7 | — |
| No startup path deletes data; demo only by CLI | ✅ | ADR 0010; `test_prod_refuses_unsafe_settings` (`cappy_common/tests/test_foundations.py:67`) | — |
| Money shown equals money moved (refunds, no-shows) | ✅ | `check:money` pass; V7-2, V7-3 fixed | — |
| Chargeback lifecycle | 🟡 | `charge.dispute.created` holds the payout (`payments/routes.py:485-492`). `charge.dispute.closed` is not handled and there is no evidence submission (FEATURES.md:1302). FEATURES points to a runbook procedure that does not exist (`grep -i chargeback docs/runbook.md` finds nothing) | R2-3 |
| Housekeeping tables pruned | ✅ | `prune_guards` (`cappy_common/guard.py:56-64`), `revoked_sessions` 25 h, `rate_hits` 2 d. PLAN "Resume here" still lists this as to do | R2-12 (stale doc) |

## 3. Security (OWASP ASVS L2 lens)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Authentication: JWKS verification, no trusted identity header, 15-min access tokens, revocation | ✅ | PLAN DoD "Safe"; P-24; V7 script 21 (the old token got 401 within 8 s) | — |
| Staff MFA and four eyes | 🟡 | P-3, P-4, H-6; prod refuses `ADMIN_MFA_REQUIRED` off (runbook "Moderation") | Never exercised against real Cognito → R2-7 |
| Access control: `/internal` unreachable, per-caller internal tokens | ✅ | curl `/api/internal/busy` 404; P-10; `test_prod_needs_per_caller_internal_tokens` | — |
| Input limits, rate limits, load shedding | ✅ | P-1, P-12, P-22, T-01; WAF rate rules `edge.tf` | Per-user limits beyond these: runbook "Known limits" (accepted) |
| Security headers and CSP | 🟡 | Headers seen by curl; CSP `edge.tf:405-424`. `style-src 'unsafe-inline'` remains (P-26). Stripe's documented `https://*.js.stripe.com` is missing from `script-src`/`frame-src` (`edge.tf:409`, `:416`) | P-26, R2-2 |
| Encryption in transit and at rest | ✅ | INFRA §4 "Encryption"; `data.tf:67`; P-11 Service Connect TLS, `verify-full` | Validated only, never applied (GOAL 12) |
| Secrets out of the repository | 🟡 | `.env` ignored (`git check-ignore`); a scan of tracked files for `sk_`, `whsec_`, `ghp_` and `AKIA` found only false positives. But the LocalStack and GitHub tokens pasted in chat are not rotated, and `Capacity_Exchange_*.pptx` are still in history (`0ba8d2c`) | R2-13 |
| Supply chain | 🟡 | `pip-audit --strict`, `npm audit --omit=dev` (`ci.yml:36-40`, `:60`); Dependabot; actions pinned by tag, not SHA | P-32 note (SHA pins) |
| Detection: CloudTrail, GuardDuty, Security Hub | ❌ | `grep -r cloudtrail\|guardduty infra/platform` finds nothing | P-14 |
| Event forgery between services | 🟡 | Notifications' `sns:Publish` is scoped to `endpoint/*` (`ecs.tf:251`); publishers get only the topic (`ecs.tf:275`). There is no topic policy listing publishers. TASKS still shows P-9 as open | P-9 (partly done; re-scope) |
| WAF sampled requests keep no tokens | ✅ | Every `sampled_requests_enabled = false` (`edge.tf:200,254,329,337`, `identity.tf:155,174,181`). TASKS still shows P-20 as open | R2-12 (tick P-20) |
| Store shells hardened | ❌ | `external-path` still in `android/.../xml/file_paths.xml:3`; `minifyEnabled false` (`android/app/build.gradle:23`); `<access origin="*" />` (`ios/App/App/config.xml:3`, Android `config.xml:3`); refresh token in Preferences (`web/src/native.ts:15-20`); no CSP in the shells | P-31, P-5, U-17 |
| Independent penetration test before real money | ❌ | Three internal reviews (PLAN Phase 12) and the security review; no external test | R2-17 |

## 4. Privacy and legal

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Impressum and DSA Art. 11/12 contact points **in the deployed build** | ❌ | `Legal.tsx:13-20` reads `VITE_LEGAL_*`. The deploy's `web_config` gives only `VITE_COGNITO_REGION` and `VITE_COGNITO_CLIENT_ID` (`infra/platform/outputs.tf:43-48`), so prod shows "Operator details to be completed before launch" (`Legal.tsx:66-70`) | R2-1; V1-3 details ⛔ |
| Data export and deletion (Art. 15/17/20), register tested | ✅ | `test_every_table_holding_a_person_is_in_the_register` (`cappy_common/tests/test_privacy.py:51`); FLOWS §21 | D-27 (a renter's name in the owner's inbox) |
| Retention schedule | 🟡 | [`retention.md`](retention.md); counsel confirms the periods (G-B2/G-B3) | ⛔ G-B3 |
| Privacy policy complete in every language shown in DACH | 🟡 | The German policy is complete. The English one omits messages, photos, reports, ID checks and push (P-15), and the two drift apart (P-16) | P-15, P-16 |
| RoPA, DPAs, DPIA for ID checks | ⛔ | G-B3, P-17 | Owner with counsel |
| Breach procedure (GDPR 72 h) and incident register | ❌ | No section in [`runbook.md`](runbook.md) | P-13 |
| Consumer law at checkout (PAngV, § 312j, withdrawal button, trader label, § 5b UWG) | 🟡 | G-6, S-4. Withdrawal is not varied by category (vans are exempt) | ⛔ S-19 (counsel) |
| Terms, age 18+, P2B | ⛔ | G-B2, S-5 (terms text), S-22 | Counsel |
| DAC7 | ⛔ | G-10 (tags done); BZSt registration G-B4; Stripe tax reporting S-31 | Owner |
| Cookie/TDDDG consent not needed | ✅ | Server-side analytics only; fonts self-hosted (P-26) | Keep crash reports identifier-free |

## 5. Payments and money

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Card data never touches Cappy (SAQ A shape) | ✅ | Payment Element in an iframe (`PayStep.tsx`); ADR 0005 | Annual SAQ A attestation → R2-15 |
| SAQ A eligibility: the site is not open to script attacks | 🟡 | Strict `script-src` (`edge.tf:409`) | Not verified against a deployed page; R2-2 |
| Card step in a real browser with Stripe test keys, 3DS, under the prod CSP | ❌ | PLAN Phase 9 box unticked. V7 script 6 "fake provider only". e2e confirms by API (72693fb), not in the browser | R2-2 |
| Webhooks subscribed to what is handled | ✅ | Runbook step 4 lists the 4 kinds that `payments/routes.py:469-492` handles, plus Identity | Add `charge.dispute.closed` with R2-3 |
| Reconciliation, retries, payout kill switch | ✅ | R-1, T-16, R-10; resilience F16-F21 | — |
| Fee invoices, gapless numbers | 🟡 | G-11; 19% German VAT for everyone (`payments/invoices.py:44`) | M-12 (tech), ⛔ M-11/G-B2 (AT/CH owners, reverse charge) |
| Stripe live platform activated (Connect Express, Identity, Radar, negative-balance liability) | ⛔ | Runbook "First deploy" step 4 | R2-15 |

## 6. Reliability and resilience

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Failure catalogue with a decision for each scenario | ✅ | [`resilience.md`](resilience.md) F1-F36 | — |
| Multi-AZ, deletion protection, PITR 14 days | ✅ | `data.tf:67-72` | — |
| Backups out of reach of a compromised deploy role | ❌ | Only in-cluster PITR. The deploy role is `AdministratorAccess` (INFRA §4 "GitHub OIDC roles"). There is no AWS Backup vault or cross-account copy | R2-5 |
| Restore rehearsed; RTO known | ❌ | "Last rehearsal: never. Do one before launch." (`runbook.md:208`) | R2-7 (⛔ needs AWS) |
| Game day | ❌ | Runbook table; none run | R2-7 |
| Region loss | 🟡 | Decided: one region, RTO hours (T-26) | Accepted for launch |

## 7. Performance and capacity

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| No query whose cost grows with the database | ✅ | [`bench.md`](bench.md): 100k listings, candidates at 10-21 ms | — |
| Load, spike, soak (local) | ✅ | L-1 (0 failures), L-2 (p99 ≈ 220 ms at 300/s), L-3 (20 min, flat) | — |
| Mixed open-model journeys | 🟡 | `make load-mixed` exists (Makefile:84); no result recorded | L-4 |
| Sized on real AWS (breakpoint, ACUs, task maxima) | ⛔ | Never applied (GOAL 12) | L-5 |
| Connection budget | ✅ | Terraform `check` (`data.tf:183-191`) | — |
| Web budget | ✅ | `check:size` 149.6 kB gz of 170 kB | Web vitals S-23 (after launch) |
| App cold start | ❌ | Not measured | S-24 |

## 8. Operability (observability, alerts, runbooks, on-call)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Structured logs with a request id, traces | ✅ | `x-request-id` in curl; T-33 ADOT → X-Ray | — |
| SLOs and burn-rate alarms per journey | ✅ | [`slo.md`](slo.md); `observability.tf:205-347` | — |
| Synthetic canary | ✅ | `synthetics.tf`; T-34 | — |
| Alarms reach a human who is paged | ❌ | Email only (`observability.tf:8-12`). No rota, no pager, no severity scale, no postmortem template, although the budget policy asks for postmortems (`slo.md`) | R2-6 |
| Runbooks: alarms, disputes, moderation, kill switches, restore, rollback | 🟡 | [`runbook.md`](runbook.md) | No chargeback (R2-3), no breach (P-13), no store release (S-25) |
| Dashboards | 🟡 | None in Terraform (INFRA §5 "Dashboards"); Container Insights, X-Ray | M-45 (per cell, later) |
| Public status page | ❌ | — | H-22 |

## 9. Delivery (CI/CD, migrations, rollback)

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| CI lints, tests, audits, builds images, validates Terraform, runs e2e | ✅ | `ci.yml` jobs backend, web, images, infra, e2e | e2e skipped without `LOCALSTACK_AUTH_TOKEN` (`ci.yml:94-99`) |
| CD with OIDC, migrations before the roll, automatic rollback | ✅ | `deploy.yml:95-139`; `ecs.tf:375-383` circuit breaker plus alarms | — |
| Prod deploy only for a SHA that CI passed | ❌ | `deploy.yml` is triggered by push or dispatch and has no gate on `ci` | R2-8 |
| One-step rollback to a named release | 🟡 | INFRA "Manual rollback" says to run deploy for an older commit. But dispatch always builds `github.sha` of `main` (`deploy.yml:26`, `:32`), so a rollback needs a revert commit or a local admin apply | R2-8 |
| Web deploy doesn't break open sessions | 🟡 | Routes are lazy (`App.tsx:25-35`). `aws s3 sync --delete` removes the previous chunks (`deploy.yml:207`). No `vite:preloadError` handler. Workbox precache softens this (not verified) | R2-9 |
| Expand-then-contract migrations | ✅ | Runbook "A deploy failed"; INFRA §5 "Migrations" | — |
| First real apply | ⛔ | PLAN Phase 10 unticked (owner's call) | R2-7 |

## 10. Mobile and store

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Privacy manifest, camera strings, arm64, no backup | ✅ | `ios/App/App/PrivacyInfo.xcprivacy`; `Info.plist:46,56`; `AndroidManifest.xml:5` | German `InfoPlist.strings` (S-2) |
| Account deletion in the app and on the web | ✅ | FLOWS §21; `/account/delete` public; R-13 | — |
| Review notes and demo accounts | ✅ | [`app-review.md`](app-review.md) | ⛔ accounts made in the prod pool at submission |
| Deep links in the release build | ❌ | The built `assetlinks.json` has an all-zero fingerprint (`vite.config.ts:33`). Deploy sets no `VITE_ANDROID_SHA256` or `VITE_APPLE_TEAM_ID` | R2-1 |
| A repeatable signed release build (API URL, signing, versioning) | ❌ | No workflow builds a shell; `capacitor.config.ts` says only to set `VITE_API_URL` | R2-10 |
| Tested on real devices (camera, push, edge-to-edge, 200% text) | ❌ | S-2, S-14, U-26, V4-12/V5-28 need a device | R2-10, S-14 |
| Privacy label, Data safety, age rating, DSA trader, Play org account | ⛔ | S-3, S-5, S-6 | Owner |
| Push credentials (APNs, FCM) | ⛔ | Runbook step 5 | Owner |
| Staged rollout process | ❌ | — | S-25 |

## 11. Accessibility and localisation

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| DE and EN complete (FR too) | ✅ | `check:i18n` 1365/1365; emails EN/DE/FR (G-7) | — |
| Swiss languages (it for Ticino; fr-CH) | 🟡 | CH is `live` with `de, fr, it, en` in `markets.json`; the app has no Italian | R2-16 |
| WCAG 2.2 AA / BFSG | 🟡 | `check:a11y` is a static scan; accessibility statement page exists; no axe run | U-30, M-36 (BFSG micro-enterprise exemption: owner confirms headcount, R2-18) |
| 200% text on the phone | 🟡 | V7-8 and V7-27 fixed; V4-12/V5-28 still open | V5-28 |
| Locale formats (money, dates, zones) | ✅ | M-3, M-4, M-15 in part; FR typography (V7-9) | — |

## 12. Support and trust and safety

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Notice-and-action, statements of reasons, audit | ✅ | G-2, S-13, H-7; runbook "Moderation" | — |
| Staff console: cases, refunds with limits, four eyes | ✅ | H-6, H-9; V7 scripts 19, 24 pass | V4-15 (raw codes left in the console) |
| Fraud rules: velocity, held listings, card linkage | ✅ | G-9, T-20, S-17 | S-20 pHash (later) |
| A staffed support channel with SLAs | ⛔ | H-23 (owner); the contact form H-10 is open | H-10, H-23 |
| Damage protection | ⛔ | G-B1 | Owner |

## 13. Cost

| Criterion | Status | Evidence | Gap → task |
|---|---|---|---|
| Cost drivers known | 🟡 | INFRA §6 "Main cost drivers" (only three prices stated) | Monthly estimate with R2-4 |
| Budgets and anomaly alerts | ❌ | No `aws_budgets_budget` or Cost Anomaly Detection in `infra/` | R2-4 |
| Expensive options off by default and switchable | ✅ | Bot Control and threat protection are switches (`envs/prod/main.tf:84`); one NAT in staging; log retention (`ecs.tf:152`) | — |
| Sustainability (right-sizing, ARM) | 🟡 | Serverless v2 scales to 1 ACU; Fargate architecture not checked (not verified) | After launch |

## Blockers for GO (first launch, DE/AT/CH)

### Technical: the team can do these (ranked)

1. **R2-1 (S)** Put the operator's details, support address and deep-link identifiers into the deployed web build, and fail a prod build that lacks them. Without this the Impressum and DSA contact points are empty in prod, which is an Abmahnung risk from day one.
2. **R2-2 (S)** Walk the Stripe card step and 3DS (and the Identity modal) in a browser with test keys under the exact prod CSP. Add `https://*.js.stripe.com`. Money has never moved through the real UI.
3. **R2-11 (M)** Verification round 8, on web and at 390 px, until a pass finds nothing (GOAL 9).
4. **P-13 (S)** Write the breach procedure and incident register (GDPR 72 h); counsel reviews it.
5. **R2-6 (S)** Page a human, not a mailbox: a pager integration, severities, and a postmortem template. The rota itself is the owner's.
6. **R2-3 (M)** Close the chargeback loop: `charge.dispute.closed`, evidence submission, and a runbook for recovery after payout.
7. **P-14 (S)** CloudTrail, GuardDuty and Security Hub in Terraform.
8. **R2-8 (S)** Deploy prod only for a CI-green SHA; add a rollback-to-SHA input.
9. **P-15/P-16 (M)** English privacy policy at parity with the German one, both from one source; counsel reviews.
10. **R2-9 (S)** Keep the previous web release's chunks, and reload on `vite:preloadError`.
11. **Store part only:**
    - P-31 (S), P-5 + U-17 (M), S-2 (S);
    - R2-10 (M): signed builds and a device pass.

    A web-first launch could defer these; the owner decides.

### Owner and business: nobody else can do these

| Item | Task | Size |
|---|---|---|
| Company details for the Impressum and invoices (`LEGAL`, `VITE_LEGAL_*`) | V1-3, R2-1 | S |
| Insurance partner or damage guarantee; decide whether vans launch | G-B1 (unblocks S-8, S-9, H-19) | L |
| Counsel: terms, cancellation, withdrawal by category, 18+, P2B mediators, VAT on the fee (DE, AT, CH owners) | G-B2, S-5, S-19, S-22, M-11 | L |
| DPAs, RoPA, DPIA for ID checks, biometric consent wording | G-B3, P-17 | M |
| DAC7: BZSt registration, Stripe platform tax reporting and withholding | G-B4, G-10, S-31 | S |
| Real AWS account, domain `cappy.app` (`envs/prod/main.tf:97`), GitHub environments, first apply, SES production access; then the staging acceptance run | Phase 10, R2-7, R2-14 | L |
| Stripe live activation: platform verification, Connect Express, Identity, Radar, webhook endpoint, SAQ A attestation, negative-balance policy | R2-15 | M |
| Store accounts: Apple DSA trader status, Play organisation account (D-U-N-S), privacy label and Data safety, age rating, APNs and FCM keys, signing keys | S-3, S-5, S-6, runbook step 5 | M |
| Staffed support with SLAs and an on-call rota | H-23, R2-6 | M |
| Rotate the pasted tokens; purge the decks from history; make the repository private | R2-13 | S |
| Switzerland: Swiss VAT (MWST) position, FADP representative need, Italian (or launch DE+AT first) | M-43, R2-16 | S (decision) |

## Not needed for the first launch

| What | Why it can wait |
|---|---|
| North America cell (M-1, M-21..M-31, M-24..M-27), CCPA/CPRA (P-29, M-28), PIPEDA/Law 25 (P-21, M-29), French for Québec (M-17) | No US or CA users at launch. `markets.json` has them `planned` |
| UK (M-42), the other EU markets, per-market legal pages (M-19), miles (M-18) | Not live in `markets.json` |
| Places as geo points and geocoding (M-5, M-7, M-8, H-34) | Districts work for DACH (V7-29 added the main German cities) |
| Backups outside the account (R2-5), budgets (R2-4), status page (H-22), dashboards (M-45) | Needed within the first weeks, but not what stops day one. Do R2-4 with the first apply: it is an hour |
| External penetration test (R2-17) | Before real volume or card-network scrutiny; the internal reviews cover L2 basics |
| Breakpoint on AWS (L-5), mixed load (L-4), RDS Proxy (T-24), Global Database (F26) | Launch traffic in one market is far below the local results |
| DSA Sections 3-4, KYBC, transparency reports | Micro and small enterprise exemption (Art. 19) |
| Growth features: H-13 iCal, H-14 saved searches, H-25 pricing hints, H-31 host tier, S-27 review prompt, S-28 collusion signals, S-20 pHash, U-14 email OTP, U-40 responsive images, S-23/S-24 vitals, F-5..F-9 seams | Quality and growth, not safety or law |
| Demo photo quality (V1-34) | Demo data only |

## How this is re-scored each round

- After each build and verification round, a reviewer who did not write the code re-reads this file against the code and the latest `TASKS.md`.
- Every row keeps its evidence as `file:line`, a test name, command output or a task id. A row changes status only when that evidence changes.
- A ⛔ row moves only when the owner records the decision, with a date, in `TASKS.md`.
- Rows marked "not verified" are re-run first.
- The verdict turns GO only when every "Blockers for GO" item is ✅ or waived in writing by the owner. The status counts in the final report are recomputed by counting the icons in the tables.
