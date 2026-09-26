"""Who is calling: a Cognito access token, verified locally, in every service.

There is no identity header. A service that acts for a person reads the
bearer token itself and checks it against the user pool's published keys:
signature (RS256 only), issuer, expiry, ``token_use == "access"`` and the app
client. Verifying is microseconds once the keys are cached, so there is no
reason to trust anything a previous hop says.

Service-to-service calls to ``/internal/*`` carry ``X-Internal-Token`` instead
(see ``require_internal``).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field

import httpx
import jwt
from fastapi import Request
from jwt.algorithms import RSAAlgorithm

from .errors import Forbidden, Unauthorized, Unavailable

log = logging.getLogger(__name__)

_ALGORITHMS = ["RS256"]


@dataclass(frozen=True)
class Principal:
    """A verified caller. ``sub`` is their stable id, and their owner id."""

    sub: str
    username: str | None = None
    client_id: str | None = None
    claims: dict = field(default_factory=dict, compare=False, repr=False)


class TokenVerifier:
    """Verifies access tokens against a JWKS, fetched lazily and cached.

    A token signed with a key id we have not seen triggers one refresh (key
    rotation), but refreshes are rate-limited so a stream of garbage tokens
    with random ``kid`` values cannot turn into a stream of requests to the
    identity provider.
    """

    def __init__(
        self,
        *,
        issuer: str,
        jwks_url: str,
        client_ids: list[str],
        jwks: dict | None = None,
        fallback_jwks: dict | None = None,
        leeway_seconds: int = 30,
        min_refresh_seconds: float = 60.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.issuer = issuer
        self.jwks_url = jwks_url
        self.client_ids = frozenset(client_ids)
        self._leeway = leeway_seconds
        self._min_refresh = min_refresh_seconds
        self._keys: dict[str, object] = {}
        self._last_refresh = float("-inf")
        self._lock = asyncio.Lock()
        self._http = http
        if fallback_jwks is not None:
            # The keys as they were at deploy: a task that starts while Cognito
            # is unreachable still verifies tokens. Refreshed like any other.
            self._load(fallback_jwks)
        if jwks is not None:
            self._load(jwks)
            # A static key set (tests) is never refreshed from the network.
            self._last_refresh = float("inf")

    def _load(self, jwks: dict) -> None:
        keys = {}
        for k in jwks.get("keys", []):
            if k.get("kty") == "RSA" and k.get("kid"):
                keys[k["kid"]] = RSAAlgorithm.from_jwk(json.dumps(k))
        self._keys = keys

    async def _refresh(self) -> None:
        async with self._lock:
            if time.monotonic() - self._last_refresh < self._min_refresh:
                return
            self._last_refresh = time.monotonic()
            client = self._http or httpx.AsyncClient(timeout=5.0)
            try:
                r = await client.get(self.jwks_url)
                r.raise_for_status()
                self._load(r.json())
            except (httpx.HTTPError, ValueError) as e:
                log.warning("could not fetch JWKS from %s: %s", self.jwks_url, e)
            finally:
                if self._http is None:
                    await client.aclose()

    async def _key_for(self, kid: str) -> object:
        if kid not in self._keys:
            await self._refresh()
        key = self._keys.get(kid)
        if key is None:
            raise Unauthorized("your sign-in is not valid; sign in again")
        return key

    async def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise Unauthorized("your sign-in is not valid; sign in again") from e
        if header.get("alg") not in _ALGORITHMS or not header.get("kid"):
            raise Unauthorized("your sign-in is not valid; sign in again")
        key = await self._key_for(header["kid"])
        try:
            claims = jwt.decode(
                token,
                key=key,  # type: ignore[arg-type]
                algorithms=_ALGORITHMS,
                issuer=self.issuer,
                leeway=self._leeway,
                # Cognito access tokens carry ``client_id``, not ``aud``.
                options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
            )
        except jwt.ExpiredSignatureError as e:
            raise Unauthorized("your session has ended; sign in again", code="token_expired") from e
        except jwt.PyJWTError as e:
            raise Unauthorized("your sign-in is not valid; sign in again") from e
        if claims.get("token_use") != "access":
            raise Unauthorized("send an access token, not an id token")
        if self.client_ids and claims.get("client_id") not in self.client_ids:
            raise Unauthorized("that token was issued to another application")
        return Principal(
            sub=str(claims["sub"]),
            username=claims.get("username"),
            client_id=claims.get("client_id"),
            claims=claims,
        )


def bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def optional_principal(request: Request) -> Principal | None:
    """The caller, or None when anonymous. A token that is present but bad is a
    401, never silently anonymous: a client with an expired session must learn
    to refresh, not see a logged-out page."""
    token = bearer_token(request)
    if token is None:
        return None
    verifier: TokenVerifier | None = getattr(request.app.state, "verifier", None)
    if verifier is None:
        raise Unauthorized("this service does not accept sign-ins")
    principal = await verifier.verify(token)
    # Signed out everywhere, or the account deleted, after this token was
    # issued: it no longer counts, though it has not expired yet (P-24).
    revocations = getattr(request.app.state, "revocations", None)
    if revocations is not None:
        not_before = await revocations.not_before(principal.sub)
        # `iat` is whole seconds; the revocation is exact. Rounding both down
        # (as before) let a token issued in the same second as the revocation,
        # the very one that asked for it, live on for 15 minutes (V4-24). A
        # token issued later within that second is refused too: sign in again.
        if not_before is not None and int(principal.claims.get("iat", 0)) < not_before:
            raise Unauthorized("your session has ended; sign in again", code="token_expired")
    request.state.principal = principal
    return principal


async def require_principal(request: Request) -> Principal:
    principal = await optional_principal(request)
    if principal is None:
        raise Unauthorized("sign in to do that")
    return principal


class StaffMfa:
    """Whether a staff account has TOTP MFA switched on (P-3).

    Checking the account is checking the session: Cognito challenges every
    user who has MFA enabled for the code at each sign-in, so no token of such
    a user was issued without it. Cached for a few minutes per person, so a
    moderator's queue does not cost a Cognito call per request."""

    ttl_seconds = 300.0

    def __init__(self, settings) -> None:  # noqa: ANN001
        self._settings = settings
        self._client = None
        self._cache: dict[str, tuple[float, bool]] = {}

    def _lookup(self, username: str) -> bool:
        if self._client is None:
            from .events import aws_client

            self._client = aws_client("cognito-idp", self._settings, self._settings.cognito_endpoint_url)
        user = self._client.admin_get_user(UserPoolId=self._settings.user_pool_id, Username=username)
        return "SOFTWARE_TOKEN_MFA" in (user.get("UserMFASettingList") or [])

    async def enabled(self, username: str) -> bool:
        hit = self._cache.get(username)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        try:
            on = await asyncio.to_thread(self._lookup, username)
        except Exception as e:  # noqa: BLE001 - fail closed: no staff powers while Cognito cannot say
            log.warning("could not check MFA for a staff account: %s", e)
            raise Unavailable("staff checks are unavailable right now; try again shortly") from e
        self._cache[username] = (time.monotonic() + self.ttl_seconds, on)
        return on


