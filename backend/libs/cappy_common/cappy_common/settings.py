"""Settings every service shares. Each service extends this with its own.

Everything comes from the environment (12-factor). ``APP_ENV`` decides how
strict the checks are: ``local`` and ``test`` are forgiving so one service can
run on a laptop with no configuration; ``staging`` and ``prod`` refuse to boot
with anything unsafe, rather than discovering it in an incident.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "test", "staging", "prod"]


class UnsafeSettings(RuntimeError):
    """Raised at startup when a deployed environment is misconfigured."""


class CommonSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Services that act on behalf of a person verify their access token, and a
    # deployed one must know whose tokens to trust. Workers set this False.
    verifies_tokens: ClassVar[bool] = True
    # Services that call or serve /internal/* need the internal token. The
    # gateway does neither, so it is never given it.
    uses_internal_token: ClassVar[bool] = True

    app_env: AppEnv = "local"
    service_name: str = "cappy"
    log_level: str = "INFO"
    # JSON lines for CloudWatch; plain text is friendlier in a terminal.
    log_json: bool = False

    # --- where the other services live --------------------------------------
    catalog_url: str = "http://localhost:8001"
    matching_url: str = "http://localhost:8002"
    booking_url: str = "http://localhost:8003"
    payments_url: str = "http://localhost:8005"
    notifications_url: str = "http://localhost:8006"

    # Aurora's reader endpoint, for services with heavy public reads. Empty:
    # reads go to the writer.
    database_read_url: str = ""

    # --- service-to-service ------------------------------------------------
    # Every ``/internal/*`` route requires this in ``X-Internal-Token``. The
    # network already keeps those routes private (the gateway never routes
    # them, security groups allow only service-to-service traffic); this is the
    # second lock, so one misconfigured rule is not an open door.
    internal_token: SecretStr = SecretStr("")
    # Per caller (P-10): this service's own token is "<service>:<random>", and
    # it accepts only the callers listed here, as "<caller>=<sha256 of their
    # token>,...". A service never holds another's token, so one leaked token
    # opens only the routes its owner could already call. Empty (local, tests):
    # one shared token, as above.
    internal_callers: str = ""

    # --- identity (Cognito, or cognito-local in development) ----------------
    # The ``iss`` claim we accept, e.g.
    # https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_AbC123
    auth_issuer: str = ""
    # Where the signing keys are. Defaults to ``{issuer}/.well-known/jwks.json``;
    # separate because cognito-local names itself differently from the address
    # other containers reach it on.
    auth_jwks_url: str = ""
    # The signing keys as fetched at deploy (JSON), used until the live set
    # can be fetched: new tasks keep working through a Cognito outage.
    auth_jwks_fallback: str = ""
    # App client ids whose access tokens we accept (comma-separated).
    auth_client_ids: str = ""
    # The user pool itself, for services that ask Cognito about a person
    # (staff MFA below; notifications for emails). cognito-local locally.
    user_pool_id: str = ""
    cognito_endpoint_url: str = ""
    # Staff powers need TOTP MFA on the staff account (P-3). Unset: required
    # when deployed, not locally (cognito-local has no MFA). Deployed, false is
    # refused below.
    admin_mfa_required: bool | None = None

    # --- events ----------------------------------------------------------------
    # ``memory://`` in tests and single-process runs; ``sns://<topic-arn>``
    # everywhere else.
    event_bus_url: str = "memory://"
    # This service's own SQS queue, when it consumes events.
    event_queue_url: str = ""

    # --- AWS ---------------------------------------------------------------------
    aws_region: str = "eu-central-1"
    # LocalStack in development; empty in AWS.
    aws_endpoint_url: str = ""

    # --- HTTP edge ---------------------------------------------------------------
    # Browsers are served from the same origin as the API in every environment
    # (CloudFront in AWS, the Vite proxy locally), so CORS is off unless a
    # separately hosted client is listed here explicitly.
    cors_origins: str = ""
    # Requests larger than this are refused before they are read. Uploads raise
    # it on their own route.
    max_body_bytes: int = 256_000

    # Who is staff (F-3): the claim in the access token and the value in it.
    # A list claim (Cognito groups) or a space-separated string (OAuth scopes).
    staff_claim: str = "cognito:groups"
    staff_value: str = "admin"

    # --- feature flags (cappy_common/flags.py, S-26) --------------------------
    # "name:percent,...". One setting for every service: the gateway hands it
    # to the apps in /api/app-config, and a service that enforces a flag reads
    # the same value, so what the app shows and what the server does agree.
    feature_flags: str = ""

    # --- observability ---------------------------------------------------------
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4318"

    @property
    def deployed(self) -> bool:
        return self.app_env in ("staging", "prod")

    @property
    def internal_caller_hashes(self) -> dict[str, str]:
        pairs = (p.split("=", 1) for p in self.internal_callers.split(",") if "=" in p)
        return {k.strip(): v.strip().lower() for k, v in pairs}

    @property
    def staff_mfa_required(self) -> bool:
        return self.deployed if self.admin_mfa_required is None else self.admin_mfa_required

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def auth_client_id_list(self) -> list[str]:
        return [c.strip() for c in self.auth_client_ids.split(",") if c.strip()]

    @property
    def jwks_url(self) -> str:
        if self.auth_jwks_url:
            return self.auth_jwks_url
        return f"{self.auth_issuer.rstrip('/')}/.well-known/jwks.json" if self.auth_issuer else ""

    def unsafe_reasons(self) -> list[str]:
        """Everything that must not reach a deployed environment. Subclasses add
        their own and call ``super()``."""
        problems: list[str] = []
        if self.uses_internal_token:
            token = self.internal_token.get_secret_value()
            if len(token) < 32:
                problems.append("INTERNAL_TOKEN must be set to at least 32 random characters")
            if not token.startswith(f"{self.service_name}:"):
                problems.append("INTERNAL_TOKEN must be this service's own token (<service>:<random>)")
            if not self.internal_caller_hashes:
                problems.append("INTERNAL_CALLERS must list which services may call this one")
        if self.event_bus_url.startswith("memory://"):
            problems.append("EVENT_BUS_URL must be a real bus (sns://...), not memory://")
        if self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL points at an emulator")
        if any(o == "*" or o.startswith("http://") for o in self.cors_origin_list):
            problems.append("CORS_ORIGINS must list explicit https origins")
        if self.verifies_tokens:
            if not self.staff_mfa_required:
                problems.append("ADMIN_MFA_REQUIRED cannot be false: staff powers need MFA")
            if not self.auth_issuer.startswith("https://"):
                problems.append("AUTH_ISSUER must be the https Cognito issuer")
            if not self.auth_client_id_list:
                problems.append("AUTH_CLIENT_IDS must list the app client ids")
        return problems

    @model_validator(mode="after")
    def _refuse_unsafe(self) -> CommonSettings:
        if self.deployed:
            problems = self.unsafe_reasons()
            if problems:
                raise UnsafeSettings(f"refusing to start {self.service_name} in {self.app_env}: " + "; ".join(problems))
        return self
