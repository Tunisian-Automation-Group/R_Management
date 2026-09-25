# Security review, September 2026

An independent review of the `prod-readiness` branch at `d2baff3`, done on 2026-09-26. It covers:

- the Python services under `backend/`;
- the React and Capacitor app under `web/`;
- the Terraform under `infra/`;
- the GitHub workflows.

The review was measured against OWASP ASVS 5.0 Level 2, the OWASP API Security Top 10 (2023) and MASVS 2 (for the Capacitor shells). It also covers the privacy and security laws of the markets in GOAL 16: GDPR and UK GDPR, CCPA/CPRA and the other US state laws, and PIPEDA with Québec Law 25 (see "Privacy and security law in each market").

**Method.** I read the code first. I then sent requests to the local stack at `http://localhost:8000/api`, using throwaway Cognito users that I created through cognito-local, the same way `local/load.py` does. I left the demo accounts alone. The probe script lives outside the repo, in the session scratchpad. After the run I deleted the throwaway users, their profiles, the probe listings, and the one booking (which I cancelled first).

Two probe reports are still in the moderation queue, because there is no API to delete them. Both are `targetType=listing` with `targetId=ls_nothing_0e2d93`, and staff can dismiss them. This review changed no other file.

**Already covered elsewhere, so not repeated here:**

| Item | Tracked as |
|---|---|
| Refresh token in web storage (accepted risk) | ADR 0002, V1-28 |
| Refresh token in Keychain/Keystore | U-17 |
| Stripe.js loading before sign-in | V3-1 |
| Tabs staying signed in after sign-out | V3-7 |
| Sign-out-everywhere error not shown to the user | V3-23 |
| Per-user limits via Redis | F2 |
| Cognito threat protection | T-06 / F6 (M4 below adds what that task misses) |
| 3DS return into the shells | U-7 |

Findings are marked **(unverified)** where I could not prove them.

## What held up

I tested each of these and it behaved correctly.

**JWT validation** (`backend/libs/cappy_common/cappy_common/auth.py:114-145`):

- Each of these gets a 401: `alg=none`, `alg=HS256` with the original signature, a tampered `sub`, an id token (with the message "send an access token, not an id token"), and a refresh token sent as the bearer.
- The issuer, `token_use`, `client_id`, `exp`, `iat` and `sub` claims are all required.
- JWKS refreshes are rate-limited, so random `kid` values cannot flood Cognito.
- A deployed environment will not start without an https issuer and a list of client ids (`settings.py:126-130`).

**Object-level authorization (BOLA).** A third user (C) got a 404 on every one of these for another person's booking:

- `GET /bookings/{id}`, `/messages`, `/evidence`, `/cancellation` and `/payment`;
- `GET /payments/bookings/{id}`;
- `POST .../messages`, `/cancel` and `/accept`.

A non-owner also got a 404 on `PUT`, `pause`, `DELETE` and `POST slots` for someone else's listing. The requester trying to accept their own request got a 403. Invoices, notifications, devices, saved listings and blocks are all filtered by `p.sub`.

**Function-level authorization.** A non-staff user gets a 403 on:

- `/admin/reports`, `/admin/audit`, `/admin/listings/held` and `/admin/dsa-stats`;
- `/admin/bookings/{id}/resolve`.

**Internal routes through the gateway.** All of these return 404 at the gateway allow-list (`gateway/routing.py:34-41`):

- `/api/internal/...`
- `..%2F`, `%2e%2e`, `%252e%252e/%2569nternal`
- `/INTERNAL`, `..;`
- `/me/../internal`

The services' `require_internal` check is a second lock. The token must be at least 32 characters when deployed (`settings.py:118`), and the gateway is never given it.

**Mass assignment.**

- `PUT /me` with `verified`, `jobsDone`, `ratingSum` or `id` in the body: all ignored.
- `POST /listings` with `id: "ls_evil"` and `ownerId: "o1"`: the server minted its own id and used the caller's `sub` as the owner.
- The hand-over `instructions` and `address` never appeared in another user's `GET /listings/{id}`.