def is_staff(p: Principal, settings) -> bool:  # noqa: ANN001
    """Whether the token says staff (before any MFA check)."""
    claim = p.claims.get(settings.staff_claim)
    values = claim if isinstance(claim, list) else str(claim or "").split()
    return settings.staff_value in values


def staff_role(p: Principal, settings) -> str:  # noqa: ANN001
    """``lead`` or ``support``: which approval limit applies (H-6)."""
    claim = p.claims.get(settings.staff_claim)
    values = claim if isinstance(claim, list) else str(claim or "").split()
    return "lead" if settings.staff_lead_value in values else "support"


async def require_admin(request: Request) -> Principal:
    """Moderators and support: the token's staff claim holds the staff value
    (Cognito: group "admin" in ``cognito:groups``; another identity provider
    is two settings, F-3), signed in with MFA wherever staff MFA is required
    (always when deployed)."""
    p = await require_principal(request)
    settings = request.app.state.settings
    if not is_staff(p, settings):
        raise Forbidden("this needs a Cappy staff account")
    if settings.staff_mfa_required:
        mfa: StaffMfa | None = getattr(request.app.state, "staff_mfa", None)
        if mfa is None:
            mfa = request.app.state.staff_mfa = StaffMfa(settings)
        # With email sign-in (our pools) the Cognito username is the sub.
        if not await mfa.enabled(p.username or p.sub):
            raise Forbidden(
                "staff accounts need an authenticator app: turn on MFA, then sign in again", code="mfa_required"
            )
    return p


def require_internal(request: Request) -> None:
    """For ``/internal/*`` routes: the caller must be one of our services, and
    one this service lets call it (P-10)."""
    settings = request.app.state.settings
    given = request.headers.get("x-internal-token", "")
    callers: dict[str, str] = settings.internal_caller_hashes
    if callers:
        # ponytail: per service, not per route; a route-level table when a
        # caller should reach only some of a service's internal routes.
        want = callers.get(given.partition(":")[0])
        got = hashlib.sha256(given.encode()).hexdigest()
        if not want or not hmac.compare_digest(got, want):
            raise Forbidden("internal route")
        return
    expected: str = settings.internal_token.get_secret_value()
    if not expected:
        # Only reachable in local/test, where settings allow an empty token.
        return
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise Forbidden("internal route")


def make_verifier(settings) -> TokenVerifier | None:
    if not settings.auth_issuer:
        return None
    fallback = json.loads(settings.auth_jwks_fallback) if settings.auth_jwks_fallback else None
    return TokenVerifier(
        issuer=settings.auth_issuer,
        jwks_url=settings.jwks_url,
        client_ids=settings.auth_client_id_list,
        fallback_jwks=fallback,
    )
