from __future__ import annotations

from typing import ClassVar

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    # It routes; each service verifies tokens and guards its own /internal.
    verifies_tokens: ClassVar[bool] = False
    uses_internal_token: ClassVar[bool] = False
    service_name: str = "gateway"
    upstream_timeout_seconds: float = 15.0
    # Photos are the one large body (the catalog's own limit is the real one).
    upload_max_bytes: int = 12_064_000
    # A built copy of the web app (``web/dist``). Locally the gateway serves it
    # at ``/`` so the app and the API share one origin. In AWS, CloudFront
    # serves the app from S3 and this stays empty.
    static_dir: str = ""

    # --- overload (docs/resilience.md F1, F3) -----------------------------------
    # Requests one task works on at once. Past this it answers 503 at once
    # (with Retry-After) instead of queueing everyone into a timeout. Writes
    # (bookings, payments, listings) keep headroom above browsing.
    max_in_flight: int = 400
    browse_share: float = 0.8
    # Calls in flight to any one service: a slow service cannot take every
    # connection the others need.
    per_upstream_in_flight: int = 200

    # --- the store apps (ADR 0012) -----------------------------------------------
    # Builds older than this are told to update; the API only changes
    # additively within a supported range.
    app_min_version: str = "1.0.0"
    app_latest_version: str = "1.0.0"
    # Crash and error reports from the apps (S-7), per client address.
    client_errors_per_minute: int = 10
    # Proxies in front of the gateway that append to X-Forwarded-For
    # (CloudFront, then the load balancer: 2 in AWS; none locally). The client
    # is the hop they saw, counted from the right: what a sender writes into
    # the header itself is to the left of it and ignored (P-34).
    trusted_proxy_hops: int = 0
    # ponytail: no app-level rate limiting. WAF rate-based rules limit per IP
    # at the edge (ADR 0008); per-user limits need shared state (Redis) and
    # are worth adding once abuse shows up in the metrics.