**Idempotency.** Keys are scoped per user. The same key and body sent by a second user produced a new report, not a replay (`idempotency.py:29-39`, and the booking's own key at `booking/repository.py:110-112`).

**Injection.** Search uses bound parameters, with `%`, `_` and `\` escaped in the LIKE pattern (`catalog/repository.py:627-641`). No raw `text()` is built from input anywhere. Invoice HTML escapes every field (`payments/invoices.py:150-178`).

**Uploads.**

- An SVG with a script, and a PNG-magic HTML polyglot: both get a 422.
- Pillow decodes the file and checks the pixel count before loading it, strips EXIF, re-encodes to WebP, and names the file after its content hash (`catalog/media.py:46-74`).
- The body is capped at 12 MB, at most two decodes run at once, and each person gets 100 uploads a day.

**Webhooks.** `stripe.Webhook.construct_event` checks the signature (`payments/provider.py:192-194`). Each event id is processed once. A deployed environment refuses the fake provider (`payments/settings.py:31-38`).

**CORS.** A preflight from `https://evil.example` gets a 405, and a GET gets no `Access-Control-Allow-Origin`. When deployed, the origin list has to be explicit https or `capacitor://`. `allow_credentials` is not set.

**SSRF.** Nothing fetches a URL that a user supplies. Photo URLs must be our own `/media/<hash>.webp`.

**Secrets.**

- No keys in the tracked files or in git history. I searched for `sk_`, `whsec_`, `AKIA` and private keys.
- The `.env` files are untracked.
- `web/dist` contains no secrets.
- The demo accounts are injected only via `VITE_DEMO_ACCOUNTS`, and the deploy workflow never sets it.

**Security headers and CORP.** They are on every response, errors included (`app.py:113-139`).

**Infrastructure basics.**

- The S3 buckets block public access and are read only through origin access control.
- The ALB accepts connections only from CloudFront's prefix list, and only with the origin-secret header.
- Aurora storage is encrypted.
- The state bucket uses KMS encryption with versioning.
- The GitHub OIDC trust is pinned to the environment, `main`, and `deploy.yml`.

**Capacitor shells.** There is no `server.url`, no `allowNavigation` and no cleartext. Deep links and push taps are reduced to a path inside the app (`web/src/native.ts:29-41`). On Android, `allowBackup=false` and the data extraction rules exclude everything.

## Findings

### High

#### H-1 [backend] Any member can break search for a whole category with one listing (stored DoS)

Listing numeric fields are not range-checked. `_validate_listing` checks only `ratePerHour > 0` (`backend/services/catalog/catalog/routes.py:237`). The models accept any float or int for these fields (`backend/libs/cappy_common/cappy_common/models.py:174-195`):

- `unitsPerHour` and `setupHours`;
- `minHours` and `maxHours`;
- `extraFee` and `setupFee`.

Pricing then divides by `listing.units_per_hour` (`backend/services/matching/matching/domain/pricing.py:25`).

**Evidence (local).** A throwaway account created a batch listing in Kreuzberg with `"unitsPerHour": 0, "setupFee": -5000`, category `additive`, at 10 €/h. The listing went live at once: it was below the review threshold, so it was not held.

- Another user's `POST /api/matches` for 3D printing in Kreuzberg went from 200 to **500**.
- It returned to 200 only after the listing was deleted.

Anyone searching that category within range gets a 500 for as long as the listing stays up. That breaks the core flow for everyone nearby (API4 and API8).

**Fix.**

- Add pydantic constraints to the models:
  - `units_per_hour: float = Field(gt=0, le=1e6)`;
  - `setup_hours`, `min_hours` and `max_hours` of at least 0, with `min_hours <= max_hours`;
  - `extra_fee` and `setup_fee` of at least 0, `rate_per_hour` of at least 1, and upper bounds on all of them;
  - `allow_inf_nan=False` in `CamelModel`.
- Make `find_matches` skip, and log, any candidate whose quote raises, rather than failing the whole answer.
- Add a test that stores a listing with `unitsPerHour=0` and checks that `/matches` still answers 200.

#### H-2 [infra] The deploy job runs third-party npm install scripts while holding AdministratorAccess

The deploy roles attach `arn:aws:iam::aws:policy/AdministratorAccess` (`infra/bootstrap/main.tf:65,69`). `deploy.yml` assumes the role at line 38, and later, in the same job, runs `npm ci && npm run build` (`.github/workflows/deploy.yml:116`). `npm ci` executes the lifecycle scripts of every dependency, with the AWS credentials in the environment.

A compromised transitive npm package would therefore get admin rights in the prod account. That means Cognito, Aurora snapshots, Secrets Manager (Stripe keys) and the ability to disable CloudTrail. The npm worm campaigns of 2025 targeted exactly this pattern. (The exploit itself is unverified; the configuration is as described.)

**Fix.**

- Build the web app in a separate job with no `id-token` permission. Use `npm ci --ignore-scripts` where the build allows it. Pass `dist/` on as an artifact.
- Scope the deploy role to what Terraform and the S3 sync need, or use a second role that can only `s3:PutObject`/`DeleteObject` on the web bucket and `cloudfront:CreateInvalidation`.
- Keep AdministratorAccess, if it is needed at all, for the Terraform step only.

#### H-3 [backend+web+infra] Staff accounts have no enforced MFA, and the app cannot complete an MFA sign-in

- Staff are just members of the Cognito group `admin` in the same user pool as everyone else (`infra/platform/identity.tf:92-96`).
- The pool's MFA is `OPTIONAL` (`identity.tf:9`).
- `require_admin` checks only the group claim (`backend/libs/cappy_common/cappy_common/auth.py:178-184`).
- The web sign-in treats any challenge, including `SOFTWARE_TOKEN_MFA`, as "This account needs a step this app does not support yet" (`web/src/data/auth.ts:215-222`). So a staff member who turned on TOTP could not sign in to the console at all.

A staff password is enough to:

- resolve disputes to `refund_buyer` or `pay_owner`, which moves money;
- take down listings and suspend any account;
- read every report, including the reporters' emails.

ASVS 5.0 V6.3.3 (L2) requires multi-factor authentication. For privileged functions it is the baseline.

**Fix.**

- Put staff in a separate user pool, or a separate app client, with `mfa_configuration = "ON"` (TOTP or passkeys).
- Accept admin tokens only from that client: have `require_admin` check `client_id` against an `ADMIN_CLIENT_IDS` setting.
- Handle the `SOFTWARE_TOKEN_MFA` challenge in `auth.ts`, which members need anyway.

### Medium

#### M-1 [app] The store shells run with no Content-Security-Policy, and the refresh token sits in plain app preferences

The CSP exists only as a CloudFront response header (`infra/platform/edge.tf:398-420`). `web/index.html` has no `<meta http-equiv="Content-Security-Policy">`. The Capacitor shells load the bundled `dist/` from `capacitor://localhost` or `https://localhost`, so no CloudFront header ever reaches them.

ADR 0012 says the refresh token lives "under the CSP", which is true on the web only. In the shells the token is in `@capacitor/preferences` (`web/src/native.ts:13-26`): UserDefaults on iOS and SharedPreferences on Android, neither encrypted. Any script injection in the shell can read it. This is MASVS-PLATFORM-2 and MASVS-STORAGE-1.

**Fix.**

- Emit the same policy as a `<meta http-equiv>` tag at build time for the native build. Adapt `connect-src` to the API origin, and add `capacitor:` or `https://localhost` to `default-src`. A meta tag cannot set `frame-ancestors`, which is acceptable here.
- Finish U-17 (Keychain/Keystore).
- Record the correction in a new ADR (see CLAUDE.md on changing decisions).

#### M-2 [backend+infra] Personal data flows into the analytics lake for two years and survives account deletion

Every event on the bus goes SNS → Firehose → S3 with no filter policy, and is kept 730 days (`infra/platform/analytics.tf:26-30, 82-88`). Both `docs/analytics.md:8` and `analytics.tf:28` say "Events carry ids, never names or emails". These events do carry personal data:

- `moderation.report_received` and `moderation.decision` carry `reporterEmail` (`backend/services/catalog/catalog/moderation.py:193, 365`).
- Moderation decisions also carry free-text `statement`s about the person.
- Every `booking.status_changed` carries `ownerName` and `ownerBusiness`: legal name, business address and VAT ID (`backend/services/booking/booking/repository.py:82-84`, filled at `routes.py:187-189`).

`PROFILE_DELETED` erases none of this, which conflicts with GDPR Art. 17. The same fields are in `listing_snapshot` on the booking rows, which also outlive deletion.

**Fix.**

- Take personal fields out of event payloads. Let consumers that need them (notifications, invoices) fetch them over `/internal/owners/{id}`, or send them on a separate topic that is not archived.
- At the least, add an SNS subscription filter, or a Firehose Lambda transform, that drops those keys.
- Correct the docs.

#### M-3 [backend] Anonymous `POST /reports` can silence reports about a target and burn the SES sending reputation

`/reports` is open to anonymous callers (`moderation.py:137-200`). There are two problems.

**Silencing reports.** After 20 reports about one `targetId` in a day, every further report gets a 429: "this has been reported many times today; it is already being looked at" (`moderation.py:172`). Anonymous reporters are limited only to 3 reports per email address (`:165`), and the address is never verified.

- A scammer can file 20 junk reports about their own listing, using 7 made-up addresses.
- Genuine reports are then turned away for the rest of the day.

**SES reputation.** Each anonymous report makes Cappy send an acknowledgement to whatever address was typed (`notifications/handlers.py:107-108`). The WAF allows 300 POSTs per 5 minutes per IP. That is enough to push SES bounce and complaint rates past the suspension line, and a suspension also stops Cognito's sign-up codes (resilience F22). (The actual SES suspension is unverified.)

**Fix.**

- Do not let the per-target cap reject reports. Accept them all, and merge duplicates in the queue instead.
- Count only signed-in or verified reporters towards any cap.
- Require an emailed confirmation link, or a CAPTCHA or Turnstile token, before an anonymous report is filed or any mail goes out.
- Add a global per-IP limit on anonymous reports.

#### M-4 [infra] Nothing stops credential stuffing in prod, and the breached-password check does not exist

- Sign-in goes straight from the app to `cognito-idp.eu-central-1.amazonaws.com` (`web/src/data/auth.ts:44-66`), so the CloudFront WAF never sees it.
- The user pool has no WAF association.
- Threat protection, which includes the compromised-credentials check, defaults to off (`infra/platform/variables.tf:113-117`), and `infra/envs/prod/main.tf` does not turn it on.
- U-15 is ticked as including a "breached-password check", but no code does one (I searched for `pwned`/`breach`). The only mention is the comment at `identity.tf:24-26`, which points at T-06, and T-06 is off.
- `ALLOW_USER_PASSWORD_AUTH` is enabled (`identity.tf:73`), which suits scripted stuffing tools.

**Fix.**

- Set `cognito_threat_protection = true` in prod (Plus tier, `ENFORCED`), with the compromised-credentials check set to block.
- Attach a regional WAF web ACL to the user pool (`aws_wafv2_web_acl_association`) with per-IP rate rules on `InitiateAuth`, `SignUp` and `ForgotPassword`.
- Consider SRP-only sign-in.
- Un-tick U-15's breached-password part until this ships.

#### M-5 [infra+backend] One compromised service can impersonate every other one

Three things combine here.

- **`sns:Publish` on `"*"`.** The notifications task role has `sns:Publish` and `sns:CreatePlatformEndpoint` on `Resource = "*"` (`infra/platform/ecs.tf:211`). That includes the domain event topic. Notifications could publish `payment.authorised` and move a booking to `requested` without any card being authorised. It could also send SMS to any number (toll fraud).
- **One shared internal token.** Every service except the gateway gets the same `INTERNAL_TOKEN` (`ecs.tf:69`, `data.tf:143-149`), so any service can call every other service's `/internal/*` routes. That includes `payments /internal/intents`, `booking /internal/bookings/{id}/resolve` and every `/internal/people/{id}/export`.
- **One flat security group.** All tasks share one group that allows port 8000 from itself (`ecs.tf:133-139`).

**Fix.**

- Scope `sns:Publish` to `arn:aws:sns:*:*:endpoint/*` (the platform endpoints), and deny the events topic explicitly.
- Add a topic policy on the events topic that allows `sns:Publish` only from the catalog, booking and payments roles.
- Issue a token per caller-callee pair, or use SigV4 or mTLS through Service Connect, and check the caller on each internal route.

#### M-6 [infra] Traffic inside the VPC, including tokens, travels in plaintext

- The services call each other over `http://<svc>:8000` (`infra/platform/ecs.tf:21-25`).
- The ALB reaches the gateway over HTTP (`edge.tf:95-99`).

So bearer tokens, `X-Internal-Token`, payment client secrets and personal data cross the VPC unencrypted. Aurora URLs use `?ssl=require` (`data.tf:110, 126, 135`), which with asyncpg encrypts the connection but does not verify the server certificate.

ASVS 5.0 V12.3.3/V12.3.4 (L2) expect TLS, with the certificate verified, between backend components.

**Fix.**

- Turn on ECS Service Connect TLS (a private CA from AWS Private CA), or use an HTTPS target group for the ALB.
- Use `ssl=verify-full` with the RDS CA bundle baked into the image.

#### M-7 [backend] No per-user limits on messages, notifications, exports or Cognito admin calls

The gateway deliberately has no app-level rate limiting (`backend/services/gateway/gateway/settings.py:40-42`). The WAF's 2000/300 requests per 5 minutes per IP is the only brake on these:

- `POST /bookings/{id}/messages` sends a push to the other side every time (`booking/messages.py:119-157`). Messages are allowed in every status, including after an unpaid or failed booking, and any member can open up to 3 unpaid bookings against any owner. That makes a free channel for push-flooding owners.
- `GET /me/export` fans out to three services, each capped at 10,000 rows (`catalog/routes.py:332-344`).
- `POST /me/sign-out-everywhere` calls `AdminUserGlobalSignOut` each time (`notifications/routes.py:151-158`). **(Unverified):** Cognito's admin API quota is per account, so heavy use could starve notifications' `AdminGetUser`.
- `PUT /me/blocks/{person}` stores any string, without limit.

This is OWASP API4 and API6.

**Fix.**

- Add per-`sub` token buckets. A Postgres row per `sub` per window, or DynamoDB, is enough. Redis is not required.
- Suggested limits: 30 messages a minute and 500 a day per sender; 3 exports a day; 5 sign-out-everywhere calls a day.
- Allow messages only while a booking is `requested`, `accepted`, `active` or `completed`.

### Low

#### L-1 [backend] Malformed input causes 500s instead of 4xx (verified)

- **Cursor without `at`.** `GET /api/bookings?cursor=eyJ4IjogMX0` returns 500 with a `KeyError: 'at'`.
- **Cursor with a bad `at`.** `/api/search?cursor=<{"at":"nope"}>` returns 500 with `ValueError: Invalid isoformat`.
  - `decode_cursor` checks only that the value is a dict (`libs/cappy_common/cappy_common/pagination.py:34-44`).
  - Every caller then indexes into it: `messages.py:175`, `notifications/routes.py:108-110` and the repositories.
- **NaN and Infinity.** Python's `json` accepts `NaN` and `Infinity`:
  - `POST /api/matches` with `"hours": NaN, "maxDistanceKm": Infinity` returns 500.
  - `PUT /listings/{id}` with `maxHours: NaN` returns 500 from Postgres (`invalid input syntax for type json`).
- The 500s leak nothing, but they page on the 5xx burn-rate alarms and can be triggered on purpose.

**Fix.**

- Parse cursors into a typed model, where a missing or bad `at`/`id` raises `Invalid`, or sign cursors with an HMAC.
- Set `model_config = ConfigDict(allow_inf_nan=False)` on `CamelModel`.

#### L-2 [backend] Access tokens keep working after sign-out-everywhere and account deletion (verified locally)

After `POST /me/sign-out-everywhere` returned 204, the same access token still got a 200 on `GET /me`. The services verify tokens statelessly, and `AdminUserGlobalSignOut` revokes only refresh tokens. In prod an access token lives up to 60 minutes (`identity.tf:78`). A lost phone or a deleted account therefore keeps API access for up to an hour (ASVS V7.4.1).

**Fix.**

- Shorten `access_token_validity` to 15 minutes.
- Or keep a small revocation list of `origin_jti` values, or a "not before" time per `sub`, written at sign-out-everywhere and deletion and checked in `TokenVerifier.verify`.

#### L-3 [infra] The Cognito app client is permissive

- `aws_cognito_user_pool_client.web` sets no `read_attributes` or `write_attributes`, so users can rewrite every standard attribute over the public API. They already call `UpdateUserAttributes` for `locale`.
- The pool has no `user_attribute_update_settings { attributes_require_verification_before_update = ["email"] }`. A user can therefore switch their username or email to an address they do not own, which then stays unverified.
  - Notifications checks `email_verified` (`notifications/mail.py:57`), which limits the damage.
  - It still allows squatting on someone else's address.
- Sign-up tells people whether an account exists ("There is already an account with that email", `web/src/data/auth.ts:37`), even though `prevent_user_existence_errors` is on for sign-in.

**Fix.**

- Restrict `write_attributes` to `locale`.
- Require verification before an email update.
- Accept the enumeration risk explicitly, or send the "already registered" message by email instead.

#### L-4 [web] The CSP and header set could be tighter, and Google Fonts load before consent

The CSP is at `infra/platform/edge.tf:403-415`.

**CSP.**

- It allows `style-src 'unsafe-inline'`.
- It still lists `img-src https://images.unsplash.com`, which only seed data uses; ADR 0007 says listings may reference only our own media.
- There is no `Permissions-Policy`, `Cross-Origin-Opener-Policy`, or Trusted Types.

**Headers.**

- The `/api/*` and `/media/*` behaviours have no response-headers policy.
- API answers carry no CSP, including the `text/html` invoice at `/api/payments/invoices/{n}`, which comes from the app's own origin. The backend's headers lack `Content-Security-Policy` (`backend/libs/cappy_common/cappy_common/app.py:113-119`).

**Fonts.** `web/index.html` loads fonts from `fonts.googleapis.com` and `fonts.gstatic.com` on every page, before sign-in. That sends every visitor's IP address to Google, which LG München I (3 O 17493/20) held unlawful without consent. It is the same class of issue as V3-1.

**Fix.**

- Self-host the two fonts.
- Drop Unsplash and `'unsafe-inline'` (move inline styles to classes, or use hashes).
- Add `Permissions-Policy: camera=(self), geolocation=(self), microphone=()` and `COOP: same-origin`.
- Have the backend add `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` to every API response.

#### L-5 [backend] Check-in and check-out evidence photos are public URLs

Evidence photos go through the same `/media/<hash>.webp` path as listing photos (`booking/messages.py:227-253`). CloudFront serves them to anyone with the URL, without authentication (`edge.tf:543-551`). The names are unguessable, but they end up in exports, support tickets and screenshots, and cannot be revoked. They may show people, number plates or the inside of someone's home.

**Fix.**

- Store evidence under a separate prefix with no CloudFront behaviour.
- Serve it through `GET /bookings/{id}/evidence/{photo}` after the `visible()` check, or with short-lived signed URLs.

#### L-6 [backend] Stripe Identity trusts the event's metadata without matching the session

`identity.verification_session.verified` looks the person up only by `metadata.personId`, and never compares `obj["id"]` with `IdentityRow.session_id` (`payments/routes.py:360-368`). The fix is cheap.

**(Unverified):** nothing checks that the verified document's name matches the profile name. Someone could verify with another person's ID and selfie, for example a willing friend's.

**Fix.**

- Require `obj["id"] == row.session_id`.
- Store `verified_outputs.first_name`/`last_name` (with the `verified_outputs` expand) and flag mismatches with the profile for staff.

#### L-7 [app] Store-shell hardening gaps

- **FileProvider scope.** It exposes `external-path name="my_images" path="."`, which is all of external storage (`web/android/app/src/main/res/xml/file_paths.xml`). The share-sheet export needs only `cache-path`.
- **No minification.** Release builds have `minifyEnabled false` (`web/android/app/build.gradle:21-25`).
- **Wildcard access.** `res/xml/config.xml` carries `<access origin="*" />`, left over from Cordova.
- **Placeholder deep-link domain.** The iOS associated domain is still `applinks:cappy.example` (`web/ios/App/App/App.entitlements:9`), while the web writes the AASA file for `cappy.app`. Universal Links will not verify.

**Fix.**

- Keep only `cache-path`.
- Enable R8 with Capacitor's keep rules.
- Delete the `access` wildcard.
- Set the real domain through an xcconfig variable.

#### L-8 [infra] The pipeline has no dependency scanning, actions are pinned by tag, and ECS Exec runs without audit logging

- **No dependency scanning.** CI runs no `pip-audit`/`uv` audit, `npm audit`, Dependabot config or image scan (`.github/workflows/ci.yml`). ASVS V15.2.1 expects one.
- **Tag pinning.** Third-party actions are pinned to tags (`@v5`, `@v3`), not commit SHAs.
- **ECS Exec.** It is on for every prod task (`infra/platform/ecs.tf:318`), with `ssmmessages:*` on `"*"` (`ecs.tf:242`). No `execute_command_configuration` logging is visible, so a shell in prod leaves no audit trail. **(Unverified):** the cluster default may log.

**Fix.**

- Add `pip-audit` (via `uv export`) and `npm audit --omit=dev` jobs, or Dependabot, plus ECR scan-on-push.
- Pin actions to SHAs.
- Configure `execute_command_configuration { logging = "OVERRIDE"; log_configuration { cloud_watch_log_group_name = ... } }`, or turn ECS Exec off in prod except during an incident.

#### L-9 [backend] Registering a device token takes it over

`POST /notifications/devices` with a token that is already registered to someone else moves it to the caller (`notifications/routes.py:40-49`). Anyone who learns another person's APNs or FCM token (tokens are not secret against a person who has the device) can take that person's pushes and point their own pushes at that device.

**Fix.** Rebind a token only when the old user's last registration is older than the new one and the platform matches. Better, make the rebind require the device's previous binding, via a per-install id stored in the app.

#### L-10 [backend] `/api/client-errors` is anonymous, its limit is spoofable, and it logs free text

The limit is keyed on the first `X-Forwarded-For` hop, which a client can forge (`gateway/main.py:218-220`). The endpoint logs `message`, `stack` and `route` as sent (`:225`). Free text from a crashing screen can hold names, addresses or message bodies, which then land in CloudWatch.

**Fix.**

- Behind CloudFront, key the limit on `CloudFront-Viewer-Address` (or the last hop the ALB appends).
- Before logging, remove emails and digit runs from `message` and `stack`, and replace ids in `route` with placeholders.

## Privacy and security law in each market (GOAL 16)

Cappy targets Europe, the UK, the US and Canada. The laws that apply are GDPR and UK GDPR (with the Swiss FADP for Switzerland), CCPA/CPRA and the other US state laws, and PIPEDA with Québec Law 25.

This section pairs each legal duty with what the code and the policy do today. Items tagged `[legal]` need counsel or the business rather than code. Whether a given law applies to Cappy (for example the CPRA's revenue and volume thresholds) is itself a `[legal]` question.

What already meets these duties:

- EU data stays in the EU: everything runs in eu-central-1, and prod has no other region.
- Export and deletion are in the app (Art. 15, 17 and 20, CCPA know and delete, Law 25 portability in a structured JSON format).
- Everyone must confirm they are 18 or older, so COPPA does not apply.
- There is no advertising technology and nothing is sold. The policy says so (`Legal.tsx:190`).
- The app never uses device geolocation (I found no `navigator.geolocation`), so there is no "precise geolocation" sensitive data under the CPRA.
- Push payloads carry only the booking title and a link, never message text (`notifications/handlers.py:74-85`).

### Medium

#### G-1 [legal+web] The English privacy policy, shown in the UK, US and Canada, is incomplete and covers no law outside the EU

The German policy lists messages, hand-over photos, reports, identity checks, push notifications, and Apple and Google as recipients (`web/src/app/screens/Legal.tsx:504-525`). The English `Privacy()` (`Legal.tsx:150-205`) lists none of these. The English text is what the UK, US and Canadian markets read.

Neither version has:

- a CCPA/CPRA section: categories collected, sources, purposes, the categories of recipients, the rights to know, delete and correct, non-discrimination, how to make a request, and a notice at collection;
- a PIPEDA or Law 25 section: the person in charge of personal information, the countries the data goes to, and Québec-specific rights;
- a UK GDPR section: the UK representative, and the ICO as the complaint route;
- any mention that data is transferred outside the reader's country.

**Fix.**

- Bring the English policy up to the German one.
- Add a section per market: CCPA/CPRA (with a "we do not sell or share" statement and how to submit and verify a request, with a 45-day answer), PIPEDA and Law 25, and UK GDPR.
- Add a test that fails when the two languages list different categories.

#### G-2 [legal] Identity checks process government IDs and biometric data

Stripe Identity takes a document and a live selfie for bookings above 300 € (G-8, `payments/routes.py:253-271`). That makes it:

- GDPR Art. 9 special-category data (biometrics used to identify someone), which needs explicit consent or another Art. 9(2) ground;
- sensitive personal information under the CPRA (government ID, biometrics);
- covered by the Illinois BIPA, the Texas CUBI and Washington's biometric law, which require a written release and a public retention schedule. **(Unverified):** whether Stripe's hosted flow gives that release on Cappy's behalf;
- under Québec's IT framework act (s. 44-45), a biometric identity check has to be declared to the CAI in advance, with a PIA.

Stripe's role (processor or independent controller) for Identity has to match what the policy says: the German policy calls Stripe an independent controller "for payment data" and lists Identity there too.

The DPIA is already tracked as G-B3.

**Fix.**

- Use a written consent screen before `verifyIdentity`, and store that consent.
- Publish the biometric retention schedule.
- Declare the check to the CAI.
- Confirm Stripe's role in the DPA, and extend G-B3 to cover the Law 25 PIA and the US biometric laws.

#### G-3 [legal+infra] There is no breach-response procedure, and nothing in Terraform to detect a breach

The deadlines are:

- **GDPR and UK GDPR:** notify the supervisory authority within 72 hours (Art. 33), and the people affected when the risk is high (Art. 34).
- **PIPEDA:** report breaches with "a real risk of significant harm" to the OPC and to the people affected, and keep a record of every breach for 24 months.
- **Law 25:** keep a register of confidentiality incidents, and notify the CAI when there is a risk of serious injury.
- **US states:** each has its own deadline (often 30 to 60 days), and some require notifying the attorney general.

`docs/runbook.md` has no incident or breach procedure. I found no mention of breach, incident notification, the 72 hours or a register.

`infra/` declares no CloudTrail, GuardDuty, Security Hub or AWS Config (none are mentioned anywhere in the tree). Without them there is no audit trail of who read which secret or snapshot. **(Unverified):** these may be enabled at the AWS organisation level.

**Fix.**

- Write a runbook section with the triage steps, who decides, the per-jurisdiction notification matrix and templates, and an incident register (a table or a document).
- Add an organisation CloudTrail with log-file validation, GuardDuty and Security Hub to Terraform, and alarm on root use and on reads of Secrets Manager or RDS snapshots from outside the task roles.

#### G-4 [legal] No privacy officer or local representatives are named

- Law 25 requires a person in charge of the protection of personal information (by default the CEO), whose title and contact details are published on the website.
- PIPEDA requires a designated, accountable individual.
- An EU operator with no UK establishment needs a UK representative (UK GDPR Art. 27), and usually a Swiss representative (FADP Art. 14).
- Whether GDPR requires a DPO (Art. 37) should be assessed and the result recorded.

The legal pages show only the operator's name and one contact address (`Legal.tsx:156-159`).

**Fix.**

- Appoint and publish the Law 25 and PIPEDA privacy officer, the UK and Swiss representatives, and the DPO if one is needed.
- Add `VITE_LEGAL_PRIVACY_OFFICER` next to the other `VITE_LEGAL_*` variables so the policy renders them.

#### G-5 [legal+infra] Data location and transfers are not documented, and non-EU data leaves its region

**Where the data lives.** Everything is in eu-central-1 (`infra/envs/prod/main.tf:7,20`), and resilience F26 records the single-region decision. That meets "EU data in the EU". It also means every US and Canadian user's data is exported to Germany:

- **PIPEDA:** people must be told that their data is processed abroad.
- **Law 25 s. 17:** before personal information leaves Québec, a transfer impact assessment is required, along with a written agreement with the recipient.
- GOAL 16 asks for a decision on "where each market's data lives". No ADR records that US and Canadian data sits in the EU, or whether US or Canadian regions (with Stripe Inc. or Stripe Canada) will come later.

**Transfers out of the EU.** These happen today, relying on the EU–US Data Privacy Framework or SCCs:

- CloudFront edges and WAF. The web ACL and its metrics live in us-east-1 (`edge.tf:161-165`). `sampled_requests_enabled = true` keeps sampled requests, headers included (so bearer tokens), where anyone with WAF console access can read them.
- APNs and FCM (Apple and Google).
- Stripe (US parent, DPF-certified).
- Google Fonts, which has no legal basis before consent (L-4).

The policy says only "in the EU (Frankfurt, eu-central-1)" (`Legal.tsx:187`). It does not name the transfers or the safeguards.

**Fix.**

- Record in an ADR where each market's data lives (EU in eu-central-1; US and Canada in the EU for now, or ca-central-1 and a US region later).
- Write the Law 25 transfer PIA and a transfer impact assessment for the US recipients.
- In the policy, name the transfers and their safeguards (DPF or SCCs through the AWS, Stripe, Apple and Google DPAs).
- Turn off WAF `sampled_requests_enabled` on the rules that see authenticated traffic, or accept this in writing.

### Low

#### G-6 [backend] Deleting an account does not delete everything

- The Cognito user, which holds the email address, is deleted only if the app then calls `DeleteUser` (`catalog/routes.py:312-315`, `web/src/data/auth.ts` `deleteAccount`). If the app crashes or goes offline after `DELETE /me`, the email stays in Cognito indefinitely.
- The analytics lake keeps names and emails (M-2).
- `listing_snapshot.ownerName` and `ownerBusiness` stay on the booking rows. That may be justified by the retention duty for financial records, but the policy says bookings are kept "without your name".

GDPR Art. 17, CCPA deletion (which has to reach service providers) and Law 25 all expect the erasure to be complete.

**Fix.**

- Have the notifications service (which already holds Cognito admin rights) call `AdminDeleteUser` on `PROFILE_DELETED`.
- Remove names from the snapshot, or state in the policy that invoices keep the owner's name (§ 14 UStG and § 147 AO).

#### G-7 [legal+backend] The CCPA/CPRA request process is missing

There is no documented way to handle requests from authorised agents, to verify people who cannot sign in, or to answer within 45 days (extendable by 45) and keep records for 24 months. Cappy neither sells nor shares data, so honouring the Global Privacy Control signal is not required today. That has to be rechecked if any ad or analytics SDK is ever added.

Several US state laws (for example Texas and Nebraska) apply regardless of revenue to businesses that are not small businesses.

**Fix.** Use a privacy-request mailbox with a documented workflow and a register. Have counsel confirm which state laws apply.

#### G-8 [legal] The processing records and assessments need extending for the new markets

G-B3 (DPAs, the Art. 30 records, the DPIA for identity checks) is still open. It should also cover:

- the Law 25 PIAs, for new systems and for transfers;
- the CPRA risk assessments and cybersecurity audits, if the thresholds are met (CPPA regulations, 2026);
- UK ICO registration and the data protection fee.

**Fix.** Extend G-B3 with these.

## Checklist

Most severe first. `[legal]` items are for the business and counsel.

- [ ] P-1 [backend] H-1: zero or negative `unitsPerHour` (and other numeric listing fields) are accepted, and one such listing makes `/matches` return 500 for the whole category nearby — bound every listing number with `Field(gt/ge/le)` plus `min_hours <= max_hours`; skip candidates whose quote raises; add a regression test
- [ ] P-2 [infra] H-2: the deploy job runs `npm ci` while holding AdministratorAccess credentials — build the web app in a job without AWS credentials (use `--ignore-scripts` where possible), and give the deploy role least privilege (a separate S3 and invalidation role for the web upload)
- [ ] P-3 [backend] H-3: staff powers need only a password (no MFA) — a staff pool or client with `mfa_configuration = "ON"`; `require_admin` checks the staff client id
- [ ] P-4 [web] H-3: the sign-in flow cannot answer `SOFTWARE_TOKEN_MFA` — handle the challenge (`RespondToAuthChallenge`) and TOTP setup
- [ ] P-5 [app] M-1: the Capacitor shells run without a CSP while holding the refresh token — emit the CSP as a meta tag in native builds; finish U-17; write an ADR that corrects ADR 0012
- [ ] P-6 [backend] M-2: `reporterEmail`, `ownerName` and `ownerBusiness` travel in events into the two-year analytics lake — take personal data out of event payloads (consumers fetch it by id) or filter it in Firehose; correct `docs/analytics.md`
- [ ] P-7 [backend] M-3: anonymous reports can hit the 20-per-target cap and turn genuine reports away, and send mail to unverified addresses — stop rejecting reports on the per-target cap (merge duplicates); confirm the email or require a CAPTCHA before any anonymous report or mail
- [ ] P-8 [infra] M-4: prod has no protection against credential stuffing or breached passwords (threat protection off, no WAF on Cognito) — turn on threat protection (ENFORCED, block compromised credentials) and add a WAF association on the user pool; un-tick U-15's breached-password claim
- [ ] P-9 [infra] M-5: the notifications role has `sns:Publish` on `*`, so it can forge domain events — scope it to platform endpoints and add a publisher allow-list policy on the events topic
- [ ] P-10 [backend] M-5: one `INTERNAL_TOKEN` is shared by all services — use per-caller credentials (a token per pair, or SigV4/mTLS) and check the caller on each `/internal` route
- [ ] P-11 [infra] M-6: service-to-service and ALB-to-gateway traffic is plain HTTP, and the database uses `ssl=require` — Service Connect TLS or an HTTPS target group; `ssl=verify-full` with the RDS CA bundle
- [ ] P-12 [backend] M-7: no per-user limits on messages (push flooding), exports or sign-out-everywhere — per-`sub` limits (Postgres or DynamoDB counters); messages only in live booking states
- [ ] P-13 [legal] G-3: no breach-response procedure (GDPR 72 h, PIPEDA record and report, Law 25 incident register, US state deadlines) — a runbook section with the notification matrix, templates and an incident register
- [ ] P-14 [infra] G-3: no CloudTrail, GuardDuty or Security Hub in Terraform — an organisation CloudTrail with log validation, GuardDuty, Security Hub, and alarms on secret and snapshot access
- [ ] P-15 [legal] G-1: the English privacy policy omits messages, photos, reports, identity checks and push, and has no CCPA/CPRA, PIPEDA/Law 25 or UK sections — match the German policy; add per-market sections; notice at collection; "we do not sell or share"
- [ ] P-16 [web] G-1: the two languages of the policy drift apart — render both from one list of categories and recipients, with a test that fails on a mismatch
- [ ] P-17 [legal] G-2: identity checks are biometric and government-ID data (GDPR Art. 9, CPRA sensitive data, BIPA, CUBI, Québec's CAI declaration) — explicit consent, a published retention schedule, the CAI declaration, and Stripe's role confirmed in the DPA
- [ ] P-18 [web] G-2: nothing records consent before `verifyIdentity` — a consent screen, with the consent stored against the verification session
- [ ] P-19 [legal] G-5: US and Canadian data sits in Frankfurt, and EU data goes to the US (CloudFront and WAF, APNs and FCM, Stripe) with no documented safeguards — an ADR on where each market's data lives; a Law 25 s. 17 transfer PIA; transfer impact assessments; name the DPF or SCCs in the policy
- [ ] P-20 [infra] G-5: WAF sampled requests keep request headers, including bearer tokens, in us-east-1 — turn off `sampled_requests_enabled` on rules that see authenticated traffic, or accept this in writing
- [ ] P-21 [legal] G-4: no Law 25 or PIPEDA privacy officer, no UK or Swiss representative, no DPO assessment — appoint them and publish them (`VITE_LEGAL_PRIVACY_OFFICER`)
- [ ] P-22 [backend] L-1: tampered cursors and NaN/Infinity numbers give 500s — a typed or HMAC-signed cursor; `allow_inf_nan=False` on `CamelModel`
- [ ] P-23 [backend] G-6: deleting an account leaves the Cognito user (and its email) behind when the app does not call `DeleteUser` — `AdminDeleteUser` on `PROFILE_DELETED`; drop names from booking snapshots or say why they are kept
- [ ] P-24 [backend] L-2: access tokens work for up to 60 minutes after sign-out-everywhere or deletion — 15-minute access tokens, or a per-`sub` "not before" or `origin_jti` revocation check
- [ ] P-25 [infra] L-3: the Cognito client lets users write any attribute and change their email without verification — `write_attributes = ["locale"]`; `attributes_require_verification_before_update = ["email"]`
- [ ] P-26 [web] L-4: Google Fonts load before sign-in, the CSP has `'unsafe-inline'` and Unsplash, and API and media responses have no CSP — self-host fonts; tighten the CSP; add Permissions-Policy and COOP; add `default-src 'none'` to API answers
- [ ] P-27 [backend] L-5: evidence photos are public CloudFront URLs — a private prefix served through an authorized booking route, or signed URLs
- [ ] P-28 [backend] L-6: the Identity webhook does not match `session_id`, and nothing checks the verified name against the profile — require the session id to match; store and compare the verified name
- [ ] P-29 [legal] G-7: no CCPA/CPRA request process (authorised agents, verification, 45 days, 24-month records); which state laws apply is unknown — a privacy-request workflow and register; counsel to confirm which state laws apply; recheck GPC if an ad or analytics SDK is ever added
- [ ] P-30 [legal] G-8: G-B3 does not cover the Law 25 PIAs, the CPRA risk assessments or audits, or ICO registration — extend G-B3
- [ ] P-31 [app] L-7: the FileProvider exposes external storage root, release builds are unminified, `access origin="*"` remains, and the associated domain is a placeholder — keep only `cache-path`; enable R8; remove the wildcard; set the real `applinks:` domain
- [ ] P-32 [infra] L-8: no dependency or image scanning, actions pinned by tag, ECS Exec without an audit log — `pip-audit`/`npm audit`/ECR scanning in CI; SHA pins; ECS Exec logging, or Exec off in prod
- [ ] P-33 [backend] L-9: re-registering a push token takes it from another user — rebind only with proof of the previous install
- [ ] P-34 [backend] L-10: `/api/client-errors` has a forgeable limit key and logs free text — key on CloudFront's viewer address; remove personal data before logging

**Counts:** 3 high; 12 medium (7 technical, 5 legal and privacy: G-1 to G-5); 13 low (10 technical, 3 legal and privacy: G-6 to G-8). No critical findings.
