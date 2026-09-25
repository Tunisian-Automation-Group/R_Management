from __future__ import annotations

from cappy_common.settings import CommonSettings


class Settings(CommonSettings):
    service_name: str = "gateway"
    upstream_timeout_seconds: float = 15.0
    # Photos are the one large body (the catalog's own limit is the real one).
    upload_max_bytes: int = 12_064_000
    # A built copy of the web app (``web/dist``). Locally the gateway serves it
    # at ``/`` so the app and the API share one origin. In AWS, CloudFront
    # serves the app from S3 and this stays empty.
    static_dir: str = ""
    # ponytail: no app-level rate limiting. WAF rate-based rules limit per IP
    # at the edge (ADR 0008); per-user limits need shared state (Redis) and
    # are worth adding once abuse shows up in the metrics.
